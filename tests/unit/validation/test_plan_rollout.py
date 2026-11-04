"""Stage C of the plan validator: one deterministic rollout of the compiled plan, no humans.

Sensitivity tests plant a fault, check the expected counterexample, then remove the fault and
check the plan passes. Mutant validators (accept everything, ignore the rollout) must fail the
same sensitivity checks, so a green result cannot come from a validator that cannot fail.
"""

import ast
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from waggle.coordination.corridors import Direction
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.params import ROBOT_PARAMS, RobotKind
from waggle.sim.scenarios import load_map
from waggle.sim.world import World
from waggle.validation.belief import HumanState
from waggle.validation.counterexample import CounterexampleCode, Rule
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan import Plan, PlanContext, parse_plan
from waggle.validation.plan_rollout import (
    RolloutConfig,
    ValidationResult,
    run_plan_rollout,
    validate_plan,
)

ZONES = frozenset(
    {"lane_1", "station_1", "depot_n", "corridor_s", "aisle_1", "connector_e", "corridor_n"}
)
CONTEXT = PlanContext({"R1": 1.5, "R2": 1.5}, frozenset({"ITEM-1"}), ZONES)


def _both(a: str, b: str, cost: float, corridor: str | None = None) -> tuple[AisleEdge, ...]:
    back = Direction.REVERSE if corridor else Direction.FORWARD
    return (AisleEdge(a, b, cost, corridor), AisleEdge(b, a, cost, corridor, back))


