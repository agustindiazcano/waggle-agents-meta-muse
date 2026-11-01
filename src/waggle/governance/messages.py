"""Fixed schema for inter-robot messages (ADR-055).

A message is data about the sender's own state. It carries no authority: it has exactly three
fields, the sender must be the authenticated caller, and anything else is rejected, never
ignored. ``parse_robot_message`` is pure and fails closed.
"""

import json
import re
from typing import Final, Literal

from waggle.governance.sanitizers import MAX_CHARS, UntrustedSource

MessageCode = Literal[
    "too_long",
    "not_an_object",
    "duplicate_key",
    "unknown_field",
    "missing_field",
    "bad_type",
    "bad_value",
    "sender_mismatch",
    "self_addressed",
]

# The status list is an assumption to calibrate against the robot states the planner needs.
STATUSES: Final[frozenset[str]] = frozenset({"waiting", "ready", "blocked", "done", "fault"})
_FIELDS: Final[frozenset[str]] = frozenset({"sender", "recipient", "status"})
_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class MessageRejected(ValueError):
    """A message was refused. ``code`` is the reason; the text never echoes message content."""

    def __init__(self, code: MessageCode) -> None:
        super().__init__(code)
        self.code: MessageCode = code


class RobotMessage:
    """A validated message."""

    __slots__ = ("recipient", "sender", "status")

    def __init__(self, sender: str, recipient: str, status: str) -> None:
        self.sender = sender
        self.recipient = recipient
        self.status = status

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RobotMessage):
            return NotImplemented
        return (self.sender, self.recipient, self.status) == (
            other.sender,
            other.recipient,
            other.status,
        )

    def __hash__(self) -> int:
        return hash((self.sender, self.recipient, self.status))


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise MessageRejected("duplicate_key")
        out[key] = value
    return out


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        raise MessageRejected("bad_type")
    if _ID.fullmatch(value) is None:
        raise MessageRejected("bad_value")
    return value


def parse_robot_message(raw: str, authenticated_sender: str) -> RobotMessage:
    """Validate ``raw`` as a status message sent by ``authenticated_sender`` or raise."""
    if _ID.fullmatch(authenticated_sender) is None:
        raise MessageRejected("sender_mismatch")
    if len(raw) > MAX_CHARS[UntrustedSource.ROBOT_MESSAGE]:
        raise MessageRejected("too_long")
    try:
        body = json.loads(raw, object_pairs_hook=_no_duplicates)
    except json.JSONDecodeError:
        raise MessageRejected("not_an_object") from None
    if not isinstance(body, dict):
        raise MessageRejected("not_an_object")
    if set(body) - _FIELDS:
        raise MessageRejected("unknown_field")
    if _FIELDS - set(body):
        raise MessageRejected("missing_field")
    sender = _identifier(body["sender"])
    recipient = _identifier(body["recipient"])
    status = body["status"]
    if not isinstance(status, str):
        raise MessageRejected("bad_type")
    if status not in STATUSES:
        raise MessageRejected("bad_value")
    if sender != authenticated_sender:
        raise MessageRejected("sender_mismatch")
    if recipient == sender:
        raise MessageRejected("self_addressed")
    return RobotMessage(sender, recipient, status)
