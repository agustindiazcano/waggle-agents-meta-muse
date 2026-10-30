"""E1 runs on development seeds: one configuration, scenarios S01 to S18, result file in JSON.

There is no option for held-out seeds: the held-out list in ``data/seeds.json`` is never read here
(AGENTS.md section 9). Counts are episodes, not ticks. Unavoidable cases are in the totals and are
also listed and subtracted separately. Run it in the cloud (``.github/workflows/e1.yml``): the full
set is 90 runs per configuration and the 30 robot scenarios are slow on a laptop.
"""

import argparse
import dataclasses
import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from waggle.control.params import (
    DEFAULT_CONTROL_PARAMS,
    DEFAULT_CPA_PARAMS,
    DEFAULT_OCCLUSION_PARAMS,
    DEFAULT_PERCEPTION_PARAMS,
)
from waggle.experiments import e1_stats
from waggle.experiments.e1_config import BY_NAME, CONFIGS, FALSE_STOP_GAP_M, E1Config
from waggle.experiments.e1_rig import ControlRig, streams_for
from waggle.sim import robots, scenarios
from waggle.sim.params import DT

SEEDS_PATH = Path("data/seeds.json")
# Records and documents are JSON trees of mixed values, so dict[str, Any] is used for them.
COUNT_KEYS = ("human_collisions", "robot_collisions", "separation_violations", "near_misses")


@dataclass(frozen=True)
class RunSpec:
    """One run: a configuration name, a scenario, a seed and an optional shortened length."""

    config: str
    scenario: str
    seed: int
    ticks: int | None = None


def run_one(spec: RunSpec) -> dict[str, Any]:
    """Run one scenario with one configuration and return its record."""
    config = BY_NAME[spec.config]
    scenario = scenarios.generate(spec.scenario, spec.seed)
    sim, det = scenarios.build_engine(scenario, streams_for(config, len(scenario.robots)))
    rig: ControlRig | None = None
    if config.controlled:
        fleet = robots.RobotFleet(
            [r.kind for r in scenario.robots], load_raised=[r.load_raised for r in scenario.robots]
        )
        rig = ControlRig(config, fleet, scenarios.load_map(scenario.map_name))
        sim.systems.insert(1, rig.system())
    total = scenario.duration_ticks if spec.ticks is None else spec.ticks
    for _ in range(total):
        sim.step()
    tasks = int(np.asarray(sim.state.arrays["script_tasks"], dtype=np.int64).sum())
    record: dict[str, Any] = {
        "scenario": spec.scenario,
        "seed": spec.seed,
        "robots": len(scenario.robots),
        "ticks": total,
        "unavoidable_at_spawn": scenario.unavoidable_at_spawn,
        "tasks_completed": tasks,
        "counts": det.counts(sim.state),
        "final_hash": sim.state_hash(),
        "stop_episodes": {},
        "false_stops": 0,
        "latency": e1_stats.latency_summary([]),
    }
    if rig is not None:
        record["stop_episodes"] = dict(sorted(rig.tally.stop_episodes.items()))
        record["false_stops"] = rig.tally.false_stops
        record["latency"] = e1_stats.latency_summary(rig.tally.latency_us)
    return record


