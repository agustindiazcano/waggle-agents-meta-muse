"""Known values and rejected inputs for the E8 call-log summaries."""

import json
from typing import cast

import pytest

from waggle.experiments.e8_metrics import latency_summary, summarize_calls
from waggle.llm.models import CallRecord, CallStatus


def record(**changes: object) -> CallRecord:
    """Build a log row, allowing malformed runtime values for rejection tests."""
    row = CallRecord("request-1", "task-1", "court", "mock", "model-1", "ok", 10, 2, 1, 0.25)
    # Bypass frozen-field types to exercise malformed external log rows.
    for name, value in changes.items():
        object.__setattr__(row, name, value)
    return row


def test_latency_nearest_rank_known_values() -> None:
    assert latency_summary(list(range(1, 101))) == {
        "count": 100,
        "min": 1.0,
        "max": 100.0,
        "p50": 50.0,
        "p95": 95.0,
        "p99": 99.0,
    }
    assert latency_summary([3.0]) == {
        "count": 1,
        "min": 3.0,
        "max": 3.0,
        "p50": 3.0,
        "p95": 3.0,
        "p99": 3.0,
    }


def test_summary_retains_rows_and_excludes_cached_errors_and_denials() -> None:
    rows = [
        record(),
        record(latency_s=3.0, cost_usd=0.5, task_id=None, fallback_label="backup"),
        record(status="cached", cost_usd=90, latency_s=900),
        record(status="error", cost_usd=90, latency_s=900),
        record(status="denied", cost_usd=90, latency_s=900),
    ]
    result = summarize_calls(rows)
    assert result["total_rows"] == 5
    assert result["unique_request_count"] == 1
    assert result["request_row_counts"] == {"request-1": 5}
    assert result["status_counts"] == {"ok": 2, "cached": 1, "error": 1, "denied": 1}
    assert result["latency_s"] == latency_summary([1, 3])
    assert result["cost_usd"] == 0.75
    assert result["tokens_in"] == 20
    assert result["tokens_out"] == 4
    assert result["costs_by_task"] == [
        {"task_id": "task-1", "cost_usd": 0.25},
        {"task_id": None, "cost_usd": 0.5},
    ]
    assert result["costs_by_role"] == {"court": 0.75}
    assert result["fallback_labels"] == [
        {"label": None, "row_count": 4},
        {"label": "backup", "row_count": 1},
    ]
    assert result["sampling_unit"] == "call_log_row"
    json.dumps(result, allow_nan=False)


def test_grouping_and_no_successful_calls() -> None:
    rows = [record(status="error"), record(provider="other", model_id="m2", role="advisor")]
    result = summarize_calls(rows)
    for key, name in [("by_provider", "mock"), ("by_model_id", "model-1"), ("by_role", "court")]:
        group = cast(dict[str, dict[str, object]], result[key])[name]
        assert group["latency_s"] is None
        assert group["cost_usd"] == 0
        assert group["tokens_in"] == 0
        assert group["status_counts"] == {"ok": 0, "cached": 0, "error": 1, "denied": 0}


@pytest.mark.parametrize("samples", [[], [-1], [float("nan")], [float("inf")], [True]])
def test_latency_rejects_invalid_samples(samples: list[float]) -> None:
    with pytest.raises(ValueError):
        latency_summary(samples)


@pytest.mark.parametrize(
    "changes",
    [
        {"latency_s": -1},
        {"cost_usd": float("inf")},
        {"cost_usd": -1},
        {"tokens_in": -1},
        {"tokens_out": 1.5},
        {"tokens_out": True},
        {"status": cast(CallStatus, "unknown")},
        {"request_id": ""},
        {"provider": ""},
        {"fallback_label": ""},
    ],
)
def test_summary_rejects_invalid_rows(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        summarize_calls([record(**changes)])


def test_summary_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        summarize_calls([])
