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

from waggle.sim import engine, params, state

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
    args = parser.parse_args(argv)
    data = measure(args.ticks, args.rollout_ticks, args.forks, args.entities)
    out_dir = Path(args.results_dir) / "e8" / "dev"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("sim_speed_%Y%m%dT%H%M%SZ")
    (out_dir / f"{run_id}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
