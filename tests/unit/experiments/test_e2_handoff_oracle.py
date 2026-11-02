"""E2 handoff oracle: counts from hand-built logs, one log per violation and one clean log."""

import pytest

from waggle.experiments.e2_handoff_oracle import HandoffReport, judge_handoffs
from waggle.experiments.e2_oracle import OracleError, TaskEvent


def _event(
    no: int,
    task: str,
    kind: str,
    state: str,
    token: int,
    *,
    tick: int = 0,
    expires: int | None = None,
    worker: str | None = "w1",
) -> TaskEvent:
    return TaskEvent(no, task, kind, state, token, worker, expires, tick)


def _claim(no: int, task: str, token: int, tick: int) -> TaskEvent:
    return _event(no, task, "claimed", "ASSIGNED", token, tick=tick, expires=tick + 10)


def test_a_clean_delivery_counts_nothing() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "executing", "EXECUTING", 1, tick=1, expires=10),
        _event(3, "d", "handoff", "DONE", 1, tick=2),
    )
    assert judge_handoffs(events, {}) == HandoffReport(0, 0, 0, 1)


def test_a_stale_handoff_while_another_attempt_is_live_is_a_double_delivery() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "recovered", "APPROVED", 1, tick=20, expires=None, worker=None),
        _claim(3, "d", 2, 21),
        _event(4, "d", "executing", "EXECUTING", 2, tick=22, expires=31),
        _event(5, "d", "handoff", "DONE", 1, tick=23),
    )
    assert judge_handoffs(events, {}) == HandoffReport(1, 1, 0, 1)


def test_a_second_accepted_handoff_for_one_task_is_a_double_delivery() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "handoff", "DONE", 1, tick=2),
        _event(3, "d", "handoff", "DONE", 1, tick=3),
    )
    assert judge_handoffs(events, {}) == HandoffReport(1, 1, 0, 2)


def test_a_stale_handoff_with_no_live_attempt_is_stale_but_not_a_double_delivery() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "recovered", "APPROVED", 1, tick=20, expires=None, worker=None),
        _event(3, "d", "handoff", "DONE", 1, tick=21),
    )
    assert judge_handoffs(events, {}) == HandoffReport(0, 1, 0, 1)


def test_a_dependent_claimed_after_a_stale_handoff_is_unblocked_early() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "recovered", "APPROVED", 1, tick=20, expires=None, worker=None),
        _claim(3, "d", 2, 21),
        _event(4, "d", "handoff", "DONE", 1, tick=23),
        _claim(5, "r", 1, 24),
    )
    assert judge_handoffs(events, {"r": "d"}) == HandoffReport(1, 1, 1, 1)


def test_a_dependent_claimed_after_a_fenced_handoff_is_not_counted() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "handoff", "DONE", 1, tick=2),
        _claim(3, "r", 1, 3),
    )
    assert judge_handoffs(events, {"r": "d"}) == HandoffReport(0, 0, 0, 1)


def test_other_write_kinds_are_not_handoffs() -> None:
    events = (
        _claim(1, "d", 1, 0),
        _event(2, "d", "executing", "EXECUTING", 7, tick=1, expires=10),
        _event(3, "d", "done", "DONE", 7, tick=2),
    )
    assert judge_handoffs(events, {}) == HandoffReport(0, 0, 0, 0)


def test_events_out_of_order_are_undecided() -> None:
    events = (_claim(2, "d", 1, 0), _event(2, "d", "handoff", "DONE", 1, tick=1))
    with pytest.raises(OracleError):
        judge_handoffs(events, {})


def test_a_claim_without_an_expiry_is_undecided() -> None:
    with pytest.raises(OracleError):
        judge_handoffs((_event(1, "d", "claimed", "ASSIGNED", 1),), {})
