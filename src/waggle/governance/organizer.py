"""Organizer governance contract: strict output schema, input screening and loop detector.

The per-robot organizer decides inside its assigned task (sub-step order, yielding, status
messages to peers, or bounded MCP tool calls under its own robot identity). It cannot widen a
fast-layer limit, forge a sender, or attach another robot's identity or token to a tool call.
Turn caps, message caps and loop detection are enforced in code.
"""

import json
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Literal

from waggle.governance.advisor_input import (
    UNKNOWN,
    UNSCORED,
    InboundMessage,
    TrustedFacts,
)
from waggle.governance.caution import ASK_CODES
from waggle.governance.classifier import GuardClassifier, classify_input
from waggle.governance.guard import GuardOutcome
from waggle.governance.messages import (
    STATUSES,
    MessageRejected,
    parse_robot_message,
)
from waggle.governance.sanitizers import SanitizeError, UntrustedSource, fence, sanitize

MAX_ORGANIZER_CHARS: Final = 1024
MAX_TOOL_ARGS: Final = 8
ALLOWED_ORGANIZER_TOOLS: Final[frozenset[str]] = frozenset(
    {"move_waypoint", "release_zone", "get_task", "get_inventory", "reserve_part"}
)
FORBIDDEN_ARG_KEYS: Final[frozenset[str]] = frozenset(
    {"robot_id", "token", "fencing_token", "chassis"}
)
_FIELDS: Final[frozenset[str]] = frozenset(
    {"action", "duration_ticks", "tool", "arguments", "recipient", "status"}
)
_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_ARG_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")

OrganizerCode = Literal[
    "too_long",
    "not_an_object",
    "duplicate_key",
    "unknown_field",
    "missing_field",
    "bad_type",
    "bad_value",
    "disallowed_tool",
    "forbidden_arg",
    "self_addressed",
    "bad_input",
    "prompt_too_large",
    "turn_cap",
    "message_cap",
    "loop_detected",
    "too_soon",
]


class OrganizerAction(StrEnum):
    """Closed vocabulary of organizer actions."""

    NONE = "none"
    YIELD_HOLD = "yield_hold"
    CALL_TOOL = "call_tool"
    SEND_MESSAGE = "send_message"


class OrganizerRejected(ValueError):
    """An organizer output, input or turn was refused. Never echoes untrusted content."""

    def __init__(self, code: OrganizerCode) -> None:
        super().__init__(code)
        self.code: OrganizerCode = code


@dataclass(frozen=True)
class OrganizerLimits:
    """Bounds on organizer prompts, intervals, turns, messages and loop detection."""

    max_prompt_chars: int
    min_interval_ticks: int
    max_turns_per_task: int
    max_messages_per_task: int
    max_identical_repeats: int
    h_max_ticks: int

    def __post_init__(self) -> None:
        values = (
            self.max_prompt_chars,
            self.min_interval_ticks,
            self.max_turns_per_task,
            self.max_messages_per_task,
            self.max_identical_repeats,
            self.h_max_ticks,
        )
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in values):
            raise ValueError("organizer limits must be positive integers")


ArgScalar = str | int | float | bool


@dataclass(frozen=True)
class ParsedOrganizerDecision:
    """Validated organizer proposal."""

    action: OrganizerAction
    duration_ticks: int | None
    tool: str | None
    arguments: tuple[tuple[str, ArgScalar], ...] | None
    recipient: str | None
    status: str | None

    def arguments_dict(self) -> dict[str, ArgScalar]:
        """Return the validated tool arguments as a plain dict."""
        if self.arguments is None:
            return {}
        return dict(self.arguments)

    def signature(self) -> tuple[object, ...]:
        """Canonical hashable signature for loop detection."""
        return (
            self.action.value,
            self.duration_ticks,
            self.tool,
            self.arguments,
            self.recipient,
            self.status,
        )


@dataclass
class OrganizerTaskState:
    """Per-robot, per-task turn, message and loop state."""

    turns: int = 0
    messages_sent: int = 0
    last_tick: int | None = None
    recent_signatures: list[tuple[object, ...]] = field(default_factory=list)


@dataclass(frozen=True)
class OrganizerInput:
    """Built organizer prompt and list of dropped inbound messages."""

    prompt: str
    dropped: tuple[tuple[str, str], ...]
    unscored_signal: bool


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise OrganizerRejected("duplicate_key")
        out[key] = value
    return out


def _no_constant(_name: str) -> object:
    raise OrganizerRejected("bad_value")


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        raise OrganizerRejected("bad_type")
    if _ID.fullmatch(value) is None:
        raise OrganizerRejected("bad_value")
    return value


