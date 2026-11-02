"""E2 result records: per-run records, aggregation with Wilson intervals, exclusive file writes."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e1_stats import wilson
from waggle.experiments.e2_faults import FaultParams, build_schedule
from waggle.experiments.e2_oracle import TaskReport
from waggle.experiments.e2_result import (
    ResultExistsError,
    aggregate,
    build_result_file,
    run_record,
    undecided_record,
    write_result,
)

PARAMS = FaultParams()
ENVIRONMENT = {
    "commit": "abc1234",
    "python": "3.12.0",
    "platform": "linux",
    "postgres_image": "pgvector/pgvector:pg16",
    "schema_revision": 9,
}


def _report(stale: int = 0, double: int = 0, expired: int = 0, stuck: int = 0) -> TaskReport:
    return TaskReport(
        double_assignments=double,
        stale_writes_accepted=stale,
        expired_writes_accepted=expired,
        tasks_recovered=3,
        recovery_ticks=(10, 20),
        tasks_stuck=tuple(f"t{i:06d}" for i in range(stuck)),
        tasks_done=497,
        tasks_total=500,
    )


def _record(seed: int, arm: str = "fenced", **counts: int) -> dict[str, object]:
    return run_record(
        arm=arm,
        seed=seed,
        schedule=build_schedule(seed, PARAMS),
        report=_report(**counts),
        restarts=12,
        wall_s=31.5,
        ended_by="all_terminal",
    )


def test_run_record_is_json_serialisable_and_keeps_the_counts() -> None:
    record = _record(1, stale=2)
    assert json.loads(json.dumps(record)) == record
    assert record["arm"] == "fenced"
    assert record["undecided"] is False
    report = record["report"]
    assert isinstance(report, dict)
    assert report["stale_writes_accepted"] == 2
    assert report["tasks_stuck"] == 0
    assert report["recovery_ticks_max"] == 20


def test_undecided_record_has_no_counts_and_a_reason() -> None:
    record = undecided_record(
        arm="fenced",
        seed=3,
        schedule=build_schedule(3, PARAMS),
        reason="no final state for: t000001",
        restarts=0,
        wall_s=1.0,
    )
    assert record["undecided"] is True
    assert record["report"] is None
    assert record["undecided_reason"] == "no final state for: t000001"


def test_aggregate_uses_wilson_over_decided_runs_and_lists_failing_seeds() -> None:
    records = [_record(1), _record(2, stale=3), _record(3, stale=1), _record(4, expired=2)]
    records.append(
        undecided_record(
            arm="fenced",
            seed=5,
            schedule=build_schedule(5, PARAMS),
            reason="x",
            restarts=0,
            wall_s=1.0,
        )
    )
    summary = aggregate(records)
    assert summary["runs"] == 5
    assert summary["decided_runs"] == 4
    assert summary["undecided_runs"] == 1
    stale = summary["stale_writes_accepted"]
    assert isinstance(stale, dict)
    assert stale["runs_with_event"] == 2
    assert stale["events"] == 4
    assert stale["wilson95"] == list(wilson(2, 4))
    assert stale["failing_seeds"] == [2, 3]
    assert summary["small_sample"] is True


def test_aggregate_with_no_decided_run_is_not_a_pass() -> None:
    summary = aggregate([])
    assert summary["decided_runs"] == 0
    stale = summary["stale_writes_accepted"]
    assert isinstance(stale, dict)
    assert stale["wilson95"] == [0.0, 1.0]


def test_result_file_records_the_run_conditions_and_zero_llm_calls() -> None:
    records = [_record(1), _record(2)]
    data = build_result_file(
        configuration="fenced",
        seed_set="development",
        params=PARAMS,
        runs=records,
        environment=ENVIRONMENT,
    )
    assert data["llm_calls"] == 0
    assert data["seed_set"] == "development"
    assert data["seeds"] == [1, 2]
    assert data["workers"] == 8
    assert data["tasks"] == 500
    assert data["commit"] == "abc1234"
    assert data["schema_revision"] == 9
    assert data["fault_parameters"]["kill_rate"] == PARAMS.kill_rate  # type: ignore[index]
    assert "same seed" in str(data["note"])


def test_result_file_rejects_a_mixed_arm_set() -> None:
    with pytest.raises(ValueError):
        build_result_file(
            configuration="fenced",
            seed_set="development",
            params=PARAMS,
            runs=[_record(1), _record(2, arm="baseline")],
            environment=ENVIRONMENT,
        )


def test_result_file_rejects_an_unknown_seed_set() -> None:
    with pytest.raises(ValueError):
        build_result_file(
            configuration="fenced",
            seed_set="whatever",
            params=PARAMS,
            runs=[_record(1)],
            environment=ENVIRONMENT,
        )


def test_write_result_creates_the_file_once_and_refuses_to_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "e2" / "dev" / "chaos_fenced_20261101T000000Z.json"
    write_result(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    with pytest.raises(ResultExistsError):
        write_result(path, {"a": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
