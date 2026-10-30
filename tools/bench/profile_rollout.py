"""Profile one scenario rollout with cProfile and write the breakdown per function.

Standard library only. Writes results/e8/dev/profile_<label>_<run_id>.json. The figures are
code speed on this machine (profiling adds overhead of its own), never a real-time guarantee on
hardware. Run it before and after an optimization with different labels to compare.
"""

import argparse
import cProfile
import json
import platform
import pstats
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import sim_speed

LABEL = "code speed on this machine, profiler overhead included, not a real-time guarantee"
COMPONENTS = {
    "detector": ("detector.py", "hullgap.py"),
    "lidar": ("sensors.py", "fastlidar.py"),
    "core": ("robots.py", "humans.py", "scripted.py", "engine.py", "state.py"),
}


def _component(filename: str) -> str:
    name = Path(filename).name
    for component, files in COMPONENTS.items():
        if name in files:
            return component
    return "other"


def summarize(stats: pstats.Stats, top: int) -> dict[str, Any]:
    """Top functions by own time, and own time summed by component."""
    rows: list[dict[str, Any]] = []
    by_component: dict[str, float] = {}
    for (filename, line, name), (_cc, calls, own, cumulative, _callers) in stats.stats.items():  # type: ignore[attr-defined]
        component = _component(filename)
        by_component[component] = by_component.get(component, 0.0) + own
        rows.append(
            {
                "function": f"{Path(filename).name}:{line}({name})",
                "component": component,
                "calls": calls,
                "own_seconds": own,
                "cumulative_seconds": cumulative,
            }
        )
    rows.sort(key=lambda r: -r["own_seconds"])
    return {
        "top_functions": rows[:top],
        "own_seconds_by_component": dict(sorted(by_component.items())),
    }


def profile(scenario_id: str, seed: int, ticks: int, lidar_mode: str, top: int) -> dict[str, Any]:
    """Profile one rollout and return the breakdown."""
    kwargs: dict[str, Any] = {} if lidar_mode == "exact" else {"lidar_mode": lidar_mode}
    profiler = cProfile.Profile()
    profiler.enable()
    measured = sim_speed.measure_scenario_rollout(scenario_id, seed, ticks, 1, **kwargs)
    profiler.disable()
    stats = pstats.Stats(profiler)
    return {
        "scenario": scenario_id,
        "seed": seed,
        "ticks": ticks,
        "lidar_mode": lidar_mode,
        "seconds_per_rollout_unprofiled_clock": measured["seconds_per_rollout"],
        "profiled_total_seconds": stats.total_tt,  # type: ignore[attr-defined]
        **summarize(stats, top),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Profile a rollout and write the result file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--label", required=True, help="for example before or after")
    parser.add_argument("--scenario", default="S14")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=1_800)
    parser.add_argument("--lidar-mode", choices=("exact", "fast"), default="exact")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args(argv)
    data = {
        "experiment": "e8",
        "kind": "profile",
        "seed_set": "dev",
        "label": LABEL,
        "run_label": args.label,
        "commit": sim_speed._commit(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        **profile(args.scenario, args.seed, args.ticks, args.lidar_mode, args.top),
    }
    out_dir = Path(args.results_dir) / "e8" / "dev"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"profile_{args.label}_{args.lidar_mode}_{run_id}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
