"""E1 no-control baseline on development seeds (Phase 1).

Runs S01 to S18 with the waypoint driver only (no fast layer, no envelope, no e-stop) on the
5 development seeds of each scenario and writes ``results/e1/dev/<run_id>.json``. There is no
option to run held-out seeds: the held-out file is never read here and nothing is written
under ``heldout/``. Counts are episodes, not ticks. Unavoidable cases are counted in the
totals and also listed and subtracted separately, never hidden.
"""

import argparse
import json
import platform
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from waggle.sim import scenarios
from waggle.sim.params import DT

COUNT_KEYS = ("human_collisions", "robot_collisions", "separation_violations", "near_misses")
SEEDS_PATH = Path("data/seeds.json")


def default_scenarios() -> list[str]:
    """The scenarios of Phase 1."""
    return list(scenarios.SCENARIO_IDS)


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _definitions() -> dict[str, str]:
    return {
        "collision": (
            "Contact between a robot footprint and a human disc or another robot footprint, "
            "closed sets (an exact touch is contact), over the swept step. Counted as episodes."
        ),
        "separation_violation": (
            f"Gap between a robot and a human disc below {scenarios.SEPARATION_MARGIN} m, "
            "strictly below, counted as episodes. A collision is also a violation."
        ),
        "near_miss": (
            f"No contact and a gap below {scenarios.NEAR_MISS_MARGIN} m, counted as episodes."
        ),
    }


def _total(runs: Sequence[dict[str, Any]], keep: Any = lambda r: True) -> dict[str, int]:
    return {k: sum(r["counts"][k] for r in runs if keep(r)) for k in COUNT_KEYS}


def assemble(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build the result document from per-run records."""
    hours = sum(r["ticks"] for r in runs) * DT / 3600.0
    tasks = sum(r["tasks_completed"] for r in runs)
    failing = sorted(
        (
            {"scenario": r["scenario"], "seed": r["seed"]}
            for r in runs
            if r["counts"]["human_collisions"] or r["counts"]["robot_collisions"]
        ),
        key=lambda f: (f["scenario"], f["seed"]),
    )
    return {
        "experiment": "e1",
        "configuration": "no_control",
        "seed_set": "dev",
        "commit": _commit(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "dt": DT,
        "definitions": _definitions(),
        "counts": _total(runs),
        "counts_excluding_unavoidable": _total(runs, lambda r: not r["unavoidable_at_spawn"]),
        "unavoidable_cases": [
            {"scenario": r["scenario"], "seed": r["seed"]}
            for r in runs
            if r["unavoidable_at_spawn"]
        ],
        "tasks_per_simulated_hour": tasks / hours if hours > 0 else 0.0,
        "failing_seeds": failing,
        "runs": list(runs),
        "model_ids": {},
        "prompt_versions": {},
        "notes": (
            "No control: the waypoint driver has no safety logic. Development seeds only. "
            "Task counts are waypoints reached. Figures are from this machine's run of the "
            "simulator; the published results come from the cloud run."
        ),
    }


def run_baseline(pairs: Sequence[tuple[str, int]], ticks: int | None = None) -> dict[str, Any]:
    """Run each (scenario, seed) pair with no control and return the result document."""
    records: list[dict[str, Any]] = []
    for sid, seed in pairs:
        scenario = scenarios.generate(sid, seed)
        record = scenarios.run_scenario(scenario, ticks=ticks)
        records.append(
            {
                "scenario": sid,
                "seed": seed,
                "ticks": record.ticks,
                "unavoidable_at_spawn": scenario.unavoidable_at_spawn,
                "tasks_completed": record.tasks_completed,
                "counts": record.counts,
                "final_hash": record.final_hash,
            }
        )
    return assemble(records)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the baseline on the development seeds and write the result file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--scenarios", nargs="+", default=default_scenarios())
    parser.add_argument("--ticks", type=int, default=None, help="shorten every run (for tests)")
    args = parser.parse_args(argv)
    dev = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["dev"]
    pairs = [(sid, int(seed)) for sid in args.scenarios for seed in dev[sid]]
    document = run_baseline(pairs, args.ticks)
    out_dir = Path(args.results_dir) / "e1" / "dev"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("no_control_%Y%m%dT%H%M%SZ")
    path = out_dir / f"{run_id}.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"e1_baseline: wrote {path} ({len(pairs)} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
