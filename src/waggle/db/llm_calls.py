"""PostgreSQL call log: the ``llm_calls`` table behind the ``CallLog`` protocol (ADR-077).

Rows hold metadata only (model, tokens, latency, cost, status, fallback label, mock or http
mode): no prompt and no response text. The budget guard reads spend from the log, so a write
that fails raises instead of being dropped, otherwise a paid call could go uncounted.
Fallback and cached rows are labeled as the client wrote them.
"""

import math
import re
from typing import cast

from waggle.db.connection import Database
from waggle.llm.budget import PROVIDERS
from waggle.llm.models import CallRecord, CallStatus

_MODES = ("mock", "http")
_STATUSES = ("ok", "denied", "error", "cached")
_LABEL_MAX = 200
_ROLE = re.compile(r"[a-z0-9_]{1,64}")
_PREFIX = re.compile(r"[a-z0-9_]{0,64}")


def _text(value: object, low: int, high: int, what: str) -> str:
    if not isinstance(value, str) or not low <= len(value) <= high:
        raise ValueError(f"invalid {what}")
    return value


def _count(value: object, what: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {what}")
    return value


def _amount(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"invalid {what}")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"invalid {what}")
    return float(value)


class PostgresCallLog:
    """Append-only call log in the database. Implements ``waggle.llm.call_log.CallLog``."""

    def __init__(self, database: Database, mode: str) -> None:
        if mode not in _MODES:
            raise ValueError("mode must be mock or http")
        self._database = database
        self._mode = mode

    def record(self, record: CallRecord) -> None:
        """Append one record. Raises ValueError for a value the table would refuse."""
        _text(record.request_id, 1, 128, "request id")
        if record.task_id is not None:
            _text(record.task_id, 1, 128, "task id")
        if not isinstance(record.role, str) or _ROLE.fullmatch(record.role) is None:
            raise ValueError("invalid role")
        if record.provider not in PROVIDERS:
            raise ValueError("invalid provider")
        _text(record.model_id, 0, 200, "model id")
        if record.status not in _STATUSES:
            raise ValueError("invalid status")
        if record.fallback_label is not None:
            _text(record.fallback_label, 1, _LABEL_MAX, "fallback label")
        values = (
            record.request_id,
            record.task_id,
            record.role,
            record.provider,
            record.model_id,
            record.status,
            _count(record.tokens_in, "tokens in"),
            _count(record.tokens_out, "tokens out"),
            _amount(record.latency_s, "latency"),
            _amount(record.cost_usd, "cost"),
            record.fallback_label,
            self._mode,
        )
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO llm_calls (request_id, task_id, role, provider, model_id, status, "
                "tokens_in, tokens_out, latency_s, cost_usd, fallback_label, mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                values,
            )

    def records(self) -> list[CallRecord]:
        """Every row in insertion order."""
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT request_id, task_id, role, provider, model_id, status, tokens_in, "
                "tokens_out, latency_s, cost_usd, fallback_label FROM llm_calls ORDER BY call_id"
            ).fetchall()
        # Column types and the table checks fix the row types.
        return [
            CallRecord(
                request_id=cast(str, r[0]),
                task_id=cast("str | None", r[1]),
                role=cast(str, r[2]),
                provider=cast(str, r[3]),
                model_id=cast(str, r[4]),
                status=cast(CallStatus, r[5]),
                tokens_in=cast(int, r[6]),
                tokens_out=cast(int, r[7]),
                latency_s=cast(float, r[8]),
                cost_usd=cast(float, r[9]),
                fallback_label=cast("str | None", r[10]),
            )
            for r in rows
        ]

    def cost_by_task(self, role_prefix: str | None = None) -> dict[str, float]:
        """Cost per task over ``ok`` rows. Cached rows cost nothing and are left out.

        ``role_prefix`` keeps the roles that start with it, for example ``court_``.
        """
        prefix = "" if role_prefix is None else role_prefix
        if _PREFIX.fullmatch(prefix) is None:
            raise ValueError("invalid role prefix")
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT task_id, sum(cost_usd) FROM llm_calls "
                "WHERE status = 'ok' AND task_id IS NOT NULL AND starts_with(role, %s) "
                "GROUP BY task_id ORDER BY task_id",
                (prefix,),
            ).fetchall()
        return {cast(str, r[0]): cast(float, r[1]) for r in rows}

    def count_by_status(self) -> dict[str, int]:
        """Raw counts of each status that occurs, cached rows counted apart from ok rows."""
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT status, count(*) FROM llm_calls GROUP BY status ORDER BY status"
            ).fetchall()
        return {cast(str, r[0]): cast(int, r[1]) for r in rows}
