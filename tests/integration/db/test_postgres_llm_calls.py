"""Cloud-only checks of the llm_calls table and the database call log (revision 13)."""

from concurrent.futures import ThreadPoolExecutor

import psycopg.errors
import pytest
from postgres_support import isolated_database

from waggle.db.connection import Database
from waggle.db.llm_calls import PostgresCallLog
from waggle.db.schema import current_revision, migrate
from waggle.llm.budget import BudgetGuard
from waggle.llm.errors import BudgetExceededError
from waggle.llm.models import CallRecord

pytestmark = pytest.mark.heavy


def _rec(request_id: str, **changes: object) -> CallRecord:
    base: dict[str, object] = dict(
        request_id=request_id,
        task_id="t-1",
        role="court_a",
        provider="modal",
        model_id="m",
        status="ok",
        tokens_in=10,
        tokens_out=5,
        latency_s=0.2,
        cost_usd=0.25,
        fallback_label=None,
    )
    base.update(changes)
    return CallRecord(**base)  # type: ignore[arg-type]


def test_revision_thirteen_upgrade_adds_an_empty_table() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=12) == 12
        assert migrate(db, expected_revision=12, target_revision=13) == 13
        assert current_revision(db) == 13
        assert PostgresCallLog(db, "mock").records() == []


def test_records_come_back_in_order_and_equal(database: Database) -> None:
    log = PostgresCallLog(database, "http")
    rows = [_rec("r-1"), _rec("r-2", status="cached", cost_usd=0.0), _rec("r-3", status="error")]
    for row in rows:
        log.record(row)
    assert log.records() == rows


def test_a_fallback_label_and_a_denied_row_without_a_task_are_kept(database: Database) -> None:
    log = PostgresCallLog(database, "http")
    denied = _rec("r-1", status="denied", task_id=None, model_id="", cost_usd=0.0)
    labeled = _rec("r-2", fallback_label="fallback:baseten->modal:error")
    log.record(denied)
    log.record(labeled)
    assert log.records() == [denied, labeled]


def test_the_table_refuses_a_negative_or_unknown_value(database: Database) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
        connection.execute(
            "INSERT INTO llm_calls (request_id, role, provider, model_id, status, tokens_in, "
            "tokens_out, latency_s, cost_usd, mode) "
            "VALUES ('r', 'guard', 'modal', 'm', 'ok', 0, 0, 0, -1, 'http')"
        )
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
        connection.execute(
            "INSERT INTO llm_calls (request_id, role, provider, model_id, status, tokens_in, "
            "tokens_out, latency_s, cost_usd, mode) "
            "VALUES ('r', 'guard', 'modal', 'm', 'ok', 0, 0, 0, 0, 'real')"
        )


def test_the_rollup_sums_ok_rows_per_task_and_leaves_cached_rows_out(database: Database) -> None:
    log = PostgresCallLog(database, "http")
    log.record(_rec("r-1", cost_usd=0.25))
    log.record(_rec("r-2", cost_usd=0.5))
    log.record(_rec("r-2", status="cached", cost_usd=0.0))
    log.record(_rec("r-3", task_id="t-2", cost_usd=1.0))
    log.record(_rec("r-4", task_id="t-2", status="error", cost_usd=0.0))
    log.record(_rec("r-5", task_id=None, cost_usd=9.0))
    assert log.cost_by_task() == {"t-1": 0.75, "t-2": 1.0}
    assert log.cost_by_task(role_prefix="court_") == {"t-1": 0.75, "t-2": 1.0}
    assert log.cost_by_task(role_prefix="guard") == {}
    assert log.count_by_status() == {"ok": 4, "cached": 1, "error": 1}


def test_the_budget_guard_sees_spend_written_by_another_log_instance(database: Database) -> None:
    PostgresCallLog(database, "http").record(_rec("r-1", cost_usd=0.9))
    guard = BudgetGuard({"MODAL_SPEND_CAP_USD": "1.0"}, PostgresCallLog(database, "http"))
    assert guard.spent("modal") == pytest.approx(0.9)
    with pytest.raises(BudgetExceededError):
        guard.check("modal", 0.2, request_id="r-2", role="court_a")
    assert [r.status for r in PostgresCallLog(database, "http").records()][-1] == "denied"


def test_concurrent_writers_lose_no_row(database: Database) -> None:
    log = PostgresCallLog(database, "mock")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: log.record(_rec(f"r-{i}", cost_usd=0.01)), range(40)))
    assert len(log.records()) == 40
