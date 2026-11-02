"""Cloud-only: a small chaos run with real worker processes, planned kills and both arms."""

import os

import pytest

from waggle.db.connection import Database
from waggle.experiments.e2_chaos import ChaosConfig, run_once
from waggle.experiments.e2_faults import FaultParams

pytestmark = pytest.mark.heavy

SMALL = FaultParams(
    workers=2,
    tasks=12,
    horizon=15000,
    kill_rate=0.4,
    max_kills_per_task=2,
    clock_jumps_per_worker=1,
    worker_iterations=20,
    jump_ticks_min=100,
    jump_ticks_max=300,
    replay_rate=0.3,
    replay_lag_max=200,
    delay_rate=0.1,
    delay_ms_max=30,
)


def _root() -> Database:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("PostgreSQL integration tests are cloud-only")
    return Database.from_environ(os.environ)


def _report(record: dict[str, object]) -> dict[str, int]:
    report = record["report"]
    assert isinstance(report, dict)
    return report


def test_the_fenced_arm_survives_planned_kills_with_no_violation() -> None:
    record = run_once(_root(), ChaosConfig(arm="fenced", seed=1, params=SMALL))
    assert record["undecided"] is False, record["undecided_reason"]
    report = _report(record)
    assert report["tasks_total"] == SMALL.tasks
    assert report["stale_writes_accepted"] == 0
    assert report["double_assignments"] == 0
    restarts = record["restarts"]
    assert isinstance(restarts, int) and restarts >= 1


def test_the_baseline_arm_runs_to_a_judged_record() -> None:
    record = run_once(_root(), ChaosConfig(arm="baseline", seed=1, params=SMALL))
    assert record["undecided"] is False, record["undecided_reason"]
    assert _report(record)["tasks_total"] == SMALL.tasks
