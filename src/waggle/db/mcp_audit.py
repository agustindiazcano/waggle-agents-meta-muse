"""MCP audit rows and the database-backed rate limit (ADR-032 steps 4, 5 and 7).

An intent row is written before any forward, so a failed write raises and the caller must deny.
The sliding-window count reads allowed intent rows under a transaction-scoped advisory lock per
chassis, so it holds across replicas and no counter lives in process memory. It authenticates
nobody and forwards nothing: the server wiring does both.
"""

import re
from dataclasses import dataclass
from typing import Literal, cast

import psycopg

from waggle.db.connection import Database, Row
from waggle.db.corridors import IdempotencyConflict

_CHASSIS_LOCK_SEED = 19730404
_CORRELATION = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_REASON = re.compile(r"[a-z_]{1,40}")
_HASH = re.compile(r"[0-9a-f]{64}")
_NAME_MAX = 64
_INT_MAX = 2**31 - 1

ResultOutcome = Literal["ok", "error"]


def _bounded(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


@dataclass(frozen=True)
class AuditIntent:
    """The validated facts of one call. ``args_hash`` is the SHA-256 of the validated arguments.

    Chassis and robot id are both set for an authenticated caller and both None for a failed
    authentication, which can only be denied.
    """

    correlation_id: str
    tool: str
    args_hash: str
    chassis: str | None
    robot_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, str) or not _CORRELATION.fullmatch(
            self.correlation_id
        ):
            raise ValueError("invalid correlation id")
        if not isinstance(self.tool, str) or not 1 <= len(self.tool) <= _NAME_MAX:
            raise ValueError("invalid tool name")
        if not isinstance(self.args_hash, str) or not _HASH.fullmatch(self.args_hash):
            raise ValueError("args hash must be 64 lowercase hex digits")
        if (self.chassis is None) != (self.robot_id is None):
            raise ValueError("chassis and robot id are set together or not at all")
        for name in (self.chassis, self.robot_id):
            if name is not None and (not isinstance(name, str) or not 1 <= len(name) <= _NAME_MAX):
                raise ValueError("invalid chassis or robot id")


@dataclass(frozen=True)
class RateLimit:
    """At most ``max_calls`` allowed intents per chassis in the last ``window_s`` seconds."""

    max_calls: int
    window_s: int

    def __post_init__(self) -> None:
        if not _bounded(self.max_calls, 1, 10_000) or not _bounded(self.window_s, 1, 3600):
            raise ValueError("rate limit values are out of range")


@dataclass(frozen=True)
class IntentOutcome:
    """The stored decision. ``result`` is the recorded outcome of an allowed call, if any."""

    allowed: bool
    replayed: bool = False
    reason: str | None = None
    result: str | None = None


@dataclass(frozen=True)
class ResultRecord:
    """Whether a result row exists for an allowed intent, and whether it was already there."""

    recorded: bool
    replayed: bool = False


