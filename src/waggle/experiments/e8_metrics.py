"""E8 summaries of measured call-log rows, without inference across repeats.

Latency percentiles use nearest rank: sorted[ceil(p * count) - 1]. Only
successful rows contribute latency, cost or token totals. Cached completions
are request observations, not additional provider spend. A group without a
successful row has null latency rather than an invented zero measurement.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Sequence

from waggle.llm.models import CallRecord, CallStatus

_STATUSES: tuple[CallStatus, ...] = ("ok", "denied", "error", "cached")


def _nonnegative_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite nonnegative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def latency_summary(samples: Sequence[float]) -> dict[str, float | int]:
    """Summarize nonempty finite seconds using nearest-rank percentiles."""
    if not samples:
        raise ValueError("latency samples must not be empty")
    ordered = sorted(_nonnegative_number(value, "latency") for value in samples)
    count = len(ordered)
    return {
        "count": count,
        "min": ordered[0],
        "max": ordered[-1],
        "p50": ordered[math.ceil(0.50 * count) - 1],
        "p95": ordered[math.ceil(0.95 * count) - 1],
        "p99": ordered[math.ceil(0.99 * count) - 1],
    }


def _validate(record: CallRecord) -> None:
    if record.status not in _STATUSES:
        raise ValueError("unknown call status")
    for name in ("request_id", "role", "provider", "model_id"):
        value = getattr(record, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a nonempty string")
    for name in ("task_id", "fallback_label"):
        value = getattr(record, name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be null or a nonempty string")
    for name in ("tokens_in", "tokens_out"):
        value = getattr(record, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    _nonnegative_number(record.latency_s, "latency_s")
    _nonnegative_number(record.cost_usd, "cost_usd")


def _cost(records: Sequence[CallRecord]) -> float:
    try:
        return math.fsum(row.cost_usd for row in records if row.status == "ok")
    except OverflowError as exc:
        raise ValueError("aggregate cost exceeds finite range") from exc


def _summary(records: Sequence[CallRecord]) -> dict[str, object]:
    successful = [row for row in records if row.status == "ok"]
    counts = Counter(row.status for row in records)
    requests = Counter(row.request_id for row in records)
    return {
        "total_rows": len(records),
        "unique_request_count": len(requests),
        "request_row_counts": dict(sorted(requests.items())),
        "status_counts": {status: counts[status] for status in _STATUSES},
        "latency_s": latency_summary([row.latency_s for row in successful]) if successful else None,
        "cost_usd": _cost(records),
        "tokens_in": sum(row.tokens_in for row in successful),
        "tokens_out": sum(row.tokens_out for row in successful),
    }


def summarize_calls(records: Sequence[CallRecord]) -> dict[str, object]:
    """Summarize validated rows, retaining repeats and explicit fallback labels.

    Unique request counts describe identifiers only; rows are never treated as
    independent experimental samples. Null task IDs remain a separate cost row.
    All status and fallback counts include cached, error and denied rows.
    """
    if not records:
        raise ValueError("call records must not be empty")
    for row in records:
        _validate(row)
    result = _summary(records)
    result["sampling_unit"] = "call_log_row"
    result["percentile_method"] = "nearest_rank"
    for field in ("provider", "model_id", "role"):
        groups: dict[str, list[CallRecord]] = defaultdict(list)
        for row in records:
            groups[getattr(row, field)].append(row)
        result[f"by_{field}"] = {key: _summary(groups[key]) for key in sorted(groups)}
    tasks: dict[str | None, list[CallRecord]] = defaultdict(list)
    roles: dict[str, list[CallRecord]] = defaultdict(list)
    for row in records:
        tasks[row.task_id].append(row)
        roles[row.role].append(row)
    result["costs_by_task"] = [
        {"task_id": task, "cost_usd": _cost(tasks[task])}
        for task in sorted(tasks, key=lambda value: (value is None, value or ""))
    ]
    result["costs_by_role"] = {role: _cost(roles[role]) for role in sorted(roles)}
    labels = Counter(row.fallback_label for row in records)
    result["fallback_labels"] = [
        {"label": label, "row_count": labels[label]}
        for label in sorted(labels, key=lambda value: (value is not None, value or ""))
    ]
    return result