def _load(raw: str) -> dict[str, object]:
    if not isinstance(raw, str):
        raise OrganizerRejected("bad_type")
    if len(raw) > MAX_ORGANIZER_CHARS:
        raise OrganizerRejected("too_long")
    try:
        body = json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except (json.JSONDecodeError, RecursionError):
        raise OrganizerRejected("not_an_object") from None
    if not isinstance(body, dict):
        raise OrganizerRejected("not_an_object")
    if set(body) - _FIELDS:
        raise OrganizerRejected("unknown_field")
    if _FIELDS - set(body):
        raise OrganizerRejected("missing_field")
    return body


def _parse_arg_value(val: object) -> ArgScalar:
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if not math.isfinite(val):
            raise OrganizerRejected("bad_value")
        return val
    if isinstance(val, str):
        if _ID.fullmatch(val) is None:
            raise OrganizerRejected("bad_value")
        return val
    raise OrganizerRejected("bad_type")


def _parse_tool_args(raw_args: object) -> tuple[tuple[str, ArgScalar], ...]:
    if not isinstance(raw_args, dict):
        raise OrganizerRejected("bad_type")
    if len(raw_args) > MAX_TOOL_ARGS:
        raise OrganizerRejected("bad_value")
    pairs: list[tuple[str, ArgScalar]] = []
    for k, v in sorted(raw_args.items()):
        if not isinstance(k, str) or _ARG_KEY.fullmatch(k) is None:
            raise OrganizerRejected("bad_value")
        if k in FORBIDDEN_ARG_KEYS:
            raise OrganizerRejected("forbidden_arg")
        pairs.append((k, _parse_arg_value(v)))
    return tuple(pairs)


def parse_organizer_output(
    raw: str, limits: OrganizerLimits, *, owner_robot: str
) -> ParsedOrganizerDecision:
    """Validate raw model output against the strict organizer schema or raise OrganizerRejected."""
    owner = _identifier(owner_robot)
    body = _load(raw)
    raw_action = body["action"]
    if not isinstance(raw_action, str) or raw_action not in {a.value for a in OrganizerAction}:
        raise OrganizerRejected("bad_value")
    action = OrganizerAction(raw_action)

    if action is OrganizerAction.NONE:
        if any(
            body[k] is not None
            for k in ("duration_ticks", "tool", "arguments", "recipient", "status")
        ):
            raise OrganizerRejected("bad_value")
        return ParsedOrganizerDecision(action, None, None, None, None, None)

    if action is OrganizerAction.YIELD_HOLD:
        if any(body[k] is not None for k in ("tool", "arguments", "recipient", "status")):
            raise OrganizerRejected("bad_value")
        dur = body["duration_ticks"]
        if isinstance(dur, bool) or not isinstance(dur, int):
            raise OrganizerRejected("bad_type")
        if dur < 1 or dur > limits.h_max_ticks:
            raise OrganizerRejected("bad_value")
        return ParsedOrganizerDecision(action, dur, None, None, None, None)

    if action is OrganizerAction.CALL_TOOL:
        if any(body[k] is not None for k in ("duration_ticks", "recipient", "status")):
            raise OrganizerRejected("bad_value")
        tool = body["tool"]
        if not isinstance(tool, str):
            raise OrganizerRejected("bad_type")
        if tool not in ALLOWED_ORGANIZER_TOOLS:
            raise OrganizerRejected("disallowed_tool")
        args = _parse_tool_args(body["arguments"])
        return ParsedOrganizerDecision(action, None, tool, args, None, None)

    # SEND_MESSAGE
    if any(body[k] is not None for k in ("duration_ticks", "tool", "arguments")):
        raise OrganizerRejected("bad_value")
    recipient = _identifier(body["recipient"])
    if recipient == owner:
        raise OrganizerRejected("self_addressed")
    status = body["status"]
    if not isinstance(status, str):
        raise OrganizerRejected("bad_type")
    if status not in STATUSES:
        raise OrganizerRejected("bad_value")
    # Verify round-trip against the canonical robot message schema
    msg_raw = json.dumps(
        {"sender": owner, "recipient": recipient, "status": status},
        sort_keys=True,
        separators=(",", ":"),
    )
    parse_robot_message(msg_raw, owner)
    return ParsedOrganizerDecision(action, None, None, None, recipient, status)


def outbound_message_json(decision: ParsedOrganizerDecision, *, owner_robot: str) -> str:
    """Serialize a validated SEND_MESSAGE decision as a canonical RobotMessage JSON string."""
    if (
        decision.action is not OrganizerAction.SEND_MESSAGE
        or decision.recipient is None
        or decision.status is None
    ):
        raise OrganizerRejected("bad_input")
    owner = _identifier(owner_robot)
    raw = json.dumps(
        {"sender": owner, "recipient": decision.recipient, "status": decision.status},
        sort_keys=True,
        separators=(",", ":"),
    )
    parse_robot_message(raw, owner)
    return raw


