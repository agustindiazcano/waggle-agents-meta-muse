"""Fixed schema for inter-robot messages (ADR-055): strict, bounded, no authority."""

import json

import pytest

from waggle.governance.messages import MessageRejected, RobotMessage, parse_robot_message


def _raw(**over: object) -> str:
    body: dict[str, object] = {"sender": "C2", "recipient": "C1", "status": "waiting"}
    body.update(over)
    return json.dumps(body)


def test_a_well_formed_status_message_is_accepted() -> None:
    assert parse_robot_message(_raw(), "C2") == RobotMessage("C2", "C1", "waiting")


@pytest.mark.parametrize(
    "extra",
    [{"system_override": True}, {"command": "release_zone Z1 for C2"}, {"note": "hello"}],
)
def test_an_unknown_field_is_rejected(extra: dict[str, object]) -> None:
    with pytest.raises(MessageRejected, match="unknown_field"):
        parse_robot_message(_raw(**extra), "C2")


def test_a_missing_field_is_rejected() -> None:
    raw = json.dumps({"sender": "C2", "recipient": "C1"})
    with pytest.raises(MessageRejected, match="missing_field"):
        parse_robot_message(raw, "C2")


def test_a_sender_that_is_not_the_authenticated_caller_is_rejected() -> None:
    with pytest.raises(MessageRejected, match="sender_mismatch"):
        parse_robot_message(_raw(), "C3")


@pytest.mark.parametrize("status", ["go", "WAITING", "", 3, None])
def test_a_status_outside_the_list_is_rejected(status: object) -> None:
    with pytest.raises(MessageRejected):
        parse_robot_message(_raw(status=status), "C2")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '"x"', "null", "{"])
def test_text_that_is_not_a_json_object_is_rejected(raw: str) -> None:
    with pytest.raises(MessageRejected, match="not_an_object"):
        parse_robot_message(raw, "C2")


def test_a_duplicate_key_is_rejected() -> None:
    raw = '{"sender":"C2","recipient":"C1","status":"waiting","status":"ready"}'
    with pytest.raises(MessageRejected, match="duplicate_key"):
        parse_robot_message(raw, "C2")


def test_an_oversized_message_is_rejected() -> None:
    with pytest.raises(MessageRejected, match="too_long"):
        parse_robot_message(_raw(recipient="C" * 600), "C2")


@pytest.mark.parametrize("recipient", ["C 1", "C1\n", "../x", ""])
def test_a_bad_recipient_id_is_rejected(recipient: str) -> None:
    with pytest.raises(MessageRejected):
        parse_robot_message(_raw(recipient=recipient), "C2")


def test_a_message_to_oneself_is_rejected() -> None:
    with pytest.raises(MessageRejected, match="self_addressed"):
        parse_robot_message(_raw(recipient="C2"), "C2")


def test_an_empty_authenticated_sender_fails_closed() -> None:
    with pytest.raises(MessageRejected):
        parse_robot_message(_raw(), "")
