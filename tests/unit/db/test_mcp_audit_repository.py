"""Invalid audit inputs fail before a database transaction opens."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.mcp_audit import AuditIntent, McpAuditRepository, RateLimit

_HASH = "a" * 64


def _intent(**overrides: str | None) -> AuditIntent:
    fields: dict[str, str | None] = {
        "correlation_id": "req-1",
        "tool": "move_waypoint",
        "args_hash": _HASH,
        "chassis": "carrier",
        "robot_id": "robot-0",
    }
    fields.update(overrides)
    return AuditIntent(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"correlation_id": ""},
        {"correlation_id": "bad id"},
        {"correlation_id": "x" * 129},
        {"tool": ""},
        {"tool": "t" * 65},
        {"args_hash": "abc"},
        {"args_hash": "G" * 64},
        {"chassis": None},
        {"robot_id": None},
        {"chassis": ""},
    ],
)
def test_invalid_intent_fields_raise(overrides: dict[str, str | None]) -> None:
    with pytest.raises(ValueError):
        _intent(**overrides)


@pytest.mark.parametrize("max_calls", [0, -1, 10_001, True, 1.5])
def test_invalid_rate_limit_calls_raise(max_calls: object) -> None:
    with pytest.raises(ValueError):
        RateLimit(max_calls=max_calls, window_s=10)  # type: ignore[arg-type]


@pytest.mark.parametrize("window_s", [0, -1, 3601, True])
def test_invalid_rate_limit_window_raises(window_s: object) -> None:
    with pytest.raises(ValueError):
        RateLimit(max_calls=1, window_s=window_s)  # type: ignore[arg-type]


def test_begin_without_identity_does_not_connect() -> None:
    database = MagicMock(spec=Database)
    anonymous = AuditIntent("req-1", "move_waypoint", _HASH, None, None)
    with pytest.raises(ValueError, match="identity"):
        McpAuditRepository(database).begin(anonymous, RateLimit(1, 10))
    database.transaction.assert_not_called()


@pytest.mark.parametrize("reason", ["", "Bad Reason", "x" * 41, "with-dash"])
def test_invalid_denial_reason_does_not_connect(reason: str) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError, match="reason"):
        McpAuditRepository(database).deny(_intent(), reason)
    database.transaction.assert_not_called()


@pytest.mark.parametrize(
    ("outcome", "latency_ms"), [("maybe", 1), ("ok", -1), ("ok", True), ("ok", 2**31)]
)
def test_invalid_result_does_not_connect(outcome: str, latency_ms: int) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        McpAuditRepository(database).complete("req-1", outcome, latency_ms)
    database.transaction.assert_not_called()