class McpAuditRepository:
    """Audit and rate-limit persistence; each method uses its own short transaction."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def begin(self, intent: AuditIntent, limit: RateLimit) -> IntentOutcome:
        """Write the intent row: allowed, or denied as ``rate_limited`` over the window limit.

        A repeated correlation id returns the stored decision and writes nothing. Reusing it
        for different content raises IdempotencyConflict. Database errors propagate: no row
        means the call must not be forwarded.
        """
        if intent.chassis is None:
            raise ValueError("an anonymous call has no identity and can only be denied")
        with self._database.transaction() as connection:
            self._lock(connection, intent.chassis)
            stored = self._stored(connection, intent)
            if stored is not None:
                return stored
            used = connection.execute(
                "SELECT count(*) FROM mcp_audit WHERE phase='intent' AND decision='allow' "
                "AND chassis=%s AND created_at > clock_timestamp() - make_interval(secs => %s)",
                (intent.chassis, limit.window_s),
            ).fetchone()
            allowed = used is not None and cast(int, used[0]) < limit.max_calls
            reason = None if allowed else "rate_limited"
            self._insert_intent(connection, intent, allowed, reason)
            return IntentOutcome(allowed, reason=reason)

    def deny(self, intent: AuditIntent, reason: str) -> IntentOutcome:
        """Audit a denial from authentication, allowlist or schema. Denials are not counted."""
        if not isinstance(reason, str) or not _REASON.fullmatch(reason):
            raise ValueError("invalid denial reason")
        with self._database.transaction() as connection:
            self._lock(connection, intent.chassis or "")
            stored = self._stored(connection, intent)
            if stored is not None:
                return IntentOutcome(False, True, stored.reason or reason)
            self._insert_intent(connection, intent, False, reason)
            return IntentOutcome(False, reason=reason)

    def complete(self, correlation_id: str, outcome: str, latency_ms: int) -> ResultRecord:
        """Write the result row sharing the correlation id of an allowed intent.

        Nothing is recorded for a missing or denied intent. A repeat with the same outcome is
        a replay; a different outcome raises IdempotencyConflict.
        """
        if not isinstance(correlation_id, str) or not _CORRELATION.fullmatch(correlation_id):
            raise ValueError("invalid correlation id")
        if outcome not in ("ok", "error"):
            raise ValueError("invalid result outcome")
        if not _bounded(latency_ms, 0, _INT_MAX):
            raise ValueError("invalid latency")
        with self._database.transaction() as connection:
            row = connection.execute(
                "INSERT INTO mcp_audit (correlation_id, phase, chassis, robot_id, tool, "
                "args_hash, decision, outcome, latency_ms) "
                "SELECT correlation_id, 'result', chassis, robot_id, tool, args_hash, "
                "'allow', %s, %s FROM mcp_audit "
                "WHERE correlation_id=%s AND phase='intent' AND decision='allow' "
                "ON CONFLICT (correlation_id, phase) DO NOTHING RETURNING audit_id",
                (outcome, latency_ms, correlation_id),
            ).fetchone()
            if row is not None:
                return ResultRecord(True)
            existing = connection.execute(
                "SELECT outcome FROM mcp_audit WHERE correlation_id=%s AND phase='result'",
                (correlation_id,),
            ).fetchone()
            if existing is None:
                return ResultRecord(False)
            if existing[0] != outcome:
                raise IdempotencyConflict("result already recorded with another outcome")
            return ResultRecord(True, True)

    @staticmethod
    def _lock(connection: psycopg.Connection[Row], chassis: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, %s))",
            (chassis, _CHASSIS_LOCK_SEED),
        )

    @staticmethod
    def _stored(connection: psycopg.Connection[Row], intent: AuditIntent) -> IntentOutcome | None:
        row = connection.execute(
            "SELECT i.chassis, i.robot_id, i.tool, i.args_hash, i.decision, i.reason, r.outcome "
            "FROM mcp_audit i LEFT JOIN mcp_audit r "
            "ON r.correlation_id=i.correlation_id AND r.phase='result' "
            "WHERE i.correlation_id=%s AND i.phase='intent'",
            (intent.correlation_id,),
        ).fetchone()
        if row is None:
            return None
        if row[:4] != (intent.chassis, intent.robot_id, intent.tool, intent.args_hash):
            raise IdempotencyConflict("correlation id reused with different content")
        return IntentOutcome(
            row[4] == "allow", True, cast(str | None, row[5]), cast(str | None, row[6])
        )

    @staticmethod
    def _insert_intent(
        connection: psycopg.Connection[Row],
        intent: AuditIntent,
        allowed: bool,
        reason: str | None,
    ) -> None:
        connection.execute(
            "INSERT INTO mcp_audit (correlation_id, phase, chassis, robot_id, tool, args_hash, "
            "decision, reason) VALUES (%s, 'intent', %s, %s, %s, %s, %s, %s)",
            (
                intent.correlation_id,
                intent.chassis,
                intent.robot_id,
                intent.tool,
                intent.args_hash,
                "allow" if allowed else "deny",
                reason,
            ),
        )
