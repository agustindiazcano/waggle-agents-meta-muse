"""Tests for the organizer governance contract, schema, message screening and loop detection."""

import asyncio
import json

import pytest

from waggle.governance.advisor_input import InboundMessage, TrustedFacts
from waggle.governance.classifier import MockClassifier
from waggle.governance.organizer import (
    OrganizerAction,
    OrganizerInput,
    OrganizerLimits,
    OrganizerRejected,
    OrganizerTaskState,
    build_organizer_input,
    check_turn_allowed,
    outbound_message_json,
    parse_organizer_output,
    record_decision,
)

LIMITS = OrganizerLimits(
    max_prompt_chars=2000,
    min_interval_ticks=5,
    max_turns_per_task=4,
    max_messages_per_task=2,
    max_identical_repeats=2,
    h_max_ticks=40,
)

FACTS = TrustedFacts(
    robot_id="robot-0",
    chassis="carrier",
    speed=1.2,
    active_reasons=("REQUEST",),
    zone="aisle_1",
    task_step="travel",
    nearest_distance=2.5,
    occluded=False,
    geofences=(),
    lease_holders=(("corridor_1", "robot-1"),),
)


def _raw(
    action: str = "none",
    *,
    duration_ticks: object = None,
    tool: object = None,
    arguments: object = None,
    recipient: object = None,
    status: object = None,
) -> str:
    return json.dumps(
        {
            "action": action,
            "duration_ticks": duration_ticks,
            "tool": tool,
            "arguments": arguments,
            "recipient": recipient,
            "status": status,
        }
    )


def test_parse_valid_none_yield_tool_and_message_decisions() -> None:
    none_dec = parse_organizer_output(_raw("none"), LIMITS, owner_robot="robot-0")
    assert none_dec.action is OrganizerAction.NONE
    assert none_dec.duration_ticks is None

    hold_dec = parse_organizer_output(
        _raw("yield_hold", duration_ticks=20), LIMITS, owner_robot="robot-0"
    )
    assert hold_dec.action is OrganizerAction.YIELD_HOLD
    assert hold_dec.duration_ticks == 20

    tool_dec = parse_organizer_output(
        _raw("call_tool", tool="release_zone", arguments={"zone_id": "corridor_1"}),
        LIMITS,
        owner_robot="robot-0",
    )
    assert tool_dec.action is OrganizerAction.CALL_TOOL
    assert tool_dec.tool == "release_zone"
    assert tool_dec.arguments_dict() == {"zone_id": "corridor_1"}

    msg_dec = parse_organizer_output(
        _raw("send_message", recipient="robot-1", status="waiting"),
        LIMITS,
        owner_robot="robot-0",
    )
    assert msg_dec.action is OrganizerAction.SEND_MESSAGE
    assert msg_dec.recipient == "robot-1"
    assert msg_dec.status == "waiting"
    raw_msg = outbound_message_json(msg_dec, owner_robot="robot-0")
    assert json.loads(raw_msg) == {
        "sender": "robot-0",
        "recipient": "robot-1",
        "status": "waiting",
    }


def test_parse_rejects_extra_fields_duplicates_and_oversize() -> None:
    extra = json.dumps(
        {
            "action": "none",
            "duration_ticks": None,
            "tool": None,
            "arguments": None,
            "recipient": None,
            "status": None,
            "override": True,
        }
    )
    with pytest.raises(OrganizerRejected) as exc:
        parse_organizer_output(extra, LIMITS, owner_robot="robot-0")
    assert exc.value.code == "unknown_field"

    dup = (
        '{"action":"none","action":"none","duration_ticks":null,'
        '"tool":null,"arguments":null,"recipient":null,"status":null}'
    )
    with pytest.raises(OrganizerRejected) as exc:
        parse_organizer_output(dup, LIMITS, owner_robot="robot-0")
    assert exc.value.code == "duplicate_key"

    with pytest.raises(OrganizerRejected) as exc:
        parse_organizer_output("x" * 2000, LIMITS, owner_robot="robot-0")
    assert exc.value.code == "too_long"


def test_parse_rejects_disallowed_tools_and_identity_spoofing_arguments() -> None:
    with pytest.raises(OrganizerRejected) as exc:
        parse_organizer_output(
            _raw("call_tool", tool="create_purchase_order", arguments={"part_id": "P1"}),
            LIMITS,
            owner_robot="robot-0",
        )
    assert exc.value.code == "disallowed_tool"

    for forbidden_key in ("robot_id", "token", "fencing_token", "chassis"):
        with pytest.raises(OrganizerRejected) as exc:
            parse_organizer_output(
                _raw("call_tool", tool="release_zone", arguments={forbidden_key: "spoof"}),
                LIMITS,
                owner_robot="robot-0",
            )
        assert exc.value.code == "forbidden_arg"


