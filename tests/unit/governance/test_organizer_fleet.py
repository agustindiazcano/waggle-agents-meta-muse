"""Fleet proposals reuse strict plans, with bounded executable semantics."""

import json

import pytest

from waggle.coordination.routing import AisleGraph, AisleNode
from waggle.governance.organizer_fleet import validate_fleet_plan
from waggle.sim.params import RobotKind
from waggle.sim.scenarios import load_map
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan import PlanContext
from waggle.validation.plan_rollout import RolloutConfig

STATIC = StaticMap(
    load_map("A"),
    AisleGraph((AisleNode("start", 3, 3),), ()),
    {"corridor_s": "start"},
    {"robot-0": "start"},
    1.0,
)
CONTEXT = PlanContext({"robot-0": 1.5}, frozenset(), frozenset({"corridor_s"}))
CONFIG = RolloutConfig({"robot-0": RobotKind.CARRIER}, frozenset(), 0.5, horizon_s=0.1)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("empty", None),
        ("escalate", "escalated"),
        ("dependency", "unsupported_execution"),
        ("oversize", "too_long"),
    ],
)
def test_only_executable_bounded_plans_have_paths(case: str, reason: str | None) -> None:
    nodes: list[dict[str, object]] = []
    if case == "dependency":
        node: dict[str, object] = {
            "label": "a",
            "robot_id": "robot-0",
            "action": "MOVE",
            "item_id": None,
            "target_zone_id": "corridor_s",
            "corridor_zone_ids": [],
            "avoid_zone_ids": [],
            "speed_cap_mps": None,
            "wait_for": [],
        }
        nodes = [node, {**node, "label": "b", "wait_for": ["a"]}]
    raw = json.dumps(
        {
            "nodes": nodes,
            "rationale": "test",
            "escalate": case == "escalate",
            "escalation_reason": "needs_operator" if case == "escalate" else None,
        }
    )
    result = validate_fleet_plan(
        raw,
        mission_id="mission",
        context=CONTEXT,
        static=STATIC,
        config=CONFIG,
        max_response_chars=1 if case == "oversize" else 2048,
    )
    assert result.reason == reason
    assert (result.plan is not None) == (reason is None)
    assert result.paths == ()