def check_turn_allowed(
    limits: OrganizerLimits, state: OrganizerTaskState, *, now_tick: int
) -> None:
    """Verify interval and turn bounds before an organizer model call."""
    if isinstance(now_tick, bool) or not isinstance(now_tick, int) or now_tick < 0:
        raise OrganizerRejected("bad_input")
    if state.last_tick is not None and now_tick < state.last_tick:
        raise OrganizerRejected("bad_input")
    if state.last_tick is not None and (now_tick - state.last_tick) < limits.min_interval_ticks:
        raise OrganizerRejected("too_soon")
    if state.turns >= limits.max_turns_per_task:
        raise OrganizerRejected("turn_cap")


def record_decision(
    limits: OrganizerLimits,
    state: OrganizerTaskState,
    decision: ParsedOrganizerDecision,
    *,
    now_tick: int,
) -> None:
    """Check message cap and loop detection, then update ``state``."""
    check_turn_allowed(limits, state, now_tick=now_tick)
    if (
        decision.action is OrganizerAction.SEND_MESSAGE
        and state.messages_sent >= limits.max_messages_per_task
    ):
        raise OrganizerRejected("message_cap")
    sig = decision.signature()
    if decision.action is not OrganizerAction.NONE:
        tail = state.recent_signatures[-limits.max_identical_repeats :]
        if len(tail) == limits.max_identical_repeats and all(item == sig for item in tail):
            raise OrganizerRejected("loop_detected")
    state.turns += 1
    state.last_tick = now_tick
    if decision.action is OrganizerAction.SEND_MESSAGE:
        state.messages_sent += 1
    state.recent_signatures.append(sig)


def _token(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise OrganizerRejected("bad_input")
    return value


def _number(value: float) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise OrganizerRejected("bad_input")
    return f"{value:.2f}"


def _facts_lines(facts: TrustedFacts, ask_signals: tuple[str, ...]) -> str:
    for sig in ask_signals:
        if not isinstance(sig, str) or sig not in ASK_CODES:
            raise OrganizerRejected("bad_input")
    step = UNKNOWN if facts.task_step is None else _token(facts.task_step)
    occluded = UNKNOWN if facts.occluded is None else str(bool(facts.occluded))
    geofences = UNKNOWN if facts.geofences is None else ",".join(_token(g) for g in facts.geofences)
    leases = (
        UNKNOWN
        if facts.lease_holders is None
        else ",".join(f"{_token(c)}:{_token(h)}" for c, h in facts.lease_holders)
    )
    signals = "none" if not ask_signals else ",".join(ask_signals)
    lines = [
        f"robot={_token(facts.robot_id)} chassis={_token(facts.chassis)}",
        f"speed={_number(facts.speed)} zone={_token(facts.zone)} step={step}",
        f"nearest_distance={_number(facts.nearest_distance)} occluded={occluded}",
        "active_reasons=" + ",".join(_token(r) for r in facts.active_reasons),
        "geofences=" + geofences,
        f"lease_holders={leases}",
        f"advisor_signals={signals}",
    ]
    return "\n".join(lines)


async def _screen_message(
    message: InboundMessage, robot_id: str, classifier: GuardClassifier
) -> tuple[str | None, str | None]:
    try:
        parsed = parse_robot_message(message.raw, message.authenticated_sender)
    except MessageRejected as exc:
        return None, exc.code
    if parsed.recipient != robot_id:
        return None, "wrong_recipient"
    res = await classify_input(message.raw, UntrustedSource.ROBOT_MESSAGE, classifier)
    if res.outcome is not GuardOutcome.PASS:
        return None, UNSCORED
    try:
        clean = sanitize(
            f"sender={parsed.sender} status={parsed.status}", UntrustedSource.ROBOT_MESSAGE
        )
    except SanitizeError:
        return None, UNSCORED
    return fence(clean), None


async def build_organizer_input(
    facts: TrustedFacts,
    messages: list[InboundMessage],
    ask_signals: tuple[str, ...],
    classifier: GuardClassifier,
    limits: OrganizerLimits,
    *,
    max_messages: int,
) -> OrganizerInput:
    """Build the organizer context block after screening all inbound messages."""
    if isinstance(max_messages, bool) or not isinstance(max_messages, int) or max_messages < 1:
        raise OrganizerRejected("bad_input")
    head = _facts_lines(facts, ask_signals)
    blocks: list[str] = []
    dropped: list[tuple[str, str]] = []
    unscored = False
    for index, msg in enumerate(messages):
        if index >= max_messages:
            dropped.append((msg.authenticated_sender, "too_many_messages"))
            continue
        block, reason = await _screen_message(msg, facts.robot_id, classifier)
        if block is not None:
            blocks.append(block)
        elif reason is not None:
            dropped.append((msg.authenticated_sender, reason))
            if reason == UNSCORED:
                unscored = True
    prompt = "\n".join(["[trusted facts]", head, *blocks])
    if len(prompt) > limits.max_prompt_chars:
        raise OrganizerRejected("prompt_too_large")
    return OrganizerInput(prompt, tuple(dropped), unscored)
