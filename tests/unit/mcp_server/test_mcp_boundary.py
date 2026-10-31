"""The MCP boundary orders its checks and fails closed (ADR-032), against in-memory fakes."""

import logging
from collections.abc import Mapping

import pytest

from waggle.db.corridors import IdempotencyConflict
from waggle.db.mcp_audit import AuditIntent, IntentOutcome, RateLimit, ResultRecord
from waggle.mcp_server.boundary import Boundary
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.identity import Identity, IdentityRecord, hash_token

TOKEN = "c" * 43
EXTENT = MapExtent(0.0, 0.0, 100.0, 50.0)
MOVE = {"task_id": "t1", "x": 10.0, "y": 5.0, "speed": 1.0}


class FakeStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.record = IdentityRecord(hash_token(TOKEN), "carrier", "carrier-0", False)

    def lookup(self, token_hash: str) -> IdentityRecord | None:
        if self.fail:
            raise RuntimeError("db down")
        return self.record if token_hash == self.record.token_hash else None


class FakeAudit:
    """Keeps decisions by correlation id, like the table."""

    def __init__(self, *, allow: bool = True, fail: str | None = None) -> None:
        self.allow = allow
        self.fail = fail
        self.intents: dict[str, IntentOutcome] = {}
        self.denials: list[tuple[AuditIntent, str]] = []
        self.results: list[tuple[str, str]] = []
        self.complete_raises = False

    def begin(self, intent: AuditIntent, limit: RateLimit) -> IntentOutcome:
        if self.fail == "begin":
            raise RuntimeError("audit down")
        if intent.correlation_id in self.intents:
            stored = self.intents[intent.correlation_id]
            return IntentOutcome(stored.allowed, True, stored.reason)
        outcome = IntentOutcome(self.allow, reason=None if self.allow else "rate_limited")
        self.intents[intent.correlation_id] = outcome
        return outcome

    def deny(self, intent: AuditIntent, reason: str) -> IntentOutcome:
        if self.fail == "deny":
            raise RuntimeError("audit down")
        self.denials.append((intent, reason))
        return IntentOutcome(False, reason=reason)

    def complete(self, correlation_id: str, outcome: str, latency_ms: int) -> ResultRecord:
        if self.complete_raises:
            raise RuntimeError("audit down")
        self.results.append((correlation_id, outcome))
        return ResultRecord(True)


class FakeForwarder:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[Identity, str, Mapping[str, object], float]] = []

    def forward(
        self, identity: Identity, tool: str, args: Mapping[str, object], timeout_s: float
    ) -> Mapping[str, object]:
        self.calls.append((identity, tool, args, timeout_s))
        if self.error is not None:
            raise self.error
        return {"accepted": True}


def _boundary(
    audit: FakeAudit | None = None,
    forwarder: FakeForwarder | None = None,
    store: FakeStore | None = None,
) -> tuple[Boundary, FakeAudit, FakeForwarder]:
    audit = audit or FakeAudit()
    forwarder = forwarder or FakeForwarder()
    boundary = Boundary(store or FakeStore(), audit, forwarder, EXTENT, RateLimit(10, 60), 2.5)
    return boundary, audit, forwarder


def test_allowed_call_is_forwarded_with_derived_identity_and_audited() -> None:
    boundary, audit, forwarder = _boundary()
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert result.ok and result.data == {"accepted": True} and result.code is None
    identity, tool, args, timeout = forwarder.calls[0]
    assert identity == Identity("carrier", "carrier-0") and tool == "move_waypoint"
    assert args == MOVE and timeout == 2.5
    assert audit.results == [("req-1", "ok")]


@pytest.mark.parametrize("token", ["", "short token", "x" * 300, "d" * 43])
def test_bad_or_unknown_token_is_denied_audited_and_not_forwarded(token: str) -> None:
    boundary, audit, forwarder = _boundary()
    result = boundary.handle(token, "req-1", "move_waypoint", MOVE)
    assert not result.ok and result.code in ("bad_token", "unknown_token")
    assert forwarder.calls == [] and audit.intents == {}
    ((intent, reason),) = audit.denials
    assert intent.chassis is None and reason == result.code


def test_revoked_token_is_denied() -> None:
    store = FakeStore()
    store.record = IdentityRecord(hash_token(TOKEN), "carrier", "carrier-0", True)
    boundary, _audit, forwarder = _boundary(store=store)
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert result.code == "revoked" and forwarder.calls == []


def test_identity_store_failure_denies() -> None:
    boundary, _audit, forwarder = _boundary(store=FakeStore(fail=True))
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert not result.ok and result.code == "store_error" and forwarder.calls == []


