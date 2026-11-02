"""Recorded caution event log: binding, hold budget, exact replay (ADVISORS_DESIGN 4, 7, 13)."""

import json

import pytest

from waggle.governance.caution import (
    CautionAction,
    CautionConfig,
    CautionEvent,
    CautionRejected,
)
from waggle.governance.caution_log import CautionLog, LogRejected

CFG = CautionConfig(max_window_ticks=100, h_max_ticks=40, n_max_holds=2)


def _ev(
    action: CautionAction = CautionAction.SLOW,
    *,
    robot: str = "C1",
    issue: int = 10,
    latency: int = 2,
    window: int = 20,
    cap: float | None = 0.5,
    code: str | None = None,
    request: str = "q1",
) -> CautionEvent:
    effective = issue + latency
    return CautionEvent(
        run_id="r1",
        robot_id=robot,
        issue_tick=issue,
        effective_tick=effective,
        expiry_tick=effective + window,
        action=action,
        speed_cap=0.0 if action is CautionAction.HOLD else cap,
        code=code,
        call_request_id=request,
        validator_verdict="accepted",
    )


def _hold(issue: int, request: str) -> CautionEvent:
    return _ev(CautionAction.HOLD, issue=issue, window=5, request=request)


def test_an_accepted_event_is_active_only_inside_its_window() -> None:
    log = CautionLog(CFG)
    log.submit(_ev(), owner_robot="C1", task_id="t1")
    assert log.active_at("C1", 11) == ()
    assert [e.call_request_id for e in log.active_at("C1", 12)] == ["q1"]
    assert len(log.active_at("C1", 31)) == 1
    assert log.active_at("C1", 32) == ()
    assert log.active_at("C2", 20) == ()


def test_i8_an_event_for_another_robot_is_rejected_and_logged() -> None:
    log = CautionLog(CFG)
    with pytest.raises(LogRejected) as info:
        log.submit(_ev(robot="C2"), owner_robot="C1", task_id="t1")
    assert info.value.code == "robot_mismatch"
    assert log.events == ()
    assert log.rejections == (("C1", 10, "robot_mismatch"),)


def test_a_repeated_request_id_is_not_logged_twice() -> None:
    log = CautionLog(CFG)
    log.submit(_ev(), owner_robot="C1", task_id="t1")
    with pytest.raises(LogRejected) as info:
        log.submit(_ev(issue=50), owner_robot="C1", task_id="t1")
    assert info.value.code == "duplicate_request"
    assert len(log.events) == 1


def test_an_event_from_the_past_is_rejected() -> None:
    log = CautionLog(CFG)
    log.submit(_ev(issue=50, request="q2"), owner_robot="C1", task_id="t1")
    with pytest.raises(LogRejected) as info:
        log.submit(_ev(issue=40, request="q3"), owner_robot="C1", task_id="t1")
    assert info.value.code == "out_of_order"


@pytest.mark.parametrize(
    "bad",
    [
        _ev(window=0),
        _ev(window=101),
        _ev(cap=-0.1),
        _ev(cap=None),
        _ev(cap=float("nan")),
        _ev(CautionAction.NONE),
        _ev(CautionAction.HOLD, window=41),
        _ev(CautionAction.ASK_ORGANIZER, window=0, cap=None, code="go"),
    ],
)
def test_the_gate_revalidates_the_event_itself(bad: CautionEvent) -> None:
    log = CautionLog(CFG)
    with pytest.raises(LogRejected) as info:
        log.submit(bad, owner_robot="C1", task_id="t1")
    assert info.value.code == "invalid_event"
    assert log.events == ()


def test_i9_after_n_max_consecutive_holds_the_advisor_is_muted_for_the_task() -> None:
    log = CautionLog(CFG)
    log.submit(_hold(10, "a"), owner_robot="C1", task_id="t1")
    log.submit(_hold(30, "b"), owner_robot="C1", task_id="t1")
    with pytest.raises(LogRejected) as info:
        log.submit(_hold(50, "c"), owner_robot="C1", task_id="t1")
    assert info.value.code == "muted"
    with pytest.raises(LogRejected):
        log.submit(_ev(issue=60, request="d"), owner_robot="C1", task_id="t1")
    assert len(log.events) == 2
    log.submit(_hold(70, "e"), owner_robot="C1", task_id="t2")  # a new task starts clean


def test_a_slow_event_resets_the_consecutive_hold_count() -> None:
    log = CautionLog(CFG)
    log.submit(_hold(10, "a"), owner_robot="C1", task_id="t1")
    log.submit(_ev(issue=30, request="b"), owner_robot="C1", task_id="t1")
    log.submit(_hold(60, "c"), owner_robot="C1", task_id="t1")
    log.submit(_hold(80, "d"), owner_robot="C1", task_id="t1")
    assert len(log.events) == 4


def test_i7_replay_of_the_serialized_log_gives_the_same_events_and_digest() -> None:
    log = CautionLog(CFG)
    log.submit(_ev(), owner_robot="C1", task_id="t1")
    log.submit(_hold(60, "b"), owner_robot="C1", task_id="t1")
    ask = _ev(CautionAction.ASK_ORGANIZER, issue=90, window=0, cap=None, code="yield", request="c")
    log.submit(ask, owner_robot="C1", task_id="t1")
    text = log.to_jsonl()
    again = CautionLog.from_jsonl(text, CFG)
    assert again.events == log.events
    assert again.digest() == log.digest()
    assert again.to_jsonl() == text
    for tick in range(0, 120):
        assert again.active_at("C1", tick) == log.active_at("C1", tick)


def test_rejections_are_not_part_of_the_replay_log() -> None:
    log = CautionLog(CFG)
    with pytest.raises(LogRejected):
        log.submit(_ev(robot="C2"), owner_robot="C1", task_id="t1")
    assert log.to_jsonl() == ""
    assert CautionLog.from_jsonl("", CFG).events == ()


@pytest.mark.parametrize("mutation", ["extra", "drop", "type", "dup", "bad_action", "junk"])
def test_a_tampered_log_line_fails_closed(mutation: str) -> None:
    log = CautionLog(CFG)
    log.submit(_ev(), owner_robot="C1", task_id="t1")
    record = json.loads(log.to_jsonl())
    if mutation == "extra":
        record["tool"] = "move_waypoint"
    elif mutation == "drop":
        del record["expiry_tick"]
    elif mutation == "type":
        record["issue_tick"] = "10"
    elif mutation == "bad_action":
        record["action"] = "widen"
    text = json.dumps(record)
    if mutation == "dup":
        text = text[:-1] + ', "run_id": "r2"}'
    if mutation == "junk":
        text = "not json"
    with pytest.raises(CautionRejected):
        CautionLog.from_jsonl(text, CFG)


def test_a_replayed_event_that_widens_beyond_the_config_is_refused() -> None:
    log = CautionLog(CFG)
    log.submit(_ev(), owner_robot="C1", task_id="t1")
    record = json.loads(log.to_jsonl())
    record["expiry_tick"] = record["effective_tick"] + 10_000
    with pytest.raises(CautionRejected):
        CautionLog.from_jsonl(json.dumps(record), CFG)
