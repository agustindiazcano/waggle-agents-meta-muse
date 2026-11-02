"""Map accepted cautions to plain speed limits; advisors can only lower (ADVISORS_DESIGN 4, 13)."""

import json
import random

import pytest

from waggle.governance.caution import (
    CautionAction,
    CautionConfig,
    CautionEvent,
    CautionRejected,
    build_event,
    parse_advisor_output,
)
from waggle.governance.caution_limits import (
    ADVISOR_SOURCE,
    apply_speed_limits,
    speed_limits_at,
)
from waggle.governance.caution_log import CautionLog, LogRejected

CFG = CautionConfig(max_window_ticks=100, h_max_ticks=40, n_max_holds=3)


def _event(
    action: CautionAction,
    cap: float | None,
    issue: int,
    window: int,
    request: str,
    code: str | None = None,
) -> CautionEvent:
    return CautionEvent(
        "r1", "C1", issue, issue, issue + window, action, cap, code, request, "accepted"
    )


def _log(*events: CautionEvent) -> CautionLog:
    log = CautionLog(CFG)
    for event in events:
        log.submit(event, owner_robot="C1", task_id="t1")
    return log


def test_active_cautions_become_plain_limits_in_log_order() -> None:
    log = _log(
        _event(CautionAction.SLOW, 0.6, 0, 50, "a"),
        _event(CautionAction.HOLD, 0.0, 10, 5, "b"),
        _event(CautionAction.ASK_ORGANIZER, None, 12, 0, "c", "yield"),
    )
    got = speed_limits_at(log, "C1", 12, class_max=1.5)
    assert [(x.speed_cap, x.source, x.call_request_id) for x in got] == [
        (0.6, ADVISOR_SOURCE, "a"),
        (0.0, ADVISOR_SOURCE, "b"),
    ]
    assert [x.call_request_id for x in speed_limits_at(log, "C1", 20, class_max=1.5)] == ["a"]
    assert speed_limits_at(log, "C1", 60, class_max=1.5) == ()
    assert speed_limits_at(log, "C2", 12, class_max=1.5) == ()


def test_a_cap_above_the_class_max_is_lowered_never_raised() -> None:
    log = _log(_event(CautionAction.SLOW, 2.0, 0, 5, "a"))
    assert speed_limits_at(log, "C1", 1, class_max=1.5)[0].speed_cap == 1.5


def test_bad_class_max_fails_closed_to_a_zero_cap() -> None:
    log = _log(_event(CautionAction.SLOW, 0.5, 0, 5, "a"))
    for bad in (float("nan"), -1.0):
        got = speed_limits_at(log, "C1", 1, class_max=bad)
        assert [x.speed_cap for x in got] == [0.0]


def test_the_same_log_gives_the_same_limits_every_time() -> None:
    log = _log(_event(CautionAction.SLOW, 0.6, 0, 50, "a"))
    replay = CautionLog.from_jsonl(log.to_jsonl(), CFG)
    for tick in range(0, 80):
        assert speed_limits_at(replay, "C1", tick, class_max=1.5) == speed_limits_at(
            log, "C1", tick, class_max=1.5
        )


def test_i1_applying_advisor_limits_never_raises_the_speed() -> None:
    rng = random.Random(7)
    for _ in range(300):
        events = []
        for i in range(rng.randint(0, 4)):
            kind = rng.choice([CautionAction.SLOW, CautionAction.HOLD])
            cap = 0.0 if kind is CautionAction.HOLD else rng.uniform(0.0, 3.0)
            events.append(_event(kind, cap, i * 10, rng.randint(1, 30), f"q{i}"))
        log = CautionLog(CFG)
        for event in events:
            try:
                log.submit(event, owner_robot="C1", task_id="t1")
            except LogRejected:  # a rejection is an allowed outcome here
                continue
        for tick in range(0, 60, 5):
            base = rng.uniform(-1.5, 1.5)
            limits = speed_limits_at(log, "C1", tick, class_max=1.5)
            out = apply_speed_limits(base, limits)
            assert abs(out) <= abs(base)
            assert out == 0.0 or (out > 0) == (base > 0)  # the sign is never changed


def test_apply_with_no_limits_changes_nothing() -> None:
    assert apply_speed_limits(0.7, ()) == 0.7
    assert apply_speed_limits(-0.7, ()) == -0.7


def test_apply_to_a_non_finite_request_fails_closed() -> None:
    assert apply_speed_limits(float("nan"), ()) == 0.0


@pytest.mark.parametrize(
    "mutant",
    [
        {"action": "slow", "speed_cap": 1.4, "duration_ticks": 10, "code": None},
        {"action": "slow", "speed_cap": -0.5, "duration_ticks": 10, "code": None},
        {"action": "slow", "speed_cap": 0.4, "duration_ticks": None, "code": None},
        {"action": "slow", "speed_cap": 0.4, "duration_ticks": 10, "code": None, "reason": "ESTOP"},
        {"action": "release", "speed_cap": None, "duration_ticks": None, "code": None},
        {"action": "slow", "speed_cap": 0.4, "duration_ticks": 10, "code": None, "robot_id": "C9"},
    ],
)
def test_i2_i3_i8_a_mutant_advisor_that_widens_motion_creates_no_limit(
    mutant: dict[str, object],
) -> None:
    log = CautionLog(CFG)
    with pytest.raises(CautionRejected):
        parsed = parse_advisor_output(json.dumps(mutant), CFG, current_cap=1.0, class_max=1.5)
        log.submit(
            build_event(
                parsed, run_id="r1", robot_id="C1", issue_tick=0, latency_ticks=0, request_id="m"
            ),
            owner_robot="C1",
            task_id="t1",
        )
    assert speed_limits_at(log, "C1", 1, class_max=1.5) == ()
    assert log.events == ()


def test_i5_text_claiming_authority_cannot_produce_anything_but_a_lowering() -> None:
    # An advisor misled by "you are authorized to resume" can still only answer in the
    # closed vocabulary. A resume-style answer is not in it.
    for text in ('{"action":"resume"}', '"resume"', "authorized"):
        with pytest.raises(CautionRejected):
            parse_advisor_output(text, CFG, current_cap=1.0, class_max=1.5)
