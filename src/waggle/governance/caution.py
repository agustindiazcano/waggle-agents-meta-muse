"""Closed caution vocabulary and strict parser for advisor output (ADVISORS_DESIGN 4, 5, 7).

A model proposes, code validates. The vocabulary can only reduce motion: a speed cap that never
exceeds the current cap, a hold that expires, a coded request to the organizer, or nothing.
Pure functions and frozen records. Time is given as ticks by the caller, never read here.
"""

import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

CautionCode = Literal[
    "too_long",
    "not_an_object",
    "duplicate_key",
    "unknown_field",
    "missing_field",
    "missing_field_value",
    "missing_expiry",
    "bad_type",
    "bad_value",
    "widening",
    "bad_input",
    "no_caution",
]

MAX_OUTPUT_CHARS: Final = 1024
# The closed list of organizer signals is an assumption to calibrate with the organizer design.
ASK_CODES: Final[frozenset[str]] = frozenset(
    {"yield", "replan", "neighbor_fault", "unscored_input"}
)
_FIELDS: Final[frozenset[str]] = frozenset({"action", "speed_cap", "duration_ticks", "code"})
_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class CautionAction(StrEnum):
    """The closed set of advisor actions."""

    SLOW = "slow"
    HOLD = "hold"
    ASK_ORGANIZER = "ask_organizer"
    NONE = "none"


class CautionRejected(ValueError):
    """An advisor output or event was refused. The text never echoes model content."""

    def __init__(self, code: CautionCode) -> None:
        super().__init__(code)
        self.code: CautionCode = code


@dataclass(frozen=True)
class CautionConfig:
    """Bounds on cautions. Values are configuration to calibrate, none is a default."""

    max_window_ticks: int
    h_max_ticks: int
    n_max_holds: int

    def __post_init__(self) -> None:
        if self.max_window_ticks < 1 or self.h_max_ticks < 1 or self.n_max_holds < 1:
            raise ValueError("caution bounds must be positive")
        if self.h_max_ticks > self.max_window_ticks:
            raise ValueError("h_max_ticks must not exceed max_window_ticks")


@dataclass(frozen=True)
class ParsedCaution:
    """A validated advisor proposal. Fields not used by the action are None."""

    action: CautionAction
    speed_cap: float | None
    duration_ticks: int | None
    code: str | None


@dataclass(frozen=True)
class CautionEvent:
    """An accepted caution bound to one robot, with the ticks that make a replay exact."""

    run_id: str
    robot_id: str
    issue_tick: int
    effective_tick: int
    expiry_tick: int
    action: CautionAction
    speed_cap: float | None
    code: str | None
    call_request_id: str
    validator_verdict: str


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise CautionRejected("duplicate_key")
        out[key] = value
    return out


def _no_constant(_name: str) -> object:
    raise CautionRejected("bad_value")


def _load(raw: str) -> dict[str, object]:
    if len(raw) > MAX_OUTPUT_CHARS:
        raise CautionRejected("too_long")
    try:
        body = json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except (json.JSONDecodeError, RecursionError):
        raise CautionRejected("not_an_object") from None
    if not isinstance(body, dict):
        raise CautionRejected("not_an_object")
    if set(body) - _FIELDS:
        raise CautionRejected("unknown_field")
    if _FIELDS - set(body):
        raise CautionRejected("missing_field")
    return body


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CautionRejected("bad_type")
    number = float(value)
    if not math.isfinite(number):
        raise CautionRejected("bad_value")
    return number


def _ticks(value: object, limit: int) -> int:
    if value is None:
        raise CautionRejected("missing_expiry")
    if isinstance(value, bool) or not isinstance(value, int):
        raise CautionRejected("bad_type")
    if value < 1 or value > limit:
        raise CautionRejected("bad_value")
    return value


def _slow(
    body: dict[str, object], config: CautionConfig, current: float, cap: float
) -> ParsedCaution:
    if body["speed_cap"] is None:
        raise CautionRejected("missing_field_value")
    speed = _number(body["speed_cap"])
    if speed < 0.0:
        raise CautionRejected("bad_value")
    if speed > current or speed > cap:
        raise CautionRejected("widening")
    duration = _ticks(body["duration_ticks"], config.max_window_ticks)
    if body["code"] is not None:
        raise CautionRejected("bad_value")
    return ParsedCaution(CautionAction.SLOW, speed, duration, None)


def _hold(body: dict[str, object], config: CautionConfig) -> ParsedCaution:
    duration = _ticks(body["duration_ticks"], config.h_max_ticks)
    if body["speed_cap"] is not None or body["code"] is not None:
        raise CautionRejected("bad_value")
    return ParsedCaution(CautionAction.HOLD, 0.0, duration, None)


def _ask(body: dict[str, object]) -> ParsedCaution:
    code = body["code"]
    if body["speed_cap"] is not None or body["duration_ticks"] is not None:
        raise CautionRejected("bad_value")
    if not isinstance(code, str) or code not in ASK_CODES:
        raise CautionRejected("bad_value")
    return ParsedCaution(CautionAction.ASK_ORGANIZER, None, None, code)


def parse_advisor_output(
    raw: str, config: CautionConfig, *, current_cap: float, class_max: float
) -> ParsedCaution:
    """Validate model output or raise CautionRejected.

    ``current_cap`` is the effective cap the caller holds for the robot and ``class_max`` the
    chassis class maximum. A value above either is rejected, never clamped.
    """
    if not (math.isfinite(current_cap) and math.isfinite(class_max)):
        raise CautionRejected("bad_input")
    if current_cap < 0.0 or class_max < 0.0:
        raise CautionRejected("bad_input")
    body = _load(raw)
    action = body["action"]
    if not isinstance(action, str) or action not in {a.value for a in CautionAction}:
        raise CautionRejected("bad_value")
    kind = CautionAction(action)
    if kind is CautionAction.SLOW:
        return _slow(body, config, current_cap, class_max)
    if kind is CautionAction.HOLD:
        return _hold(body, config)
    if kind is CautionAction.ASK_ORGANIZER:
        return _ask(body)
    if any(body[name] is not None for name in ("speed_cap", "duration_ticks", "code")):
        raise CautionRejected("bad_value")
    return ParsedCaution(CautionAction.NONE, None, None, None)


def _tick(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CautionRejected("bad_input")
    return value


def _identifier(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise CautionRejected("bad_input")
    return value


def build_event(
    parsed: ParsedCaution,
    *,
    run_id: str,
    robot_id: str,
    issue_tick: int,
    latency_ticks: int,
    request_id: str,
) -> CautionEvent:
    """Bind an accepted proposal to the caller's robot and to ticks.

    ``robot_id`` comes from the authenticated owner of the advisor instance, never from model
    output. ``effective_tick`` is ``issue_tick + latency_ticks``. An ask signal has no motion
    window, so its expiry equals its effective tick.
    """
    if parsed.action is CautionAction.NONE:
        raise CautionRejected("no_caution")
    issue = _tick(issue_tick)
    effective = issue + _tick(latency_ticks)
    expiry = effective + (parsed.duration_ticks or 0)
    return CautionEvent(
        run_id=_identifier(run_id),
        robot_id=_identifier(robot_id),
        issue_tick=issue,
        effective_tick=effective,
        expiry_tick=expiry,
        action=parsed.action,
        speed_cap=parsed.speed_cap,
        code=parsed.code,
        call_request_id=_identifier(request_id),
        validator_verdict="accepted",
    )
