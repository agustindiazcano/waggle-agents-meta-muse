"""Cloud-only paired S03 admission comparison, a component of E2, not full chaos.

Every pair uses identical staging, routes, control and sensor streams. Progress timeouts
are reported as stalls, never as cycle-proven deadlocks. No database or provider is used.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from waggle.experiments.corridor_admission import build_s03_admission
from waggle.experiments.e1_run import dev_pairs
from waggle.experiments.e1_stats import wilson

HORIZON_TICKS = 3200
STALL_TICKS = 400
PROGRESS_M = 0.05


def _integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True)
class RunResult:
    """Raw measurements from one bounded simulator run."""

    seed: int
    admission_enabled: bool
    ticks: int
    robot_count: int
    completed_routes: int
    completed_waypoints: int
    double_occupancy_ticks: int
    robot_collisions: int
    stalled_unfinished_robots: int
    fault_occupied_ticks: int | None
    final_hash: str

    def __post_init__(self) -> None:
        _integer(self.seed, "seed")
        _integer(self.ticks, "ticks", 1)
        _integer(self.robot_count, "robot_count", 1)
        for name in (
            "completed_routes",
            "completed_waypoints",
            "double_occupancy_ticks",
            "robot_collisions",
            "stalled_unfinished_robots",
        ):
            _integer(getattr(self, name), name)
        if type(self.admission_enabled) is not bool:
            raise ValueError("admission_enabled must be a boolean")
        if (
            self.completed_routes > self.robot_count
            or self.stalled_unfinished_robots > self.robot_count
        ):
            raise ValueError("robot counts exceed the fleet")
        if self.double_occupancy_ticks > self.ticks:
            raise ValueError("occupancy ticks exceed the horizon")
        if self.fault_occupied_ticks is not None:
            _integer(self.fault_occupied_ticks, "fault_occupied_ticks")
        if not self.final_hash:
            raise ValueError("final_hash is required")


@dataclass(frozen=True)
class Proportion:
    """Raw run count and Wilson 95 percent interval; robot-ticks are not trials."""

    successes: int
    total: int
    low: float
    high: float


@dataclass(frozen=True)
class Summary:
    """A single configuration, with failing seeds and an explicit small-sample flag."""

    admission_enabled: bool
    completed_runs: Proportion
    occupancy_violation_runs: Proportion
    robot_collision_runs: Proportion
    stalled_runs: Proportion
    double_occupancy_ticks: int
    robot_collisions: int
    failing_seeds: tuple[int, ...]
    small_sample: bool


def summarize(runs: tuple[RunResult, ...]) -> Summary:
    """Summarize unique seeds of one configuration, rejecting empty or mixed inputs."""
    if not runs or len({r.seed for r in runs}) != len(runs):
        raise ValueError("results require nonempty unique seeds")
    if len({r.admission_enabled for r in runs}) != 1:
        raise ValueError("cannot mix configurations in a summary")

    def proportion(count: int) -> Proportion:
        low, high = wilson(count, len(runs))
        return Proportion(count, len(runs), low, high)

    return Summary(
        runs[0].admission_enabled,
        proportion(sum(r.completed_routes == r.robot_count for r in runs)),
        proportion(sum(r.double_occupancy_ticks > 0 for r in runs)),
        proportion(sum(r.robot_collisions > 0 for r in runs)),
        proportion(sum(r.stalled_unfinished_robots > 0 for r in runs)),
        sum(r.double_occupancy_ticks for r in runs),
        sum(r.robot_collisions for r in runs),
        tuple(
            r.seed
            for r in runs
            if r.completed_routes < r.robot_count or r.double_occupancy_ticks or r.robot_collisions
        ),
        len(runs) < 30,
    )


def run_case(
    seed: int,
    admission_enabled: bool,
    *,
    ticks: int = HORIZON_TICKS,
    stall_ticks: int = STALL_TICKS,
) -> RunResult:
    """Measure one case; callers run full sweeps only in the cloud workflow."""
    _integer(ticks, "ticks", 1)
    _integer(stall_ticks, "stall_ticks", 1)
    sim, admission, det = build_s03_admission(seed, admission_enabled=admission_enabled)
    anchors = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)[:, :2].copy()
    last_progress = np.zeros(len(anchors), dtype=np.int64)
    last_wp = np.asarray(sim.state.arrays["script_wp"], dtype=np.int64).copy()
    double_ticks = fault_ticks = 0
    for _ in range(ticks):
        sim.step()
        observations = admission.occupancy(sim.state)
        if any(o.occupants is None for o in observations):
            raise RuntimeError("unknown occupancy cannot be scored as clear")
        double_ticks += int(any(len(o.occupants or ()) > 1 for o in observations))
        fault_ticks += int(bool(np.any(sim.state.arrays["admission_fault"])))
        xy = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)[:, :2]
        wp = np.asarray(sim.state.arrays["script_wp"], dtype=np.int64)
        moved = (np.linalg.norm(xy - anchors, axis=1) >= PROGRESS_M) | (wp != last_wp)
        last_progress[moved] = sim.state.tick
        anchors[moved] = xy[moved]
        last_wp = wp.copy()
    unfinished = wp < np.array(admission.route_lengths)
    stalled = unfinished & (sim.state.tick - last_progress >= stall_ticks)
    return RunResult(
        seed,
        admission_enabled,
        ticks,
        admission.fleet.count,
        int((~unfinished).sum()),
        int(np.asarray(sim.state.arrays["script_tasks"]).sum()),
        double_ticks,
        det.counts(sim.state)["robot_collisions"],
        int(stalled.sum()),
        fault_ticks if admission_enabled else None,
        sim.state_hash(),
    )


def run_comparison(seeds: tuple[int, ...]) -> tuple[RunResult, ...]:
    """Run both configurations over exactly the same ordered development seeds."""
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("development seeds must be nonempty and unique")
    for seed in seeds:
        _integer(seed, "seed")
    return tuple(run_case(seed, enabled) for enabled in (False, True) for seed in seeds)


def write_report(report: Mapping[str, object], path: Path) -> None:
    """Write valid JSON exclusively; existing results are never overwritten."""
    payload = json.dumps(dict(report), indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        target.write(payload)


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for experiment provenance")
    result = subprocess.run(
        [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=15
    )
    commit = result.stdout.strip()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise RuntimeError("invalid commit provenance")
    return commit


def main(argv: Sequence[str] | None = None) -> int:
    """Write the development-only S03 component report from GitHub Actions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("E2 sweeps are cloud-only; use the manual GitHub workflow")
    commit = _commit()
    seeds = tuple(seed for _, seed in dev_pairs(("S03",)))
    runs = run_comparison(seeds)
    summaries = tuple(
        summarize(tuple(r for r in runs if r.admission_enabled == enabled))
        for enabled in (False, True)
    )
    created = datetime.now(UTC)
    report: dict[str, object] = {
        "schema_version": 1,
        "experiment": "E2",
        "scope": "simulator admission component only; not the database chaos protocol",
        "scenario_variant": "s03-admission-v1",
        "commit": commit,
        "date": created.isoformat(),
        "seed_set": "dev",
        "seeds": seeds,
        "configurations": ("admission_disabled", "admission_enabled"),
        "fast_layer": "envelope_oracle",
        "horizon_ticks": HORIZON_TICKS,
        "lease_ticks": 4000,
        "progress_distance_m": PROGRESS_M,
        "stall_ticks": STALL_TICKS,
        "stall_definition": (
            "unfinished robot with no 0.05 m displacement or waypoint change in the final "
            "400 ticks; includes planned waits, not proof of deadlock"
        ),
        "occupancy_definition": (
            "closed footprint bounding boxes against lane_1 after each dynamics tick; "
            "discrete occupancy, not continuous swept zone occupancy"
        ),
        "not_measured": (
            "cycle-proven deadlocks",
            "S13-S18 density",
            "double assignments",
            "stale-token database writes",
            "worker recovery",
            "database delays",
            "handoff chaos",
            "full control-rig snapshot replay",
        ),
        "model_ids": (),
        "prompt_versions": (),
        "llm_calls": 0,
        "sampling_note": (
            "fixed geometry and routes; seed variation is sensor and odometry noise, "
            "not independent warehouse layouts"
        ),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "runs": [asdict(run) for run in runs],
        "summaries": [asdict(summary) for summary in summaries],
    }
    name = f"s03_admission_{commit[:12]}_{created.strftime('%Y%m%dT%H%M%SZ')}.json"
    write_report(report, Path("results/e2/dev") / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
