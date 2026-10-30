"""Measure ticks per second of the simulator loop (code speed on this machine).

Not part of waggle.sim: it reads a wall clock, which the determinism scan forbids there.
Writes results/e8/dev/<run_id>.json. The figures are code speed on this machine and are never
a real-time guarantee on hardware.
"""

import argparse
import json
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from waggle.sim import engine, params, robots, scenarios, sensors, state

LABEL = "code speed on this machine, not a real-time guarantee on hardware"


def _walk(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
    pos = sim.arrays["pos"]
    for i in range(pos.shape[0]):
        pos[i] += rngs[f"humans/{i}"].normal(0.0, 0.1, size=2)


def _make(entities: int) -> engine.Engine:
    arrays: dict[str, state.Array] = {"pos": np.zeros((entities, 2))}
    return engine.Engine(1, arrays, [_walk], {"humans": entities})


def _rate(ticks: int, seconds: float) -> float:
    return ticks / seconds if seconds > 0 else float("inf")


def measure(ticks: int, rollout_ticks: int, forks: int, entities: int) -> dict[str, Any]:
    """Time the empty loop and fork rollouts. Raises ValueError on a non-positive size."""
    if min(ticks, rollout_ticks, forks, entities) < 1:
        raise ValueError("ticks, rollout_ticks, forks and entities must be at least 1")
    empty = engine.Engine(1, {"pos": np.zeros((1, 2))}, [], {})
    start = time.perf_counter()
    empty.run(ticks)
    empty_seconds = time.perf_counter() - start

    base = _make(entities)
    base.run(10)
    start = time.perf_counter()
    for _ in range(forks):
        base.fork().run(rollout_ticks)
    fork_seconds = time.perf_counter() - start
    return {
        "experiment": "e8",
        "seed_set": "dev",
        "label": LABEL,
        "commit": _commit(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "dt": params.DT,
        "entities": entities,
        "empty_loop": {"ticks": ticks, "ticks_per_second": _rate(ticks, empty_seconds)},
        "fork_rollout": {
            "forks": forks,
            "ticks_per_fork": rollout_ticks,
            "ticks_per_second": _rate(forks * rollout_ticks, fork_seconds),
            "note": "toy random-walk system; the 10-robot rollout with lidar is measured in B8",
        },
    }


def _lidar_system(sim_robots: int) -> engine.System:
    """Lidar for every robot on the ticks where it is due (reads ground truth)."""
    config = sensors.LidarConfig()
    counter = {"scans": 0}

    def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        if not sensors.lidar_due(sim.tick):
            return
        pose = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        people = np.asarray(sim.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
        discs = np.hstack([people, np.full((len(people), 1), params.HUMAN_RADIUS)])
        static = np.asarray(_STATIC["segments"], dtype=np.float64)
        for i in range(sim_robots):
            others = [
                robots.footprint_corners(_STATIC["params"][j], *pose[j])  # type: ignore[index]
                for j in range(sim_robots)
                if j != i
            ]
            boxes = np.array(others).reshape(-1, 4, 2)
            sensors.lidar_scan(static, discs, boxes, pose[i], config, rngs[f"lidar/{i}"])
            counter["scans"] += 1

    step.counter = counter  # type: ignore[attr-defined]
    return step


_STATIC: dict[str, object] = {}


def measure_scenario_rollout(scenario_id: str, seed: int, ticks: int, forks: int) -> dict[str, Any]:
    """Time fork rollouts of a scenario with the lidar of every robot included."""
    if min(ticks, forks) < 1:
        raise ValueError("ticks and forks must be at least 1")
    scenario = scenarios.generate(scenario_id, seed)
    n = len(scenario.robots)
    sim, _ = scenarios.build_engine(scenario, {"lidar": n})
    _STATIC["segments"] = sensors.static_segments(scenarios.load_map(scenario.map_name))
    _STATIC["params"] = [params.ROBOT_PARAMS[r.kind] for r in scenario.robots]
    lidar = _lidar_system(n)
    sim.systems.append(lidar)
    sim.run(10)
    scans_before = lidar.counter["scans"]  # type: ignore[attr-defined]
    start = time.perf_counter()
    for _ in range(forks):
        sim.fork().run(ticks)
    seconds = time.perf_counter() - start
    scans = (lidar.counter["scans"] - scans_before) // forks  # type: ignore[attr-defined]
    return {
        "label": LABEL,
        "scenario": scenario_id,
        "seed": seed,
        "robots": n,
        "humans": len(scenario.humans),
        "forks": forks,
        "ticks_per_fork": ticks,
        "lidar_scans_per_rollout": scans,
        "ticks_per_second": _rate(forks * ticks, seconds),
        "seconds_per_rollout": seconds / forks,
    }


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the measurement and write the result file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--ticks", type=int, default=200_000)
    parser.add_argument("--rollout-ticks", type=int, default=1_800)
    parser.add_argument("--forks", type=int, default=5)
    parser.add_argument("--entities", type=int, default=10)
    parser.add_argument("--scenario-ticks", type=int, default=1_800)
    parser.add_argument("--scenario-forks", type=int, default=3)
    args = parser.parse_args(argv)
    data = measure(args.ticks, args.rollout_ticks, args.forks, args.entities)
    data["scenario_rollout"] = measure_scenario_rollout(
        "S14", 1, args.scenario_ticks, min(args.scenario_forks, args.forks) or 1
    )
    out_dir = Path(args.results_dir) / "e8" / "dev"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("sim_speed_%Y%m%dT%H%M%SZ")
    (out_dir / f"{run_id}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
