"""PostgresCallLog refuses a bad mode or record before any query, and writes one INSERT."""

import pytest
from db_fakes import FakeDatabase

from waggle.db.llm_calls import PostgresCallLog
from waggle.llm.models import CallRecord


def _record(**changes: object) -> CallRecord:
    base = dict(
        request_id="r-1",
        task_id="t-1",
        role="guard",
        provider="modal",
        model_id="m",
        status="ok",
        tokens_in=3,
        tokens_out=4,
        latency_s=0.5,
        cost_usd=0.01,
        fallback_label=None,
    )
    base.update(changes)
    return CallRecord(**base)  # type: ignore[arg-type]


def _log(mode: str = "mock") -> tuple[PostgresCallLog, FakeDatabase]:
    db = FakeDatabase(lambda sql, params: None)
    return PostgresCallLog(db, mode), db  # type: ignore[arg-type]


def test_a_mode_other_than_mock_or_http_is_refused() -> None:
    with pytest.raises(ValueError):
        _log("real")


def test_a_record_is_one_insert_into_llm_calls() -> None:
    log, db = _log()
    log.record(_record())
    assert len(db.log) == 1 and db.log[0].startswith("INSERT INTO llm_calls")
    assert db.transactions == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"cost_usd": float("nan")},
        {"cost_usd": float("inf")},
        {"cost_usd": -0.01},
        {"latency_s": float("nan")},
        {"tokens_in": -1},
        {"request_id": ""},
        {"role": "x" * 65},
        {"provider": "someone"},
        {"status": "maybe"},
    ],
)
def test_a_record_the_table_would_refuse_is_refused_before_the_query(
    changes: dict[str, object],
) -> None:
    log, db = _log()
    with pytest.raises(ValueError):
        log.record(_record(**changes))
    assert db.log == []
