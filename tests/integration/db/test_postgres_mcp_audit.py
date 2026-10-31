"""Cloud-only MCP audit and rate-limit checks against PostgreSQL."""

import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict
from waggle.db.mcp_audit import AuditIntent, McpAuditRepository, RateLimit

pytestmark = pytest.mark.heavy

_HASH = "b" * 64


def _intent(
    correlation_id: str, chassis: str = "carrier", tool: str = "move_waypoint"
) -> AuditIntent:
    return AuditIntent(correlation_id, tool, _HASH, chassis, f"{chassis}-0")


def _rows(db: Database, where: str = "true") -> list[tuple[object, ...]]:
    query = (
        "SELECT correlation_id, phase, decision, reason, outcome FROM mcp_audit "
        f"WHERE {where} ORDER BY audit_id"
    )
    with db.transaction() as connection:
        return connection.execute(query).fetchall()


def test_calls_over_the_limit_are_denied_and_audited(database: Database) -> None:
    repo = McpAuditRepository(database)
    limit = RateLimit(max_calls=2, window_s=60)
    results = [repo.begin(_intent(f"req-{i}"), limit) for i in range(3)]
    assert [r.allowed for r in results] == [True, True, False]
    assert results[2].reason == "rate_limited"
    assert _rows(database, "decision='deny'") == [("req-2", "intent", "deny", "rate_limited", None)]


def test_limit_is_per_chassis(database: Database) -> None:
    repo = McpAuditRepository(database)
    limit = RateLimit(max_calls=1, window_s=60)
    assert repo.begin(_intent("a-1", "carrier"), limit).allowed
    assert repo.begin(_intent("b-1", "forklift"), limit).allowed
    assert not repo.begin(_intent("a-2", "carrier"), limit).allowed


def test_thirty_simultaneous_calls_respect_the_limit(database: Database) -> None:
    limit = RateLimit(max_calls=10, window_s=60)

    def call(index: int) -> bool:
        return McpAuditRepository(database).begin(_intent(f"burst-{index}"), limit).allowed

    with ThreadPoolExecutor(max_workers=30) as pool:
        allowed = list(pool.map(call, range(30)))
    assert sum(allowed) == 10
    assert len(_rows(database, "decision='allow'")) == 10


def test_old_calls_leave_the_window(database: Database) -> None:
    repo = McpAuditRepository(database)
    limit = RateLimit(max_calls=1, window_s=1)
    assert repo.begin(_intent("w-1"), limit).allowed
    assert not repo.begin(_intent("w-2"), limit).allowed
    time.sleep(1.2)
    assert repo.begin(_intent("w-3"), limit).allowed


def test_repeat_returns_the_stored_decision_without_a_new_row(database: Database) -> None:
    repo = McpAuditRepository(database)
    limit = RateLimit(max_calls=1, window_s=60)
    first = repo.begin(_intent("same"), limit)
    again = repo.begin(_intent("same"), limit)
    assert first.allowed and not first.replayed
    assert again.allowed and again.replayed
    assert len(_rows(database, "correlation_id='same'")) == 1


def test_repeat_of_a_denied_call_stays_denied(database: Database) -> None:
    repo = McpAuditRepository(database)
    limit = RateLimit(max_calls=1, window_s=60)
    repo.begin(_intent("one"), limit)
    assert not repo.begin(_intent("two"), limit).allowed
    again = repo.begin(_intent("two"), limit)
    assert not again.allowed and again.replayed and again.reason == "rate_limited"


def test_reused_correlation_id_with_other_content_conflicts(database: Database) -> None:
    repo = McpAuditRepository(database)
    limit = RateLimit(max_calls=5, window_s=60)
    repo.begin(_intent("dup"), limit)
    with pytest.raises(IdempotencyConflict):
        repo.begin(_intent("dup", tool="pick_package"), limit)
    with pytest.raises(IdempotencyConflict):
        repo.begin(_intent("dup", chassis="forklift"), limit)


def test_denial_without_identity_is_audited_and_not_counted(database: Database) -> None:
    repo = McpAuditRepository(database)
    anonymous = AuditIntent("anon-1", "move_waypoint", _HASH, None, None)
    outcome = repo.deny(anonymous, "unknown_token")
    assert not outcome.allowed and outcome.reason == "unknown_token"
    assert repo.deny(anonymous, "unknown_token").replayed
    assert _rows(database) == [("anon-1", "intent", "deny", "unknown_token", None)]
    assert repo.begin(_intent("ok-1"), RateLimit(1, 60)).allowed


def test_denial_cannot_turn_into_an_allow(database: Database) -> None:
    repo = McpAuditRepository(database)
    repo.deny(_intent("d-1"), "schema")
    replay = repo.begin(_intent("d-1"), RateLimit(5, 60))
    assert not replay.allowed and replay.replayed and replay.reason == "schema"


def test_result_row_is_correlated_and_replay_safe(database: Database) -> None:
    repo = McpAuditRepository(database)
    repo.begin(_intent("res-1"), RateLimit(5, 60))
    first = repo.complete("res-1", "ok", 12)
    again = repo.complete("res-1", "ok", 12)
    assert first.recorded and not first.replayed
    assert again.recorded and again.replayed
    assert _rows(database, "phase='result'") == [("res-1", "result", "allow", None, "ok")]
    assert repo.begin(_intent("res-1"), RateLimit(5, 60)).result == "ok"


def test_result_needs_an_allowed_intent_and_cannot_change(database: Database) -> None:
    repo = McpAuditRepository(database)
    assert not repo.complete("missing", "ok", 1).recorded
    repo.deny(_intent("den-1"), "schema")
    assert not repo.complete("den-1", "ok", 1).recorded
    repo.begin(_intent("fix-1"), RateLimit(5, 60))
    repo.complete("fix-1", "ok", 1)
    with pytest.raises(IdempotencyConflict):
        repo.complete("fix-1", "error", 1)


def test_failed_audit_write_raises_so_the_call_is_not_forwarded(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute("ALTER TABLE mcp_audit RENAME TO mcp_audit_gone")
    with pytest.raises(psycopg.Error):
        McpAuditRepository(database).begin(_intent("lost"), RateLimit(5, 60))