def run_set(specs: Sequence[RunSpec], workers: int = 1) -> list[dict[str, Any]]:
    """Run the specs, in order. Each run is a pure function of its spec, so workers do not
    change the results."""
    if workers <= 1 or len(specs) <= 1:
        return [run_one(spec) for spec in specs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_one, specs))


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        out = subprocess.run(
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _totals(
    runs: Sequence[dict[str, Any]], keep: Callable[[dict[str, Any]], bool] = lambda r: True
) -> dict[str, int]:
    return {k: sum(r["counts"][k] for r in runs if keep(r)) for k in COUNT_KEYS}


def _proportion(runs: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    hits = sum(1 for r in runs if r["counts"][key] > 0)
    low, high = e1_stats.wilson(hits, len(runs))
    return {"runs_with": hits, "runs": len(runs), "wilson95_low": low, "wilson95_high": high}


def _latency(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    parts = [r["latency"] for r in runs if r["latency"]["n"] > 0]
    if not parts:
        return {"calls": 0}
    return {
        "calls": sum(p["n"] for p in parts),
        "median_of_run_medians_us": float(np.median([p["median_us"] for p in parts])),
        "max_of_run_p99_us": max(p["p99_us"] for p in parts),
        "max_us": max(p["max_us"] for p in parts),
        "note": "code latency of control_step on the machine named in platform, "
        "not a real-time bound",
    }


def _stops(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_reason: dict[str, int] = {}
    for r in runs:
        for reason, count in r["stop_episodes"].items():
            by_reason[reason] = by_reason.get(reason, 0) + count
    return {
        "episodes": sum(by_reason.values()),
        "by_reason": dict(sorted(by_reason.items())),
        "false_stops": sum(r["false_stops"] for r in runs),
        "false_stop_gap_m": FALSE_STOP_GAP_M,
    }


def assemble(config: E1Config, runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build the result document of one configuration from its run records."""
    hours = sum(r["ticks"] for r in runs) * DT / 3600.0
    tasks = sum(r["tasks_completed"] for r in runs)
    failing = [
        {"scenario": r["scenario"], "seed": r["seed"]}
        for r in runs
        if r["counts"]["human_collisions"] or r["counts"]["robot_collisions"]
    ]
    return {
        "experiment": "e1",
        "configuration": config.name,
        "configuration_detail": dataclasses.asdict(config) | {"mode": config.mode.value},
        "seed_set": "dev",
        "commit": _commit(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "dt": DT,
        "definitions": {
            "collision": "Contact of a robot footprint with a human disc or a robot footprint, "
            "closed sets, counted as episodes.",
            "separation_violation": f"Gap to a human below {scenarios.SEPARATION_MARGIN} m, "
            "counted as episodes. A collision is also a violation.",
            "near_miss": f"No contact and a gap below {scenarios.NEAR_MISS_MARGIN} m, "
            "counted as episodes.",
            "stop_episode": "A tick where the requested speed is above zero and the limited speed "
            "is zero, after a tick where it was not. Counted per robot.",
            "false_stop": f"A stop episode that starts while the centre distance to every human "
            f"minus the human radius is above {FALSE_STOP_GAP_M} m.",
        },
        "counts": _totals(runs),
        "counts_excluding_unavoidable": _totals(runs, lambda r: not r["unavoidable_at_spawn"]),
        "proportions": {
            "human_collision": _proportion(runs, "human_collisions"),
            "robot_collision": _proportion(runs, "robot_collisions"),
            "separation_violation": _proportion(runs, "separation_violations"),
        },
        "unavoidable_cases": [
            {"scenario": r["scenario"], "seed": r["seed"]}
            for r in runs
            if r["unavoidable_at_spawn"]
        ],
        "tasks_completed": tasks,
        "tasks_per_simulated_hour": tasks / hours if hours > 0 else 0.0,
        "stops": _stops(runs),
        "latency": _latency(runs),
        "failing_seeds": sorted(failing, key=lambda f: (f["scenario"], f["seed"])),
        "assumptions": {
            "control": dataclasses.asdict(DEFAULT_CONTROL_PARAMS),
            "perception": dataclasses.asdict(DEFAULT_PERCEPTION_PARAMS),
            "occlusion": dataclasses.asdict(DEFAULT_OCCLUSION_PARAMS),
            "cpa": dataclasses.asdict(DEFAULT_CPA_PARAMS),
        },
        "runs": list(runs),
        "model_ids": {},
        "prompt_versions": {},
        "notes": "Development seeds only. Every control value is an assumption, not calibrated. "
        "Reflex limits (watchdog, geofence, e-stop) are off in E1. Throughput is waypoints "
        "reached per simulated hour.",
    }


def dev_pairs(scenario_ids: Sequence[str]) -> list[tuple[str, int]]:
    """The (scenario, seed) pairs of the development set. The held-out list is not read."""
    dev = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["dev"]
    return [(sid, int(seed)) for sid in scenario_ids for seed in dev[sid]]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the chosen configurations on the development seeds and write one file each."""
    parser = argparse.ArgumentParser(prog="experiments-dev", description=__doc__)
    parser.add_argument("--config", nargs="+", default=[c.name for c in CONFIGS])
    parser.add_argument("--scenarios", nargs="+", default=list(scenarios.SCENARIO_IDS))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=None, help="shorten every run (for tests)")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    unknown = [name for name in args.config if name not in BY_NAME]
    if unknown:
        print(f"experiments-dev: unknown configuration {unknown}", file=sys.stderr)
        return 2
    out_dir = args.results_dir / "e1" / "dev"
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs = dev_pairs(args.scenarios)
    for name in args.config:
        specs = [RunSpec(name, sid, seed, args.ticks) for sid, seed in pairs]
        document = assemble(BY_NAME[name], run_set(specs, args.workers))
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"{name}_{stamp}.json"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"experiments-dev: wrote {path} ({len(specs)} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