def test_identity_fields_in_arguments_are_rejected_not_trusted() -> None:
    boundary, audit, forwarder = _boundary()
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", {**MOVE, "chassis": "forklift"})
    assert result.code == "unknown_field" and forwarder.calls == []
    assert audit.denials[0][0].chassis == "carrier"


def test_tool_outside_the_allowlist_is_denied() -> None:
    boundary, audit, forwarder = _boundary()
    result = boundary.handle(TOKEN, "req-1", "create_purchase_order", {})
    assert result.code == "tool_not_allowed" and forwarder.calls == []
    assert audit.denials[0][1] == "tool_not_allowed"


def test_out_of_bounds_speed_is_denied_not_clamped() -> None:
    boundary, _audit, forwarder = _boundary()
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", {**MOVE, "speed": 2.5})
    assert result.code == "out_of_bounds" and forwarder.calls == []


def test_rate_limited_call_is_not_forwarded() -> None:
    boundary, audit, forwarder = _boundary(FakeAudit(allow=False))
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert result.code == "rate_limited" and forwarder.calls == [] and audit.results == []


def test_failed_intent_write_denies_without_forwarding() -> None:
    boundary, _audit, forwarder = _boundary(FakeAudit(fail="begin"))
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert not result.ok and result.code == "audit_unavailable" and forwarder.calls == []


def test_failed_denial_write_still_denies() -> None:
    boundary, _audit, forwarder = _boundary(FakeAudit(fail="deny"))
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", {**MOVE, "speed": 9.0})
    assert not result.ok and result.code == "audit_unavailable" and forwarder.calls == []


def test_repeat_of_an_allowed_request_is_never_forwarded_twice() -> None:
    boundary, _audit, forwarder = _boundary()
    boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    again = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert not again.ok and again.code == "duplicate_request" and again.replayed
    assert len(forwarder.calls) == 1


def test_reused_request_id_with_other_content_is_denied() -> None:
    class Conflicting(FakeAudit):
        def begin(self, intent: AuditIntent, limit: RateLimit) -> IntentOutcome:
            raise IdempotencyConflict("reused")

    boundary, _audit, forwarder = _boundary(Conflicting())
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert result.code == "request_id_conflict" and forwarder.calls == []


def test_tool_exception_becomes_an_error_result_and_an_error_row(
    caplog: pytest.LogCaptureFixture,
) -> None:
    boundary, audit, _forwarder = _boundary(forwarder=FakeForwarder(error=TimeoutError("secret")))
    with caplog.at_level(logging.ERROR):
        result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert not result.ok and result.code == "tool_error" and "secret" not in str(result)
    assert audit.results == [("req-1", "error")]
    assert TOKEN not in caplog.text


def test_result_row_failure_does_not_hide_a_completed_effect() -> None:
    audit = FakeAudit()
    audit.complete_raises = True
    boundary, _, forwarder = _boundary(audit)
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", MOVE)
    assert result.ok and len(forwarder.calls) == 1


@pytest.mark.parametrize("request_id", ["", "bad id", "x" * 129, None, 5])
def test_invalid_request_id_is_denied_before_any_work(request_id: object) -> None:
    store = FakeStore()
    boundary, audit, forwarder = _boundary(store=store)
    result = boundary.handle(TOKEN, request_id, "move_waypoint", MOVE)  # type: ignore[arg-type]
    assert result.code == "bad_request_id" and forwarder.calls == []
    assert audit.denials == [] and audit.intents == {}


def test_unserializable_arguments_are_denied_and_audited() -> None:
    boundary, audit, forwarder = _boundary()
    result = boundary.handle(TOKEN, "req-1", "move_waypoint", {"task_id": object()})
    assert not result.ok and forwarder.calls == []
    assert audit.denials and len(audit.denials[0][0].args_hash) == 64


def test_oversize_tool_name_is_denied_and_audited_with_a_safe_name() -> None:
    boundary, audit, forwarder = _boundary()
    result = boundary.handle(TOKEN, "req-1", "t" * 500, {})
    assert result.code == "tool_not_allowed" and forwarder.calls == []
    assert len(audit.denials[0][0].tool) <= 64


def test_constructor_rejects_a_bad_timeout() -> None:
    for timeout in (0, -1, 0.0, float("nan"), 61):
        with pytest.raises(ValueError):
            Boundary(FakeStore(), FakeAudit(), FakeForwarder(), EXTENT, RateLimit(1, 1), timeout)