def test_parse_rejects_self_addressed_message_and_invalid_hold_duration() -> None:
    with pytest.raises(OrganizerRejected) as exc:
        parse_organizer_output(
            _raw("send_message", recipient="robot-0", status="waiting"),
            LIMITS,
            owner_robot="robot-0",
        )
    assert exc.value.code == "self_addressed"

    with pytest.raises(OrganizerRejected) as exc:
        parse_organizer_output(
            _raw("yield_hold", duration_ticks=LIMITS.h_max_ticks + 1),
            LIMITS,
            owner_robot="robot-0",
        )
    assert exc.value.code == "bad_value"


def test_turn_cap_message_cap_interval_and_loop_detection() -> None:
    state = OrganizerTaskState()
    check_turn_allowed(LIMITS, state, now_tick=0)

    msg = parse_organizer_output(
        _raw("send_message", recipient="robot-1", status="waiting"),
        LIMITS,
        owner_robot="robot-0",
    )
    record_decision(LIMITS, state, msg, now_tick=0)

    # Calling again before min_interval_ticks is rejected as too_soon
    with pytest.raises(OrganizerRejected) as exc:
        check_turn_allowed(LIMITS, state, now_tick=3)
    assert exc.value.code == "too_soon"

    # Second identical message hits max_identical_repeats=2 -> loop_detected on the third
    check_turn_allowed(LIMITS, state, now_tick=5)
    record_decision(LIMITS, state, msg, now_tick=5)

    hold = parse_organizer_output(
        _raw("yield_hold", duration_ticks=10), LIMITS, owner_robot="robot-0"
    )
    # A third outbound message exceeds max_messages_per_task=2
    msg_other = parse_organizer_output(
        _raw("send_message", recipient="robot-1", status="ready"),
        LIMITS,
        owner_robot="robot-0",
    )
    check_turn_allowed(LIMITS, state, now_tick=10)
    with pytest.raises(OrganizerRejected) as exc:
        record_decision(LIMITS, state, msg_other, now_tick=10)
    assert exc.value.code == "message_cap"

    # Loop detection on repeated identical non-none actions
    loop_state = OrganizerTaskState()
    record_decision(LIMITS, loop_state, hold, now_tick=0)
    record_decision(LIMITS, loop_state, hold, now_tick=5)
    with pytest.raises(OrganizerRejected) as exc:
        record_decision(LIMITS, loop_state, hold, now_tick=10)
    assert exc.value.code == "loop_detected"


def test_turn_cap_enforced_after_max_turns() -> None:
    state = OrganizerTaskState()
    none_dec = parse_organizer_output(_raw("none"), LIMITS, owner_robot="robot-0")
    for i in range(LIMITS.max_turns_per_task):
        tick = i * LIMITS.min_interval_ticks
        check_turn_allowed(LIMITS, state, now_tick=tick)
        record_decision(LIMITS, state, none_dec, now_tick=tick)

    with pytest.raises(OrganizerRejected) as exc:
        check_turn_allowed(
            LIMITS, state, now_tick=LIMITS.max_turns_per_task * LIMITS.min_interval_ticks
        )
    assert exc.value.code == "turn_cap"


def test_build_organizer_input_screens_messages_and_fences_ask_signals() -> None:
    benign_guard = MockClassifier(response='{"label":"benign","reason_code":"ok"}')
    valid_msg = InboundMessage(
        authenticated_sender="robot-1",
        raw='{"sender":"robot-1","recipient":"robot-0","status":"blocked"}',
    )
    forged_msg = InboundMessage(
        authenticated_sender="robot-2",
        raw='{"sender":"robot-1","recipient":"robot-0","status":"blocked"}',
    )
    built: OrganizerInput = asyncio.run(
        build_organizer_input(
            FACTS,
            [valid_msg, forged_msg],
            ("yield",),
            benign_guard,
            LIMITS,
            max_messages=5,
        )
    )
    assert "advisor_signals=yield" in built.prompt
    assert '<untrusted source="robot_message">\nsender=robot-1 status=blocked\n</untrusted>' in (
        built.prompt
    )
    assert ("robot-2", "sender_mismatch") in built.dropped

    # Unknown advisor signal is rejected
    with pytest.raises(OrganizerRejected) as exc:
        asyncio.run(
            build_organizer_input(
                FACTS, [], ("invented_signal",), benign_guard, LIMITS, max_messages=5
            )
        )
    assert exc.value.code == "bad_input"
