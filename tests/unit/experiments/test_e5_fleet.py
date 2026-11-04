"""C4 executes validated MOVE routes offline while preserving deterministic control."""

import json
from dataclasses import replace

import pytest

from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.experiments.e1_config import BY_NAME
from waggle.experiments.e5_advisors import E5Runner, RunSpec
from waggle.governance.advisor_input import AdvisorInputLimits
from waggle.governance.caution import CautionConfig
from waggle.sim.params import RobotKind
from waggle.sim.scenarios import load_map
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan_rollout import RolloutConfig

SEED = 419688070
STATIC = StaticMap(
    load_map("A"),
    AisleGraph(
        (AisleNode("start", 2, 3), AisleNode("goal", 4, 3)), (AisleEdge("start", "goal", 2),)
    ),
    {"corridor_s": "goal"},
    {"robot-0": "start"},
    1.0,
)
ROLLOUT = RolloutConfig({"robot-0": RobotKind.FORKLIFT}, frozenset(), 0.5, horizon_s=3)


def _runner(static: StaticMap = STATIC, config: RolloutConfig = ROLLOUT) -> E5Runner:
    return E5Runner(
        caution_config=CautionConfig(100, 50, 3),
        input_limits=AdvisorInputLimits(2000, 5, 10, 5),
        timeout_s=2,
        rate_limit_ticks=5,
        max_response_chars=2048,
        near_threshold_m=3,
        base_config=BY_NAME["envelope_oracle"],
        fleet_static=static,
        fleet_rollout=config,
    )


def _plan(**over: object) -> str:
    node: dict[str, object] = {
        "label": "a",
        "robot_id": "robot-0",
        "item_id": None,
        "target_zone_id": "corridor_s",
        "action": "MOVE",
        "corridor_zone_ids": [],
        "avoid_zone_ids": [],
        "wait_for": [],
        "speed_cap_mps": 0.2,
    }
    node.update(over)
    return json.dumps(
        {"nodes": [node], "rationale": "route", "escalate": False, "escalation_reason": None}
    )


def _spec(config: str = "C4", plan: str | None = None) -> RunSpec:
    return RunSpec(
        config,
        "S01",
        SEED,
        provider_script={"planner": plan or _plan()},
        ticks=25,
        trigger_ticks=(0,),
    )


def test_c4_applies_route_and_speed_cap_and_keeps_both_robot_roles() -> None:
    runner = _runner()
    baseline = runner.run_one(_spec("C3"))
    capped = runner.run_one(_spec())
    uncapped = runner.run_one(_spec(plan=_plan(speed_cap_mps=None)))
    assert capped["fleet_planner_status"] == "accepted"
    assert capped["fleet_planner_calls"] == 1
    assert capped["advisor_calls"] > 0 and capped["organizer_calls"] > 0
    assert capped["fleet_routes"] == {"robot-0": [[4.0, 3.0]]}
    assert capped["final_hash"] != baseline["final_hash"]
    assert capped["distance_m"] < uncapped["distance_m"]
    assert capped["widening_ticks"] == 0
    assert capped["speed_sums"]["limited"] <= capped["speed_sums"]["requested"]
    assert capped["final_hash"] == runner.run_one(_spec())["final_hash"]


def test_c4_completes_the_new_route_instead_of_following_the_original_destination() -> None:
    runner = _runner()
    baseline = runner.run_one(replace(_spec("C3"), ticks=100))
    planned = runner.run_one(replace(_spec(plan=_plan(speed_cap_mps=None)), ticks=100))
    assert baseline["tasks_completed"] == 0
    assert planned["tasks_completed"] == 1
    assert planned["distance_m"] < baseline["distance_m"]
    assert planned["widening_ticks"] == 0


@pytest.mark.parametrize(
    "plan,reason",
    [
        (_plan(robot_id="forged"), "unknown_reference"),
        (_plan(action="DISPATCH_REPAIR"), "unsupported_execution"),
        (_plan(wait_for=["a"]), "cycle"),
        (_plan(speed_cap_mps=100), "bad_value"),
        ('{"nodes":[]}', "missing_field"),
    ],
)
def test_bad_plan_never_replaces_the_baseline_route(plan: str, reason: str) -> None:
    runner = _runner()
    baseline = runner.run_one(_spec("C3"))
    result = runner.run_one(_spec(plan=plan))
    assert result["fleet_planner_status"] == "rejected"
    assert result["fleet_planner_reason"] == reason
    assert result["fleet_routes"] == {}
    assert result["final_hash"] == baseline["final_hash"]


def test_geofence_rejection_never_applies_a_route() -> None:
    runner = _runner(config=replace(ROLLOUT, hazard_zone_ids=frozenset({"corridor_s"})))
    result = runner.run_one(_spec())
    assert result["fleet_planner_status"] == "rejected"
    assert result["fleet_planner_reason"] == "geofence"
    assert result["fleet_routes"] == {}


def test_provider_failure_keeps_the_existing_c3_trajectory() -> None:
    runner = _runner()
    failed = replace(_spec(), failure_window=(0, 25))
    baseline = runner.run_one(replace(failed, config="C3"))
    result = runner.run_one(failed)
    assert result["fleet_planner_status"] == "error"
    assert result["final_hash"] == baseline["final_hash"]


def test_mismatched_topology_is_a_real_configuration_error() -> None:
    runner = _runner(static=replace(STATIC, robot_start={"robot-0": "goal"}))
    with pytest.raises(ValueError, match="start"):
        runner.run_one(_spec())


def test_planner_request_identity_covers_trusted_topology_and_original_mission() -> None:
    from waggle.experiments.e5_fleet import fleet_context, fleet_feedback
    from waggle.llm.crisis_adapter import planner_request_id
    from waggle.sim.scenarios import generate

    scenario = generate("S01", SEED)
    context = fleet_context(scenario, STATIC, ROLLOUT)
    first = fleet_feedback(scenario, STATIC, ROLLOUT)
    changed = replace(STATIC, zone_anchor={"corridor_s": "start"})
    second = fleet_feedback(scenario, changed, ROLLOUT)
    assert first == fleet_feedback(scenario, STATIC, ROLLOUT)
    assert json.loads(first)["scenario"]["robots"][0]["route"] == [[38.0, 3.0]]
    assert planner_request_id("mission", context, first) != planner_request_id(
        "mission", context, second
    )


def test_module_runner_exposes_c4_topology_and_policy() -> None:
    from waggle.experiments.e5_advisors import run_one

    result = run_one(
        _spec(),
        caution_config=CautionConfig(100, 50, 3),
        input_limits=AdvisorInputLimits(2000, 5, 10, 5),
        timeout_s=2,
        rate_limit_ticks=5,
        max_response_chars=2048,
        near_threshold_m=3,
        base_config=BY_NAME["envelope_oracle"],
        fleet_static=STATIC,
        fleet_rollout=ROLLOUT,
    )
    assert result["fleet_planner_status"] == "accepted"