def _graph() -> AisleGraph:
    points = {
        "sw": (3, 2),
        "sm": (20, 2),
        "se": (37, 2),
        "nw": (3, 22),
        "nm": (20, 22),
        "ne": (37, 22),
        "isle": (20, 9),
    }
    edges = (
        *_both("sw", "sm", 17),
        *_both("sm", "se", 17),
        *_both("nw", "nm", 18),
        *_both("nm", "ne", 17),
        *_both("se", "ne", 20),
        *_both("sw", "nw", 20, "lane_1"),
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
HEAD_ON_START = {"R1": "sw", "R2": "se"}
HEAD_ON = (_node("a", "R1", "connector_e"), _node("b", "R2", "lane_1", corridor_zone_ids=[]))


def _codes(result: ValidationResult) -> set[str]:
    return {str(c.code) for c in result.counterexamples}


def test_two_robots_on_separate_aisles_pass() -> None:
    result = validate_plan(_plan(*SAFE), _static(SAFE_START), _config())
    assert result.accepted and result.counterexamples == () and result.stage == "rollout"
    assert result.final_hash is not None


def _parked_pair(gap_m: float) -> StaticMap:
    length = ROBOT_PARAMS[RobotKind.CARRIER].length
    graph = AisleGraph((AisleNode("a", 3.0, 2.0), AisleNode("b", 3.0 + length + gap_m, 2.0)), ())
    return replace(_static({"R1": "a", "R2": "b"}), graph=graph, zone_anchor={})


@pytest.mark.parametrize("walkers", [(), (HumanState((30.0, 20.0), (0.0, 0.0)),)])
def test_noncontact_robot_separation_is_reported_once_with_or_without_humans(
    walkers: tuple[HumanState, ...],
) -> None:
    # Carrier length is 1.2 m; centers 1.45 m apart give a known 0.25 m gap.
    config = _config(horizon_s=0.1)
    result = run_plan_rollout((), _parked_pair(0.25), config, walkers)
    assert len(result.counterexamples) == 1
    violation = result.counterexamples[0]
    assert violation.code == CounterexampleCode.SEPARATION_VIOLATION
    assert violation.entities == ("R1", "R2")
    assert violation.rule == Rule.SEPARATION_MIN
    assert violation.min_clearance_m == pytest.approx(0.25)
    assert violation.time_s == pytest.approx(0.025)
    assert violation.place_xy_m is not None
    assert result == run_plan_rollout((), _parked_pair(0.25), config, walkers)


@pytest.mark.parametrize("gap_m", [0.5, 0.75])
def test_robot_gap_at_or_above_the_margin_is_not_rejected(gap_m: float) -> None:
    result = validate_plan(_plan(), _parked_pair(gap_m), _config(horizon_s=0.1))
    assert result.accepted and result.counterexamples == ()


def test_validator_rejects_a_robot_separation_violation_without_contact() -> None:
    result = validate_plan(_plan(), _parked_pair(0.25), _config(horizon_s=0.1))
    assert not result.accepted
    assert _codes(result) == {CounterexampleCode.SEPARATION_VIOLATION}


def test_a_moving_robot_passing_an_idle_robot_is_rejected_without_contact() -> None:
    graph = AisleGraph(
        (AisleNode("a", 3.0, 2.0), AisleNode("b", 6.0, 3.05), AisleNode("c", 9.0, 2.0)),
        _both("a", "c", 6.0),
    )
    static = StaticMap(
        World("open", (0.0, 0.0, 20.0, 20.0), (), (), ()),
        graph,
        {"connector_e": "c"},
        {"R1": "a", "R2": "b"},
        0.9,
    )
    # Side-by-side carrier half-widths sum to 0.8 m: lateral gap is 0.25 m.
    result = validate_plan(_plan(_node("a", "R1", "connector_e")), static, _config(horizon_s=5.0))
    assert not result.accepted
    assert _codes(result) == {CounterexampleCode.SEPARATION_VIOLATION}
    violation = result.counterexamples[0]
    assert violation.time_s is not None and violation.time_s > 0.025
    assert violation.min_clearance_m is not None
    assert 0.0 < violation.min_clearance_m < 0.5


def test_contact_still_reports_collision_as_well_as_separation() -> None:
    result = run_plan_rollout((), _parked_pair(-0.1), _config(horizon_s=0.1))
    assert {c.code for c in result.counterexamples} == {
        CounterexampleCode.COLLISION,
        CounterexampleCode.SEPARATION_VIOLATION,
    }


def test_a_head_on_plan_is_rejected_with_a_collision_at_a_time_and_place() -> None:
    result = validate_plan(_plan(*HEAD_ON), _static(HEAD_ON_START), _config())
    assert not result.accepted
    collision = next(c for c in result.counterexamples if c.code == CounterexampleCode.COLLISION)
    assert set(collision.entities) == {"R1", "R2"}
    assert collision.time_s is not None and collision.time_s > 0
    assert collision.place_xy_m is not None and collision.variant is None


def test_a_path_through_a_hazard_zone_is_rejected_though_no_node_names_it() -> None:
    plan = _plan(_node("a", "R1", "connector_e"))
    start = {"R1": "sw", "R2": "ne"}
    config = _config(hazard_zone_ids=frozenset({"corridor_s"}))
    result = validate_plan(plan, _static(start), config)
    assert CounterexampleCode.GEOFENCE_INTRUSION in _codes(result)
    hit = next(c for c in result.counterexamples if c.zone == "corridor_s")
    assert hit.entities == ("R1",) and hit.time_s is not None
    assert validate_plan(plan, _static(start), _config()).accepted


def test_a_robot_that_does_not_reach_its_first_waypoint_has_no_progress() -> None:
    plan = _plan(_node("a", "R1", "connector_e"))
    short = validate_plan(plan, _static(SAFE_START), _config(horizon_s=1.0))
    assert CounterexampleCode.NO_PROGRESS in _codes(short)
    assert validate_plan(plan, _static(SAFE_START), _config()).accepted


def test_an_idle_robot_on_the_route_is_hit() -> None:
    plan = _plan(_node("a", "R1", "connector_e"))
    result = validate_plan(plan, _static({"R1": "sw", "R2": "sm"}), _config())
    assert CounterexampleCode.COLLISION in _codes(result)


def test_an_escalated_plan_is_not_validated_as_motion() -> None:
    result = validate_plan(_plan(*SAFE, escalate=True), _static(SAFE_START), _config())
    assert not result.accepted and result.escalated and result.stage == "escalated"


def test_the_geofence_and_static_stages_run_before_the_rollout() -> None:
    geo = validate_plan(
        _plan(_node("a", "R1", "corridor_s")),
        _static(SAFE_START),
        _config(hazard_zone_ids=frozenset({"corridor_s"})),
    )
    assert geo.stage == "geofence" and geo.final_hash is None
    undeclared = validate_plan(_plan(_node("a", "R1", "station_1")), _static(SAFE_START), _config())
    assert (
        undeclared.stage == "static" and not undeclared.accepted and undeclared.final_hash is None
    )


def test_the_same_plan_gives_the_same_counterexamples_and_hash() -> None:
    first = validate_plan(_plan(*HEAD_ON), _static(HEAD_ON_START), _config())
    second = validate_plan(_plan(*HEAD_ON), _static(HEAD_ON_START), _config())
    assert first == second


def test_a_different_seed_does_not_change_a_rollout_without_humans() -> None:
    a = validate_plan(_plan(*SAFE), _static(SAFE_START), _config(seed=1))
    b = validate_plan(_plan(*SAFE), _static(SAFE_START), _config(seed=2))
    assert a.counterexamples == b.counterexamples


@pytest.mark.parametrize(
    ("make", "error"),
    [
        (lambda: _config(robot_kinds={"R1": RobotKind.CARRIER}), "robot kind"),
        (lambda: _config(hazard_zone_ids=frozenset({"no_such_zone"})), "hazard"),
    ],
)
def test_a_missing_or_unknown_input_raises_and_is_never_an_empty_pass(
    make: Callable[[], RolloutConfig], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        validate_plan(_plan(*SAFE), _static(SAFE_START), make())


def test_a_plan_robot_without_a_start_is_rejected_by_the_static_stage() -> None:
    result = validate_plan(_plan(*SAFE), _static({"R1": "sw"}), _config())
    assert not result.accepted and result.stage == "static"
    assert CounterexampleCode.ROUTE_INFEASIBLE in _codes(result)


@pytest.mark.parametrize(
    "make",
    [
        lambda: _config(horizon_s=0.0),
        lambda: _config(horizon_s=float("nan")),
        lambda: _config(horizon_s=0.03),
        lambda: _config(separation_margin_m=-1.0),
        lambda: _config(seed=-1),
    ],
)
def test_an_invalid_config_is_refused(make: Callable[[], RolloutConfig]) -> None:
    with pytest.raises(ValueError):
        make()


def test_the_default_horizon_is_the_adr_025_basis() -> None:
    assert _config().horizon_s == 45.0


def test_rollout_alone_reports_the_first_ticks_state_hash_deterministically() -> None:
    from waggle.validation.path_compiler import compile_plan

    plan, static = _plan(*SAFE), _static(SAFE_START)
    paths = compile_plan(plan, static).paths
    one = run_plan_rollout(paths, static, _config())
    two = run_plan_rollout(paths, static, _config())
    assert one == two and one.ticks == 1800


# Mutants: validators that cannot fail. The sensitivity suite must reject them.


def _sensitivity(validate: Callable[[Plan, StaticMap, RolloutConfig], ValidationResult]) -> None:
    head_on = validate(_plan(*HEAD_ON), _static(HEAD_ON_START), _config())
    assert not head_on.accepted
    safe = validate(_plan(*SAFE), _static(SAFE_START), _config())
    assert safe.accepted


def _accept_everything(plan: Plan, static: StaticMap, config: RolloutConfig) -> ValidationResult:
    return ValidationResult(True, False, "rollout", (), None)


def _skip_the_rollout(plan: Plan, static: StaticMap, config: RolloutConfig) -> ValidationResult:
    result = validate_plan(plan, static, config)
    if result.stage == "rollout":
        return ValidationResult(True, False, "rollout", (), result.final_hash)
    return result


def test_the_real_validator_passes_the_sensitivity_suite() -> None:
    _sensitivity(validate_plan)


@pytest.mark.parametrize("mutant", [_accept_everything, _skip_the_rollout])
def test_a_validator_that_cannot_fail_is_caught_by_the_suite(
    mutant: Callable[[Plan, StaticMap, RolloutConfig], ValidationResult],
) -> None:
    with pytest.raises(AssertionError):
        _sensitivity(mutant)


def test_the_module_imports_no_llm_governance_or_mcp_code() -> None:
    source = Path(__file__).parents[3] / "src" / "waggle" / "validation" / "plan_rollout.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    banned = ("waggle.llm", "waggle.governance", "waggle.mcp_server", "waggle.control")
    assert not [m for m in imported if m.startswith(banned)]
