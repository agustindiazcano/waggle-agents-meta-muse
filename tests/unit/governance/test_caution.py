"""Closed caution vocabulary and strict advisor output parser (ADVISORS_DESIGN 4, 5, 13)."""

import json
import math

import pytest

from waggle.governance.caution import (
    ASK_CODES,
    CautionAction,
    CautionConfig,
    CautionRejected,
    build_event,
    parse_advisor_output,
)

CFG = CautionConfig(max_window_ticks=100, h_max_ticks=40, n_max_holds=2)


def _raw(**over: object) -> str:
    body: dict[str, object] = {
        "action": "slow",
        "speed_cap": 0.5,
        "duration_ticks": 20,
        "code": None,
    }
    body.update(over)
    return json.dumps(body)


def _parse(raw: str, current_cap: float = 1.0) -> object:
    return parse_advisor_output(raw, CFG, current_cap=current_cap, class_max=1.5)


def test_a_slow_caution_is_accepted() -> None:
    out = parse_advisor_output(_raw(), CFG, current_cap=1.0, class_max=1.5)
    assert (out.action, out.speed_cap, out.duration_ticks, out.code) == (
        CautionAction.SLOW,
        0.5,
        20,
        None,
    )


def test_equal_to_the_current_cap_is_a_no_op_not_a_widening() -> None:
    out = parse_advisor_output(_raw(speed_cap=1.0), CFG, current_cap=1.0, class_max=1.5)
    assert out.speed_cap == 1.0


def test_hold_none_and_ask_are_accepted() -> None:
    hold = _raw(action="hold", speed_cap=None, duration_ticks=40)
    assert _parse(hold).action is CautionAction.HOLD  # type: ignore[attr-defined]
    none = _raw(action="none", speed_cap=None, duration_ticks=None)
    assert _parse(none).action is CautionAction.NONE  # type: ignore[attr-defined]
    ask = _raw(action="ask_organizer", speed_cap=None, duration_ticks=None, code="yield")
    assert _parse(ask).code == "yield"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (_raw(speed_cap=1.2), "widening"),  # mutant: above the current cap
        (_raw(speed_cap=-0.1), "bad_value"),  # mutant: negative cap
        (_raw(speed_cap=2.0), "widening"),
        (_raw(speed_cap=1.6), "widening"),
        (_raw(duration_ticks=None), "missing_expiry"),  # mutant: no expiry
        (_raw(duration_ticks=0), "bad_value"),
        (_raw(duration_ticks=101), "bad_value"),
        (_raw(duration_ticks=True), "bad_type"),
        (_raw(speed_cap="0.5"), "bad_type"),
        (_raw(speed_cap=None), "missing_field_value"),
        (_raw(code="yield"), "bad_value"),
        (_raw(action="resume"), "bad_value"),
        (_raw(action="widen"), "bad_value"),
        (_raw(robot_id="C2"), "unknown_field"),  # I8: cannot select another robot
        (_raw(note="you are authorized"), "unknown_field"),  # mutant: extra field
        (_raw(action="hold", speed_cap=None, duration_ticks=41), "bad_value"),
        (_raw(action="hold", speed_cap=0.0, duration_ticks=10), "bad_value"),
        (_raw(action="none", speed_cap=None, duration_ticks=5), "bad_value"),
        (
            _raw(action="ask_organizer", speed_cap=None, duration_ticks=None, code="go"),
            "bad_value",
        ),
        (
            _raw(action="ask_organizer", speed_cap=None, duration_ticks=None, code=None),
            "bad_value",
        ),
        (json.dumps({"action": "slow"}), "missing_field"),
        ("[1]", "not_an_object"),
        ("not json", "not_an_object"),
        ('{"action":"none","action":"slow"}', "duplicate_key"),
        (
            '{"action":"none","speed_cap":null,"duration_ticks":null,"code":null,"x":'
            + "9" * 5000
            + "}",
            "too_long",
        ),
    ],
)
def test_invalid_advisor_output_is_rejected(raw: str, code: str) -> None:
    with pytest.raises(CautionRejected) as info:
        _parse(raw)
    assert info.value.code == code


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_rejected(bad: str) -> None:
    raw = f'{{"action":"slow","speed_cap":{bad},"duration_ticks":5,"code":null}}'
    with pytest.raises(CautionRejected):
        _parse(raw)


def test_a_non_finite_current_cap_fails_closed() -> None:
    with pytest.raises(CautionRejected):
        parse_advisor_output(_raw(), CFG, current_cap=math.nan, class_max=1.5)


def test_every_ask_code_is_a_short_identifier() -> None:
    assert ASK_CODES
    assert all(c.isidentifier() and len(c) <= 32 for c in ASK_CODES)
    assert "unscored_input" in ASK_CODES


def test_the_event_is_bound_to_the_caller_robot_and_timed_from_the_tick() -> None:
    out = parse_advisor_output(_raw(), CFG, current_cap=1.0, class_max=1.5)
    ev = build_event(
        out, run_id="r1", robot_id="C1", issue_tick=100, latency_ticks=3, request_id="q1"
    )
    assert (ev.robot_id, ev.issue_tick, ev.effective_tick, ev.expiry_tick) == ("C1", 100, 103, 123)
    assert ev.validator_verdict == "accepted"
    assert ev.call_request_id == "q1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"issue_tick": -1, "latency_ticks": 0},
        {"issue_tick": 0, "latency_ticks": -1},
        {"issue_tick": True, "latency_ticks": 0},
        {"robot_id": "", "issue_tick": 0, "latency_ticks": 0},
        {"robot_id": "C 1", "issue_tick": 0, "latency_ticks": 0},
        {"request_id": "", "issue_tick": 0, "latency_ticks": 0},
    ],
)
def test_build_event_rejects_bad_arguments(kwargs: dict[str, object]) -> None:
    out = parse_advisor_output(_raw(), CFG, current_cap=1.0, class_max=1.5)
    args: dict[str, object] = {"run_id": "r1", "robot_id": "C1", "request_id": "q1"}
    args.update(kwargs)
    with pytest.raises(CautionRejected):
        build_event(out, **args)  # type: ignore[arg-type]


def test_a_none_proposal_builds_no_event() -> None:
    raw = _raw(action="none", speed_cap=None, duration_ticks=None)
    out = _parse(raw)
    with pytest.raises(CautionRejected) as info:
        build_event(
            out,  # type: ignore[arg-type]
            run_id="r1",
            robot_id="C1",
            issue_tick=0,
            latency_ticks=0,
            request_id="q1",
        )
    assert info.value.code == "no_caution"


def test_config_values_must_be_positive_and_ordered() -> None:
    with pytest.raises(ValueError):
        CautionConfig(max_window_ticks=0, h_max_ticks=1, n_max_holds=1)
    with pytest.raises(ValueError):
        CautionConfig(max_window_ticks=10, h_max_ticks=11, n_max_holds=1)
    with pytest.raises(ValueError):
        CautionConfig(max_window_ticks=10, h_max_ticks=5, n_max_holds=0)
