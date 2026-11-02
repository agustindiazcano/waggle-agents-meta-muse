"""Recorded caution event log and exact replay (ADVISORS_DESIGN 7).

The harness, outside ``waggle.sim`` and ``waggle.control``, appends accepted events here. The log
holds only events that had an effect, so the same seed and the same serialized log give the same
per-tick event lists. Every event is validated again at the gate and at load time. Ticks are
arguments; nothing here reads a clock.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Final, Literal

from waggle.governance.caution import (
    ASK_CODES,
    CautionAction,
    CautionConfig,
    CautionEvent,
    CautionRejected,
)

LogCode = Literal["robot_mismatch", "invalid_event", "muted", "duplicate_request", "out_of_order"]
_FIELDS: Final[tuple[str, ...]] = (
    "run_id",
    "robot_id",
    "issue_tick",
    "effective_tick",
    "expiry_tick",
    "action",
    "speed_cap",
    "code",
    "call_request_id",
    "validator_verdict",
)
_ID_CHARS: Final = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")


class LogRejected(ValueError):
    """An event was refused at the gate. It is counted and logged, and has no effect."""

    def __init__(self, code: LogCode) -> None:
        super().__init__(code)
        self.code: LogCode = code


def _is_id(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 64 and all(c in _ID_CHARS for c in value)


def _is_tick(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _window_ok(event: CautionEvent, config: CautionConfig) -> bool:
    window = event.expiry_tick - event.effective_tick
    cap = event.speed_cap
    if event.action is CautionAction.SLOW:
        finite = isinstance(cap, float) and math.isfinite(cap) and cap >= 0.0
        return finite and 1 <= window <= config.max_window_ticks and event.code is None
    if event.action is CautionAction.HOLD:
        return cap == 0.0 and 1 <= window <= config.h_max_ticks and event.code is None
    if event.action is CautionAction.ASK_ORGANIZER:
        return cap is None and window == 0 and event.code in ASK_CODES
    return False


def validate_event(event: CautionEvent, config: CautionConfig) -> None:
    """Raise CautionRejected unless the event is well formed and inside the bounds."""
    ticks = (event.issue_tick, event.effective_tick, event.expiry_tick)
    ok = (
        _is_id(event.run_id)
        and _is_id(event.robot_id)
        and _is_id(event.call_request_id)
        and all(_is_tick(t) for t in ticks)
        and isinstance(event.action, CautionAction)
        and event.validator_verdict == "accepted"
    )
    if not ok or not (event.issue_tick <= event.effective_tick <= event.expiry_tick):
        raise CautionRejected("bad_value")
    if not _window_ok(event, config):
        raise CautionRejected("bad_value")


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise CautionRejected("duplicate_key")
        out[key] = value
    return out


def _no_constant(_name: str) -> object:
    raise CautionRejected("bad_value")


def _event_from_line(line: str) -> CautionEvent:
    try:
        body = json.loads(line, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except (json.JSONDecodeError, RecursionError):
        raise CautionRejected("not_an_object") from None
    if not isinstance(body, dict):
        raise CautionRejected("not_an_object")
    if set(body) != set(_FIELDS):
        raise CautionRejected("unknown_field" if set(body) - set(_FIELDS) else "missing_field")
    action = body["action"]
    if not isinstance(action, str) or action not in {a.value for a in CautionAction}:
        raise CautionRejected("bad_value")
    cap = body["speed_cap"]
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, (int, float))):
        raise CautionRejected("bad_type")
    code = body["code"]
    if code is not None and not isinstance(code, str):
        raise CautionRejected("bad_type")
    for name in ("issue_tick", "effective_tick", "expiry_tick"):
        if not _is_tick(body[name]):
            raise CautionRejected("bad_type")
    return CautionEvent(
        run_id=str(body["run_id"]),
        robot_id=str(body["robot_id"]),
        issue_tick=int(body["issue_tick"]),  # checked above
        effective_tick=int(body["effective_tick"]),
        expiry_tick=int(body["expiry_tick"]),
        action=CautionAction(action),
        speed_cap=None if cap is None else float(cap),
        code=code,
        call_request_id=str(body["call_request_id"]),
        validator_verdict=str(body["validator_verdict"]),
    )


def _line(event: CautionEvent) -> str:
    record = {name: getattr(event, name) for name in _FIELDS}
    record["action"] = event.action.value
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


@dataclass
class CautionLog:
    """Append-only log of accepted events plus a separate list of rejections."""

    config: CautionConfig
    _events: list[CautionEvent] = field(default_factory=list)
    _rejections: list[tuple[str, int, str]] = field(default_factory=list)
    _requests: set[str] = field(default_factory=set)
    _last_issue: dict[str, int] = field(default_factory=dict)
    _holds: dict[tuple[str, str], int] = field(default_factory=dict)

    @property
    def events(self) -> tuple[CautionEvent, ...]:
        """Accepted events in append order."""
        return tuple(self._events)

    @property
    def rejections(self) -> tuple[tuple[str, int, str], ...]:
        """Rejected submissions as (owner robot, issue tick, code). Not used for replay."""
        return tuple(self._rejections)

    def _refuse(self, owner: str, event: CautionEvent, code: LogCode) -> LogRejected:
        self._rejections.append((owner, event.issue_tick, code))
        return LogRejected(code)

    def submit(self, event: CautionEvent, *, owner_robot: str, task_id: str) -> None:
        """Append ``event`` or raise LogRejected.

        ``owner_robot`` is the authenticated owner of the advisor instance. After
        ``n_max_holds`` consecutive holds in a task the advisor is muted for that task.
        """
        if event.robot_id != owner_robot:
            raise self._refuse(owner_robot, event, "robot_mismatch")
        try:
            validate_event(event, self.config)
        except CautionRejected:
            raise self._refuse(owner_robot, event, "invalid_event") from None
        key = (owner_robot, task_id)
        if self._holds.get(key, 0) >= self.config.n_max_holds:
            raise self._refuse(owner_robot, event, "muted")
        if event.call_request_id in self._requests:
            raise self._refuse(owner_robot, event, "duplicate_request")
        if event.issue_tick < self._last_issue.get(owner_robot, 0):
            raise self._refuse(owner_robot, event, "out_of_order")
        self._events.append(event)
        self._requests.add(event.call_request_id)
        self._last_issue[owner_robot] = event.issue_tick
        is_hold = event.action is CautionAction.HOLD
        self._holds[key] = self._holds.get(key, 0) + 1 if is_hold else 0

    def active_at(self, robot_id: str, tick: int) -> tuple[CautionEvent, ...]:
        """Motion cautions of ``robot_id`` in force at ``tick``, in append order."""
        motion = (CautionAction.SLOW, CautionAction.HOLD)
        return tuple(
            e
            for e in self._events
            if e.robot_id == robot_id
            and e.action in motion
            and e.effective_tick <= tick < e.expiry_tick
        )

    def to_jsonl(self) -> str:
        """Canonical serialization: one sorted-key JSON object per line."""
        return "\n".join(_line(e) for e in self._events)

    def digest(self) -> str:
        """SHA-256 of the canonical serialization, for the result file."""
        return hashlib.sha256(self.to_jsonl().encode("utf-8")).hexdigest()

    @classmethod
    def from_jsonl(cls, text: str, config: CautionConfig) -> "CautionLog":
        """Load a stored log, validating every event again. Any bad line raises."""
        log = cls(config)
        for line in text.splitlines():
            event = _event_from_line(line)
            validate_event(event, config)
            if event.call_request_id in log._requests:
                raise CautionRejected("duplicate_key")
            log._events.append(event)
            log._requests.add(event.call_request_id)
        return log
