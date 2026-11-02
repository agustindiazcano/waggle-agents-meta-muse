"""Cloud-only: a small chaos run with real worker processes, planned kills and both arms."""

import json
import os
from pathlib import Path

import pytest

from waggle.db.connection import Database
from waggle.experiments.e2_chaos import ChaosConfig, run_once
from waggle.experiments.e2_faults import FaultParams
from waggle.experiments.e2_sweep import main

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


def test_the_sweep_writes_one_result_file_per_arm(tmp_path: Path) -> None:
    environ = {
        **os.environ,
        "E2_POSTGRES_IMAGE": "pgvector/pgvector:pg16",
        "GITHUB_SHA": os.environ.get("GITHUB_SHA", "local"),
    }
    argv = ["--seeds", "1", "--tasks", "8", "--workers", "2", "--horizon", "8000"]
    assert main([*argv, "--out", str(tmp_path)], environ) == 0
    files = sorted(tmp_path.glob("chaos_*.json"))
    assert [file.name.split("_")[1] for file in files] == ["baseline", "fenced"]
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        assert data["llm_calls"] == 0
        assert data["seed_set"] == "development"
        assert data["summary"]["runs"] == 1
    fenced = json.loads(files[1].read_text(encoding="utf-8"))
    assert fenced["summary"]["undecided_runs"] == 0
    assert fenced["summary"]["stale_writes_accepted"]["events"] == 0
