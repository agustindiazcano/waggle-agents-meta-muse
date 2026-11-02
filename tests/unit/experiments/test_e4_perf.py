"""Latency per model and cost per task from CallLog records (COURT_DESIGN sections 6 and 8)."""

import math

from waggle.experiments.e4_metrics import RunRecord
from waggle.experiments.e4_perf import cost_per_task, latency_per_model
from waggle.llm.models import CallRecord, CallStatus


def _call(
    role: str,
    status: CallStatus,
    *,
    model: str = "m1",
    cost: float = 0.0,
    latency: float = 0.0,
    task: str | None = None,
) -> CallRecord:
    return CallRecord(f"req-{role}-{status}", task, role, "p", model, status, 1, 1, latency, cost)


def _run(case_id: str, repeat: int, calls: tuple[CallRecord, ...]) -> RunRecord:
    return RunRecord(case_id, "benign", repeat, "execute", "unanimous", (), calls)


def test_cost_per_task_sums_ok_court_rows_and_counts_cached_rows_apart() -> None:
    runs = [
        _run(
            "c1",
            0,
            (
                _call("court_1", "ok", cost=0.25),
                _call("court_2", "ok", cost=0.5),
                _call("court_2", "cached"),
            ),
        ),
        _run("c2", 0, (_call("court_1", "ok", cost=0.75),)),
        _run("c3", 0, ()),
    ]
    out = cost_per_task(runs)
    assert out["tasks"] == 3
    assert out["per_task"] == {"c1-r0": 0.75, "c2-r0": 0.75, "c3-r0": 0.0}
    assert math.isclose(out["total_usd"], 1.5)
    assert math.isclose(out["mean_usd"], 0.5)
    assert out["cached_rows"] == 1
    assert out["cached_rows_excluded_cost_usd"] == 0.0


def test_cached_rows_never_add_cost_even_if_they_carry_one() -> None:
    runs = [_run("c1", 1, (_call("court_1", "ok", cost=1.0), _call("court_1", "cached", cost=1.0)))]
    out = cost_per_task(runs)
    assert out["per_task"] == {"c1-r1": 1.0}
    assert out["cached_rows"] == 1 and out["cached_rows_excluded_cost_usd"] == 1.0


def test_only_court_roles_with_ok_status_count() -> None:
    runs = [
        _run(
            "c1",
            0,
            (
                _call("guard", "ok", cost=9.0),
                _call("court_1", "error", cost=9.0),
                _call("court_1", "denied", cost=9.0),
                _call("court_1", "ok", cost=0.5),
            ),
        )
    ]
    out = cost_per_task(runs)
    assert out["per_task"] == {"c1-r0": 0.5}
    assert out["not_ok_rows"] == 2


def test_cost_with_no_runs_is_an_empty_report_not_a_zero_mean() -> None:
    out = cost_per_task([])
    assert out["tasks"] == 0 and out["mean_usd"] is None


def test_latency_per_model_uses_ok_rows_only() -> None:
    runs = [
        _run(
            "c1",
            0,
            (
                _call("court_1", "ok", model="a", latency=1.0),
                _call("court_2", "ok", model="b", latency=3.0),
                _call("court_1", "cached", model="a", latency=0.0),
            ),
        ),
        _run(
            "c2",
            0,
            (
                _call("court_1", "ok", model="a", latency=3.0),
                _call("court_1", "error", model="a", latency=0.0),
            ),
        ),
    ]
    out = latency_per_model(runs)
    assert out["a"] == {"n": 2, "median_s": 2.0, "max_s": 3.0, "mean_s": 2.0}
    assert out["b"] == {"n": 1, "median_s": 3.0, "max_s": 3.0, "mean_s": 3.0}
    assert set(out) == {"a", "b"}


def test_latency_label_says_what_it_measures() -> None:
    out = latency_per_model([_run("c1", 0, (_call("court_1", "ok", latency=0.5),))])
    assert out["m1"]["n"] == 1
