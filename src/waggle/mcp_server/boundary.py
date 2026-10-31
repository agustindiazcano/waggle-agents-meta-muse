"""The MCP call boundary (ADR-032): the only path from a caller to a tool effect.

Order of checks, each failing closed with a typed result and no forward: authenticate,
allowlist and schema, rate limit with the intent row, forward with a per-call timeout, result
row. Identity comes from the token only. The module holds no state, opens no connection and
writes nothing to stdout; the identity store, the audit log and the forwarder are injected.
"""

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from waggle.db.corridors import IdempotencyConflict
from waggle.db.mcp_audit import AuditIntent, IntentOutcome, RateLimit, ResultRecord
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.identity import AuthError, Identity, IdentityStore, authenticate
from waggle.mcp_server.schemas import SchemaError, validate_call

logger = logging.getLogger("waggle.mcp_server")

_REQUEST_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_TOOL_MAX = 64
_TIMEOUT_MAX_S = 60.0


class AuditLog(Protocol):
    """The audit and rate-limit store. ``McpAuditRepository`` satisfies it."""

    def begin(self, intent: AuditIntent, limit: RateLimit) -> IntentOutcome:
        """Write the intent row, allowed or denied by the rate limit."""
        ...

    def deny(self, intent: AuditIntent, reason: str) -> IntentOutcome:
        """Audit a denial."""
        ...

    def complete(self, correlation_id: str, outcome: str, latency_ms: int) -> ResultRecord:
        """Write the result row for an allowed intent."""
        ...


class Forwarder(Protocol):
    """Executes an allowed call. It must enforce the timeout and do its own fencing."""

    def forward(
        self, identity: Identity, tool: str, args: Mapping[str, object], timeout_s: float
    ) -> Mapping[str, object]:
        """Run the tool and return its data, or raise."""
        ...


@dataclass(frozen=True)
class CallResult:
    """Outcome of one call. ``code`` is the reason code of a denial or error. Never a value."""

    ok: bool
    code: str | None = None
    data: Mapping[str, object] | None = None
    replayed: bool = False


def _digest(args: object) -> str:
    try:
        text = json.dumps(args, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        text = "unserializable"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tool_name(tool: object) -> str:
    if isinstance(tool, str) and 1 <= len(tool) <= _TOOL_MAX:
        return tool
    return "invalid_tool"


class Boundary:
    """Runs one call through every check in order."""

    def __init__(
        self,
        store: IdentityStore,
        audit: AuditLog,
        forwarder: Forwarder,
        extent: MapExtent,
        limit: RateLimit,
        timeout_s: float,
    ) -> None:
        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, int | float)
            or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= _TIMEOUT_MAX_S
        ):
            raise ValueError("timeout must be positive and at most 60 seconds")
        self._store = store
        self._audit = audit
        self._forwarder = forwarder
        self._extent = extent
        self._limit = limit
        self._timeout_s = float(timeout_s)

    def handle(
        self, token: str, request_id: str, tool: str, args: Mapping[str, object]
    ) -> CallResult:
        """Return a typed result. Never raises: a bad call must not stop the process."""
        if not isinstance(request_id, str) or _REQUEST_ID.fullmatch(request_id) is None:
            logger.warning("call rejected: invalid request id")
            return CallResult(False, "bad_request_id")
        name = _tool_name(tool)
        try:
            identity = authenticate(token, self._store)
        except AuthError as err:
            anonymous = AuditIntent(request_id, name, _digest(args), None, None)
            return self._deny(anonymous, err.code)
        try:
            checked = validate_call(tool, identity.chassis, args, self._extent)
        except SchemaError as err:
            denied = AuditIntent(
                request_id, name, _digest(args), identity.chassis, identity.robot_id
            )
            return self._deny(denied, err.code)
        intent = AuditIntent(
            request_id, name, _digest(checked), identity.chassis, identity.robot_id
        )
        try:
            decision = self._audit.begin(intent, self._limit)
        except IdempotencyConflict:
            return CallResult(False, "request_id_conflict")
        except Exception as err:
            logger.error("intent write failed: %s", type(err).__name__)
            return CallResult(False, "audit_unavailable")
        if not decision.allowed:
            return CallResult(False, decision.reason or "denied", replayed=decision.replayed)
        if decision.replayed:
            return CallResult(False, "duplicate_request", replayed=True)
        return self._forward(identity, request_id, name, checked)

    def _deny(self, intent: AuditIntent, reason: str) -> CallResult:
        try:
            self._audit.deny(intent, reason)
        except Exception as err:
            logger.error("denial write failed: %s", type(err).__name__)
            return CallResult(False, "audit_unavailable")
        return CallResult(False, reason)

    def _forward(
        self, identity: Identity, request_id: str, tool: str, args: Mapping[str, object]
    ) -> CallResult:
        started = time.monotonic()
        data: Mapping[str, object] | None = None
        try:
            data = self._forwarder.forward(identity, tool, args, self._timeout_s)
            if not isinstance(data, Mapping):
                raise TypeError("tool result is not a mapping")
            outcome = "ok"
        except Exception as err:
            logger.error("tool %s failed: %s", tool, type(err).__name__)
            outcome = "error"
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        try:
            self._audit.complete(request_id, outcome, latency_ms)
        except Exception as err:
            logger.error("result write failed: %s", type(err).__name__)
        if outcome == "ok":
            return CallResult(True, data=data)
        return CallResult(False, "tool_error")
