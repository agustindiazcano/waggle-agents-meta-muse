"""Automated metadata-only export of llm_calls rows for the E8 report runner.

The export selects only metadata columns for one mode, in insertion order, and
writes the exact document that ``waggle.experiments.e8_run.load_calls`` accepts.
No prompt or response text exists in the table or in this export. Validation of
the rows themselves is reused from ``summarize_calls``; this module adds only
the query, the row mapping and the provenance checks the loader also requires.
"""

import json
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, cast

from waggle.experiments.e8_metrics import summarize_calls
from waggle.llm.models import CallRecord, CallStatus

_MODES = ("mock", "http")
_QUERY = (
    "SELECT request_id, task_id, role, provider, model_id, status, tokens_in, "
    "tokens_out, latency_s, cost_usd, fallback_label FROM llm_calls "
    "WHERE mode = %s ORDER BY call_id"
)


class _Cursor(Protocol):
    """Minimal cursor shape used by the export query."""

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return every selected row."""
        ...


class _Connection(Protocol):
    """Minimal connection shape used by the export query."""

    def execute(self, sql: str, params: tuple[object, ...] = ...) -> _Cursor:
        """Run one query."""
        ...


class CallDatabase(Protocol):
    """Database shape with short-lived transactions, as in waggle.db.Database."""

    def transaction(self) -> AbstractContextManager[_Connection]:
        """Open one transaction."""
        ...


def _provenance(mode: str, commit: str, prompt_versions: Mapping[str, str]) -> dict[str, str]:
    if mode not in _MODES:
        raise ValueError("mode must be mock or http")
    if not isinstance(commit, str) or not commit.strip() or len(commit) > 256:
        raise ValueError("invalid source commit")
    if not prompt_versions:
        raise ValueError("prompt_versions must be a nonempty object")
    versions: dict[str, str] = {}
    for role, version in prompt_versions.items():
        for value in (role, version):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError("invalid prompt version")
        versions[role] = version
    return versions


def fetch_call_records(database: CallDatabase, *, mode: str) -> list[CallRecord]:
    """Read metadata rows for one mode in insertion order; prompt text is never selected."""
    if mode not in _MODES:
        raise ValueError("mode must be mock or http")
    with database.transaction() as connection:
        rows = connection.execute(_QUERY, (mode,)).fetchall()
    records: list[CallRecord] = []
    for row in rows:
        if len(row) != 11:
            raise ValueError("llm_calls row must contain exactly the metadata columns")
        records.append(
            CallRecord(
                request_id=cast(str, row[0]),
                task_id=cast("str | None", row[1]),
                role=cast(str, row[2]),
                provider=cast(str, row[3]),
                model_id=cast(str, row[4]),
                status=cast(CallStatus, row[5]),
                tokens_in=cast(int, row[6]),
                tokens_out=cast(int, row[7]),
                latency_s=cast(float, row[8]),
                cost_usd=cast(float, row[9]),
                fallback_label=cast("str | None", row[10]),
            )
        )
    return records


def build_export(
    records: Sequence[CallRecord],
    *,
    mode: str,
    commit: str,
    prompt_versions: Mapping[str, str],
) -> dict[str, object]:
    """Build the strict export document consumed by the existing E8 loader."""
    versions = _provenance(mode, commit, prompt_versions)
    summarize_calls(records)
    if not {record.role for record in records}.issubset(versions):
        raise ValueError("prompt_versions must cover every recorded role")
    return {
        "source": "llm_calls",
        "mode": mode,
        "commit": commit,
        "prompt_versions": versions,
        "records": [
            {
                "request_id": record.request_id,
                "task_id": record.task_id,
                "role": record.role,
                "provider": record.provider,
                "model_id": record.model_id,
                "status": record.status,
                "tokens_in": record.tokens_in,
                "tokens_out": record.tokens_out,
                "latency_s": record.latency_s,
                "cost_usd": record.cost_usd,
                "fallback_label": record.fallback_label,
            }
            for record in records
        ],
    }


def export_calls(
    database: CallDatabase,
    *,
    mode: str,
    commit: str,
    prompt_versions: Mapping[str, str],
    output: Path,
) -> dict[str, object]:
    """Export one mode from llm_calls to a new file; existing files are never replaced."""
    document = build_export(
        fetch_call_records(database, mode=mode),
        mode=mode,
        commit=commit,
        prompt_versions=prompt_versions,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(document, indent=2, allow_nan=False) + "\n")
    return document
