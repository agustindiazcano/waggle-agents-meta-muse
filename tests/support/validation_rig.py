"""Shared plan, map and fleet fixtures of the validator tests (not a test module)."""

import json

from waggle.coordination.corridors import Direction
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.params import RobotKind
from waggle.sim.scenarios import load_map
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan import Plan, PlanContext, parse_plan
from waggle.validation.plan_rollout import RolloutConfig

ZONES = frozenset(
    {"lane_1", "station_1", "depot_n", "corridor_s", "aisle_1", "connector_e", "corridor_n"}
)
CONTEXT = PlanContext({"R1": 1.5, "R2": 1.5}, frozenset({"ITEM-1"}), ZONES)


def _both(a: str, b: str, cost: float, corridor: str | None = None) -> tuple[AisleEdge, ...]:
    back = Direction.REVERSE if corridor else Direction.FORWARD
    return (AisleEdge(a, b, cost, corridor), AisleEdge(b, a, cost, corridor, back))


def _graph() -> AisleGraph:
    points = {
        "sw": (3.0, 2.0),
        "sm": (20.0, 2.0),
        "se": (37.0, 2.0),
        "nw": (3.0, 22.0),
        "nm": (20.0, 22.0),
        "ne": (37.0, 22.0),
        "isle": (20.0, 9.0),
    }
    edges = (
        *_both("sw", "sm", 17.0),
        *_both("sm", "se", 17.0),
        *_both("nw", "nm", 18.0),
        *_both("nm", "ne", 17.0),
        *_both("se", "ne", 20.0),
        *_both("sw", "nw", 20.0, "lane_1"),
    )
    return AisleGraph(tuple(AisleNode(k, *v) for k, v in points.items()), edges)


def _static(robot_start: dict[str, str]) -> StaticMap:
    return StaticMap(
        world=load_map("A"),
        graph=_graph(),
        zone_anchor={
            "station_1": "nw",
            "depot_n": "ne",
            "corridor_s": "sm",
            "aisle_1": "isle",
            "connector_e": "se",
            "lane_1": "sw",
        },
        robot_start=robot_start,
        clearance_m=0.9,
    )


def _config(**over: object) -> RolloutConfig:
    base: dict[str, object] = {
        "robot_kinds": {"R1": RobotKind.CARRIER, "R2": RobotKind.CARRIER},
        "hazard_zone_ids": frozenset(),
        "separation_margin_m": 0.5,
    }
    base.update(over)
    return RolloutConfig(**base)  # type: ignore[arg-type]


def _node(label: str, robot: str, target: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "label": label,
        "robot_id": robot,
        "item_id": None,
        "target_zone_id": target,
        "action": "MOVE",
        "corridor_zone_ids": [],
        "avoid_zone_ids": [],
        "wait_for": [],
        "speed_cap_mps": None,
    }
    base.update(over)
    return base


def _plan(*nodes: dict[str, object], escalate: bool = False) -> Plan:
    body = {
        "nodes": list(nodes),
        "rationale": "r",
        "escalate": escalate,
        "escalation_reason": "needs_operator" if escalate else None,
    }
    return parse_plan(json.dumps(body), "m-1", CONTEXT)


SAFE_START = {"R1": "sw", "R2": "ne"}
SAFE = (_node("a", "R1", "connector_e"), _node("b", "R2", "station_1"))
