"""Strict plan schema: the contract between the planner and the validator (ADR-059).

``parse_plan`` is pure and fails closed. The plan is model output, so it is data: it must be
one JSON object with exactly the documented fields. Unknown fields are rejected, never ignored,
so a field such as ``validator_override`` cannot be carried along. The mission id is set by code
and a model-supplied one is an unknown field. Ids are checked against the fleet, the inventory
and the map in ``PlanContext``. Errors carry a code and never the offending text.
"""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

PlanCode = Literal[
    "not_an_object",
    "duplicate_key",
    "unknown_field",
    "missing_field",
    "bad_type",
    "bad_value",
    "unknown_reference",
    "too_many_nodes",
    "duplicate_label",
    "cycle",
    "conflicting_zone",
    "bad_mission",
]

MAX_NODES: Final = 20
_MAX_ZONES_PER_NODE: Final = 20
_RATIONALE_MAX: Final = 2000
_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
ACTIONS: Final[frozenset[str]] = frozenset(
    {"MOVE", "PICK", "HANDOFF", "DELIVER", "DISPATCH_REPAIR"}
)
_ITEM_ACTIONS: Final[frozenset[str]] = frozenset({"PICK", "HANDOFF", "DELIVER"})
# The reason list is an assumption to calibrate against the replanning loop (ADR-023).
ESCALATION_REASONS: Final[frozenset[str]] = frozenset(
    {"no_feasible_plan", "unsafe_state", "needs_operator"}
)
_PLAN_FIELDS: Final[frozenset[str]] = frozenset(
    {"nodes", "rationale", "escalate", "escalation_reason"}
)
_NODE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "label",
        "robot_id",
        "item_id",
        "target_zone_id",
        "action",
        "corridor_zone_ids",
        "avoid_zone_ids",
        "wait_for",
        "speed_cap_mps",
    }
)


class PlanRejected(ValueError):
    """The plan was refused. ``code`` is the reason; the text never echoes plan content."""

    def __init__(self, code: PlanCode) -> None:
        super().__init__(code)
        self.code: PlanCode = code


@dataclass(frozen=True)
class PlanContext:
    """What the plan may refer to. ``robot_max_speed_mps`` keys are the fleet."""

    robot_max_speed_mps: Mapping[str, float]
    items: frozenset[str]
    zones: frozenset[str]


@dataclass(frozen=True)
class PlanNode:
    """One validated step."""

    label: str
    robot_id: str
    item_id: str | None
    target_zone_id: str
    action: str
    corridor_zone_ids: tuple[str, ...]
    avoid_zone_ids: tuple[str, ...]
    wait_for: tuple[str, ...]
    speed_cap_mps: float | None


@dataclass(frozen=True)
class Plan:
    """A validated plan. ``rationale`` is for the operator log and is never sent to a model."""

    mission_id: str
    nodes: tuple[PlanNode, ...]
    rationale: str
    escalate: bool
    escalation_reason: str | None


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise PlanRejected("duplicate_key")
        out[key] = value
    return out


def _no_constant(_name: str) -> object:
    raise PlanRejected("bad_value")


def _fields(body: object, allowed: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(body, dict):
        raise PlanRejected("bad_type")
    if set(body) - allowed:
        raise PlanRejected("unknown_field")
    if allowed - set(body):
        raise PlanRejected("missing_field")
    return body


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        raise PlanRejected("bad_type")
    if _ID.fullmatch(value) is None:
        raise PlanRejected("bad_value")
    return value


def _known(value: object, known: frozenset[str]) -> str:
    name = _identifier(value)
    if name not in known:
        raise PlanRejected("unknown_reference")
    return name


def _zones(value: object, known: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PlanRejected("bad_type")
    if len(value) > _MAX_ZONES_PER_NODE:
        raise PlanRejected("bad_value")
    return tuple(_known(zone, known) for zone in value)


def _speed(value: object, limit: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PlanRejected("bad_type")
    if not math.isfinite(value) or value <= 0 or value > limit:
        raise PlanRejected("bad_value")
    return float(value)


def _node(body: object, context: PlanContext) -> PlanNode:
    fields = _fields(body, _NODE_FIELDS)
    robot = _known(fields["robot_id"], frozenset(context.robot_max_speed_mps))
    action = fields["action"]
    if not isinstance(action, str):
        raise PlanRejected("bad_type")
    if action not in ACTIONS:
        raise PlanRejected("bad_value")
    raw_item = fields["item_id"]
    if action in _ITEM_ACTIONS:
        if raw_item is None:
            raise PlanRejected("missing_field")
        item: str | None = _known(raw_item, context.items)
    elif raw_item is not None:
        raise PlanRejected("bad_value")
    else:
        item = None
    corridor = _zones(fields["corridor_zone_ids"], context.zones)
    avoid = _zones(fields["avoid_zone_ids"], context.zones)
    if set(corridor) & set(avoid):
        raise PlanRejected("conflicting_zone")
    waits = fields["wait_for"]
    if not isinstance(waits, list):
        raise PlanRejected("bad_type")
    return PlanNode(
        _identifier(fields["label"]),
        robot,
        item,
        _known(fields["target_zone_id"], context.zones),
        action,
        corridor,
        avoid,
        tuple(_identifier(w) for w in waits),
        _speed(fields["speed_cap_mps"], context.robot_max_speed_mps[robot]),
    )


def _check_dependencies(nodes: tuple[PlanNode, ...]) -> None:
    labels = [n.label for n in nodes]
    if len(set(labels)) != len(labels):
        raise PlanRejected("duplicate_label")
    waits = {n.label: n.wait_for for n in nodes}
    if any(w not in waits for ws in waits.values() for w in ws):
        raise PlanRejected("unknown_reference")
    done: set[str] = set()
    pending = dict(waits)
    while pending:
        ready = [label for label, ws in pending.items() if all(w in done for w in ws)]
        if not ready:
            raise PlanRejected("cycle")
        for label in ready:
            done.add(label)
            del pending[label]


def parse_plan(raw: str, mission_id: str, context: PlanContext) -> Plan:
    """Validate ``raw`` model output as a plan for ``mission_id`` or raise PlanRejected."""
    if not isinstance(mission_id, str) or _ID.fullmatch(mission_id) is None:
        raise PlanRejected("bad_mission")
    try:
        body = json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except (json.JSONDecodeError, TypeError):
        raise PlanRejected("not_an_object") from None
    if not isinstance(body, dict):
        raise PlanRejected("not_an_object")
    fields = _fields(body, _PLAN_FIELDS)
    raw_nodes = fields["nodes"]
    if not isinstance(raw_nodes, list):
        raise PlanRejected("bad_type")
    if len(raw_nodes) > MAX_NODES:
        raise PlanRejected("too_many_nodes")
    nodes = tuple(_node(n, context) for n in raw_nodes)
    _check_dependencies(nodes)
    rationale = fields["rationale"]
    if not isinstance(rationale, str):
        raise PlanRejected("bad_type")
    if len(rationale) > _RATIONALE_MAX:
        raise PlanRejected("bad_value")
    escalate, reason = fields["escalate"], fields["escalation_reason"]
    if not isinstance(escalate, bool):
        raise PlanRejected("bad_type")
    if escalate != (reason is not None):
        raise PlanRejected("bad_value")
    if reason is not None and reason not in ESCALATION_REASONS:
        raise PlanRejected("bad_value")
    return Plan(mission_id, nodes, rationale, escalate, reason)
