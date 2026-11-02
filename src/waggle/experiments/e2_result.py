"""E2 result records: one record per run, a summary with Wilson intervals, an exclusive file write.

Pure apart from ``write_result``. A run whose log the oracle could not judge is an undecided
record: it is counted apart and never enters a proportion as a pass. Proportions are over decided
runs, with the raw counts and the failing seeds next to the Wilson 95 percent interval
(AGENTS.md 9.5). A summary of fewer than 30 decided runs is marked small.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from waggle.experiments.e1_stats import wilson
from waggle.experiments.e2_faults import FaultParams, FaultSchedule
from waggle.experiments.e2_oracle import TaskReport

SMALL_SAMPLE = 30
SEED_SETS = frozenset({"development", "held_out"})
_METRICS = ("double_assignments", "stale_writes_accepted", "expired_writes_accepted", "tasks_stuck")
_ENVIRONMENT_KEYS = ("commit", "python", "platform", "postgres_image", "schema_revision")
_NOTE = (
    "Repeats are repeats, not independent samples. The seed fixes the fault schedule, not the "
    "operating system scheduling, so two runs with the same seed can differ."
)


class ResultExistsError(FileExistsError):
    """A result file for this configuration already exists and is not overwritten."""


def run_record(
    *,
    arm: str,
    seed: int,
    schedule: FaultSchedule,
    report: TaskReport,
    restarts: int,
    wall_s: float,
    ended_by: str,
) -> dict[str, object]:
    """The record of one run the oracle could judge."""
    return {
        "arm": arm,
        "seed": seed,
        "undecided": False,
        "undecided_reason": None,
        "schedule": schedule.summary(),
        "restarts": restarts,
        "wall_s": round(wall_s, 3),
        "ended_by": ended_by,
        "report": {
            "double_assignments": report.double_assignments,
            "stale_writes_accepted": report.stale_writes_accepted,
            "expired_writes_accepted": report.expired_writes_accepted,
            "tasks_recovered": report.tasks_recovered,
            "recovery_ticks_max": max(report.recovery_ticks, default=0),
            "tasks_stuck": len(report.tasks_stuck),
            "stuck_ids": list(report.tasks_stuck),
            "tasks_done": report.tasks_done,
            "tasks_total": report.tasks_total,
        },
    }


def undecided_record(
    *,
    arm: str,
    seed: int,
    schedule: FaultSchedule,
    reason: str,
    restarts: int,
    wall_s: float,
) -> dict[str, object]:
    """The record of a run whose log could not be judged; it carries no counts."""
    return {
        "arm": arm,
        "seed": seed,
        "undecided": True,
        "undecided_reason": reason,
        "schedule": schedule.summary(),
        "restarts": restarts,
        "wall_s": round(wall_s, 3),
        "ended_by": "undecided",
        "report": None,
    }


def _metric_summary(decided: Sequence[Mapping[str, object]], name: str) -> dict[str, object]:
    counts = []
    for record in decided:
        report = record["report"]
        if not isinstance(report, dict):
            raise ValueError("a decided record needs a report")
        counts.append((int(record["seed"]), int(report[name])))  # type: ignore[call-overload]
    failing = [seed for seed, value in counts if value > 0]
    low, high = wilson(len(failing), len(counts))
    return {
        "runs_with_event": len(failing),
        "events": sum(value for _, value in counts),
        "wilson95": [low, high],
        "failing_seeds": failing,
    }


def aggregate(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Counts, Wilson intervals over decided runs and the failing seeds of one configuration."""
    decided = [record for record in records if not record["undecided"]]
    summary: dict[str, object] = {
        "runs": len(records),
        "decided_runs": len(decided),
        "undecided_runs": len(records) - len(decided),
        "undecided_seeds": [record["seed"] for record in records if record["undecided"]],
        "small_sample": len(decided) < SMALL_SAMPLE,
        "restarts_total": sum(int(record["restarts"]) for record in records),  # type: ignore[call-overload]
    }
    for name in _METRICS:
        summary[name] = _metric_summary(decided, name)
    return summary


def build_result_file(
    *,
    configuration: str,
    seed_set: str,
    params: FaultParams,
    runs: Sequence[Mapping[str, object]],
    environment: Mapping[str, object],
) -> dict[str, object]:
    """The contents of one result file; it records the conditions and zero model calls."""
    if seed_set not in SEED_SETS:
        raise ValueError("seed_set must be development or held_out")
    if any(run["arm"] != configuration for run in runs):
        raise ValueError("every run must belong to the configuration of the file")
    missing = [key for key in _ENVIRONMENT_KEYS if key not in environment]
    if missing:
        raise ValueError("environment is missing: " + ", ".join(missing))
    return {
        "configuration": configuration,
        "seed_set": seed_set,
        "seeds": [run["seed"] for run in runs],
        "workers": params.workers,
        "tasks": params.tasks,
        "horizon": params.horizon,
        "fault_parameters": asdict(params),
        **{key: environment[key] for key in _ENVIRONMENT_KEYS},
        "llm_calls": 0,
        "summary": aggregate(runs),
        "runs": list(runs),
        "note": _NOTE,
    }


def write_result(path: Path, data: Mapping[str, object]) -> None:
    """Create the file with exclusive creation; an existing file is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as error:
        raise ResultExistsError(str(path)) from error
