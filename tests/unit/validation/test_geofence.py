"""Geofence check of a validated plan against trusted hazard zones (ADR-060)."""

import json

from waggle.validation.geofence import Counterexample, check_geofence
from waggle.validation.plan import Plan, PlanContext, parse_plan

CONTEXT = PlanContext(
    robot_max_speed_mps={"C1": 1.5, "F1": 2.0},
    items=frozenset({"ITEM-17"}),
    zones=frozenset({"Z1", "Z2", "Z3", "DOCK"}),
)


def _plan(*nodes: dict[str, object]) -> Plan:
    body = {"nodes": list(nodes), "rationale": "r", "escalate": False, "escalation_reason": None}
    return parse_plan(json.dumps(body), "m-1", CONTEXT)


def _node(label: str = "n1", **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "label": label,
        "robot_id": "F1",
        "item_id": None,
        "target_zone_id": "DOCK",
        "action": "MOVE",
        "corridor_zone_ids": [],
        "avoid_zone_ids": [],
        "wait_for": [],
        "speed_cap_mps": None,
    }
    base.update(over)
    return base


def test_a_plan_outside_the_hazard_zone_has_no_counterexample() -> None:
    assert check_geofence(_plan(_node(corridor_zone_ids=["Z2"])), frozenset({"Z1"})) == ()


def test_a_corridor_through_a_hazard_zone_is_a_geofence_intrusion() -> None:
    plan = _plan(_node(corridor_zone_ids=["Z1"]))
    assert check_geofence(plan, frozenset({"Z1"})) == (
        Counterexample("GEOFENCE_INTRUSION", "n1", "Z1"),
    )


def test_a_target_inside_a_hazard_zone_is_a_geofence_intrusion() -> None:
    plan = _plan(_node(target_zone_id="Z1"))
    assert check_geofence(plan, frozenset({"Z1"})) == (
        Counterexample("GEOFENCE_INTRUSION", "n1", "Z1"),
    )


def test_avoiding_the_hazard_zone_is_accepted() -> None:
    plan = _plan(_node(avoid_zone_ids=["Z1"], corridor_zone_ids=["Z2"]))
    assert check_geofence(plan, frozenset({"Z1"})) == ()


def test_every_offending_node_and_zone_is_listed_in_order() -> None:
    plan = _plan(
        _node("a", corridor_zone_ids=["Z1", "Z3"]),
        _node("b", target_zone_id="Z3"),
    )
    found = check_geofence(plan, frozenset({"Z1", "Z3"}))
    assert [(c.node, c.zone) for c in found] == [("a", "Z1"), ("a", "Z3"), ("b", "Z3")]
