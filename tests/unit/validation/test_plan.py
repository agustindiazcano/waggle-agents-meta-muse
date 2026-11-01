"""Strict plan schema, the contract between the planner and the validator (ADR-059)."""

import copy
import json

import pytest

from waggle.validation.plan import Plan, PlanContext, PlanNode, PlanRejected, parse_plan

CONTEXT = PlanContext(
    robot_max_speed_mps={"C1": 1.5, "F1": 2.0},
    items=frozenset({"ITEM-17"}),
    zones=frozenset({"Z1", "Z2", "DOCK"}),
)

NODE = {
    "label": "n1",
    "robot_id": "C1",
    "item_id": "ITEM-17",
    "target_zone_id": "DOCK",
    "action": "PICK",
    "corridor_zone_ids": ["Z1"],
    "avoid_zone_ids": ["Z2"],
    "wait_for": [],
    "speed_cap_mps": 1.0,
}
PLAN = {"nodes": [NODE], "rationale": "pick via Z1", "escalate": False, "escalation_reason": None}


def _plan(**over: object) -> dict[str, object]:
    body = copy.deepcopy(PLAN)
    body.update(over)
    return body


def _node(**over: object) -> dict[str, object]:
    body = copy.deepcopy(NODE)
    body.update(over)
    return body


def _parse(body: object, mission: str = "m-1") -> Plan:
    return parse_plan(json.dumps(body), mission, CONTEXT)


def test_a_valid_plan_is_accepted_with_the_mission_set_by_code() -> None:
    plan = _parse(PLAN)
    assert plan.mission_id == "m-1"
    assert plan.nodes == (
        PlanNode("n1", "C1", "ITEM-17", "DOCK", "PICK", ("Z1",), ("Z2",), (), 1.0),
    )
    assert plan.escalate is False


@pytest.mark.parametrize(
    "extra",
    [
        {"execute_python": "disable_all_checks()", "validator_override": True},
        {"mission_id": "forged"},
        {"task_id": "t-1"},
    ],
)
def test_unknown_plan_fields_are_rejected_including_a_model_supplied_mission(
    extra: dict[str, object],
) -> None:
    with pytest.raises(PlanRejected, match="unknown_field"):
        _parse(_plan(**extra))


def test_unknown_node_fields_are_rejected() -> None:
    with pytest.raises(PlanRejected, match="unknown_field"):
        _parse(_plan(nodes=[_node(idempotency_key="k-1")]))


@pytest.mark.parametrize("missing", ["nodes", "rationale", "escalate", "escalation_reason"])
def test_a_missing_plan_field_is_rejected(missing: str) -> None:
    body = _plan()
    del body[missing]
    with pytest.raises(PlanRejected, match="missing_field"):
        _parse(body)


@pytest.mark.parametrize("raw", ["", "nope", "[]", "null", "{", '{"a":1,"a":2}'])
def test_text_that_is_not_one_json_object_is_rejected(raw: str) -> None:
    with pytest.raises(PlanRejected):
        parse_plan(raw, "m-1", CONTEXT)


def test_more_than_twenty_nodes_are_rejected() -> None:
    nodes = [_node(label=f"n{i}") for i in range(21)]
    with pytest.raises(PlanRejected, match="too_many_nodes"):
        _parse(_plan(nodes=nodes))


def test_duplicate_labels_are_rejected() -> None:
    with pytest.raises(PlanRejected, match="duplicate_label"):
        _parse(_plan(nodes=[_node(), _node()]))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("robot_id", "X9"),
        ("item_id", "ITEM-99"),
        ("target_zone_id", "Z9"),
        ("corridor_zone_ids", ["Z9"]),
        ("avoid_zone_ids", ["Z9"]),
        ("action", "SELF_DESTRUCT"),
        ("action", "pick"),
    ],
)
def test_ids_and_actions_outside_the_fleet_inventory_and_map_are_rejected(
    field: str, value: object
) -> None:
    with pytest.raises(PlanRejected, match=r"unknown_reference|bad_value"):
        _parse(_plan(nodes=[_node(**{field: value})]))


@pytest.mark.parametrize("cap", [0, -1.0, 2.5, float("inf"), True, "fast"])
def test_a_speed_cap_must_be_above_zero_and_not_above_the_robot_maximum(cap: object) -> None:
    with pytest.raises(PlanRejected):
        parse_plan(json.dumps(_plan(nodes=[_node(speed_cap_mps=cap)])), "m-1", CONTEXT)


def test_a_null_speed_cap_is_accepted() -> None:
    assert _parse(_plan(nodes=[_node(speed_cap_mps=None)])).nodes[0].speed_cap_mps is None


def test_wait_for_must_name_existing_labels() -> None:
    with pytest.raises(PlanRejected, match="unknown_reference"):
        _parse(_plan(nodes=[_node(wait_for=["n9"])]))


def test_wait_for_cycles_are_rejected() -> None:
    nodes = [_node(label="a", wait_for=["b"]), _node(label="b", wait_for=["a"])]
    with pytest.raises(PlanRejected, match="cycle"):
        _parse(_plan(nodes=nodes))
    with pytest.raises(PlanRejected, match="cycle"):
        _parse(_plan(nodes=[_node(label="a", wait_for=["a"])]))


def test_an_acyclic_dependency_chain_is_accepted() -> None:
    nodes = [
        _node(label="a"),
        _node(label="b", wait_for=["a"]),
        _node(label="c", wait_for=["a", "b"]),
    ]
    assert len(_parse(_plan(nodes=nodes)).nodes) == 3


def test_a_zone_cannot_be_both_required_corridor_and_avoided() -> None:
    with pytest.raises(PlanRejected, match="conflicting_zone"):
        _parse(_plan(nodes=[_node(corridor_zone_ids=["Z1"], avoid_zone_ids=["Z1"])]))


@pytest.mark.parametrize("action", ["PICK", "DELIVER", "HANDOFF"])
def test_actions_on_an_item_require_one(action: str) -> None:
    with pytest.raises(PlanRejected, match="missing_field"):
        _parse(_plan(nodes=[_node(action=action, item_id=None)]))


@pytest.mark.parametrize("action", ["MOVE", "DISPATCH_REPAIR"])
def test_actions_without_an_item_reject_one(action: str) -> None:
    with pytest.raises(PlanRejected, match="bad_value"):
        _parse(_plan(nodes=[_node(action=action)]))


def test_escalation_needs_a_reason_from_the_list_and_no_reason_otherwise() -> None:
    assert _parse(_plan(nodes=[], escalate=True, escalation_reason="no_feasible_plan")).escalate
    with pytest.raises(PlanRejected):
        _parse(_plan(escalate=True, escalation_reason=None))
    with pytest.raises(PlanRejected):
        _parse(_plan(escalate=True, escalation_reason="because"))
    with pytest.raises(PlanRejected):
        _parse(_plan(escalate=False, escalation_reason="no_feasible_plan"))


def test_the_rationale_is_bounded_text() -> None:
    with pytest.raises(PlanRejected):
        _parse(_plan(rationale="x" * 2001))
    with pytest.raises(PlanRejected):
        _parse(_plan(rationale=5))


def test_a_bad_mission_id_fails_closed() -> None:
    with pytest.raises(PlanRejected):
        parse_plan(json.dumps(PLAN), "bad id", CONTEXT)


def test_a_rejection_never_echoes_the_offending_text() -> None:
    secret = "disable_all_checks()"
    with pytest.raises(PlanRejected) as error:
        _parse(_plan(execute_python=secret))
    assert secret not in str(error.value)
