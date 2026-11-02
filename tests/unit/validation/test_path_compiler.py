"""Static geometry stage: plan nodes to paths on the aisle graph, before any rollout."""

import json
from collections.abc import Callable

import pytest

from waggle.coordination.corridors import Direction
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.scenarios import load_map
from waggle.validation.counterexample import CounterexampleCode, Rule
from waggle.validation.path_compiler import CompileResult, StaticMap, compile_plan
from waggle.validation.plan import Plan, PlanContext, parse_plan

CLEARANCE = 0.9
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


def _static(**over: object) -> StaticMap:
    base: dict[str, object] = {
        "world": load_map("A"),
        "graph": _graph(),
        "zone_anchor": {
            "station_1": "nw",
            "depot_n": "ne",
            "corridor_s": "sm",
            "aisle_1": "isle",
            "connector_e": "se",
            "lane_1": "sw",
        },
        "robot_start": {"R1": "sw", "R2": "se"},
        "clearance_m": CLEARANCE,
    }
    base.update(over)
    return StaticMap(**base)  # type: ignore[arg-type]


def _node(label: str, target: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "label": label,
        "robot_id": "R1",
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


def _plan(*nodes: dict[str, object]) -> Plan:
    body = {"nodes": list(nodes), "rationale": "r", "escalate": False, "escalation_reason": None}
    return parse_plan(json.dumps(body), "m-1", CONTEXT)


def test_a_reachable_node_compiles_to_a_path_with_clearance() -> None:
    result = compile_plan(_plan(_node("n1", "corridor_s")), _static())
    assert result.counterexamples == ()
    (path,) = result.paths
    assert (path.label, path.robot_id) == ("n1", "R1")
    assert path.route_nodes == ("sw", "sm") and path.waypoints == ((20.0, 2.0),)
    assert path.cost == 17.0 and path.corridor_ids == ()
    assert path.min_clearance_m == pytest.approx(3.0)


def test_consecutive_nodes_of_one_robot_start_where_the_last_one_ended() -> None:
    plan = _plan(
        _node("n1", "corridor_s"),
        _node("n2", "station_1", corridor_zone_ids=["lane_1"]),
    )
    first, second = compile_plan(plan, _static()).paths
    assert first.route_nodes == ("sw", "sm")
    assert second.route_nodes[0] == "sm" and second.route_nodes[-1] == "nw"
    assert second.corridor_ids == ("lane_1",)


def test_a_declared_corridor_is_accepted_and_an_undeclared_one_is_rejected() -> None:
    declared = compile_plan(
        _plan(_node("n1", "station_1", corridor_zone_ids=["lane_1"])), _static()
    )
    assert declared.counterexamples == ()
    assert declared.paths[0].corridor_ids == ("lane_1",)
    undeclared = compile_plan(_plan(_node("n1", "station_1")), _static())
    (cx,) = undeclared.counterexamples
    assert cx.code == "ROUTE_INFEASIBLE" and cx.rule is Rule.UNDECLARED_CORRIDOR
    assert (cx.node, cx.zone, cx.entities, cx.variant, cx.time_s) == (
        "n1",
        "lane_1",
        ("R1",),
        None,
        None,
    )
    assert undeclared.paths == ()


def test_an_unreachable_node_is_route_infeasible() -> None:
    (cx,) = compile_plan(_plan(_node("n1", "aisle_1")), _static()).counterexamples
    assert (cx.code, cx.rule, cx.zone, cx.node) == (
        CounterexampleCode.ROUTE_INFEASIBLE,
        Rule.NO_ROUTE,
        "aisle_1",
        "n1",
    )


def test_a_zone_without_an_anchor_or_a_robot_without_a_start_fails_closed() -> None:
    no_anchor = _static(zone_anchor={"depot_n": "ne"})
    (cx,) = compile_plan(_plan(_node("n1", "corridor_s")), no_anchor).counterexamples
    assert (cx.rule, cx.zone) == (Rule.NO_ROUTE, "corridor_s")
    no_start = _static(robot_start={})
    (cx2,) = compile_plan(_plan(_node("n1", "corridor_s")), no_start).counterexamples
    assert (cx2.rule, cx2.entities) == (Rule.NO_ROUTE, ("R1",))
    bad_anchor = _static(zone_anchor={"corridor_s": "nowhere"})
    assert compile_plan(_plan(_node("n1", "corridor_s")), bad_anchor).counterexamples


def test_an_avoided_corridor_is_routed_around_when_a_detour_exists() -> None:
    plan = _plan(_node("n1", "station_1", avoid_zone_ids=["lane_1"]))
    result = compile_plan(plan, _static())
    assert result.counterexamples == ()
    assert result.paths[0].route_nodes == ("sw", "sm", "se", "ne", "nm", "nw")
    assert result.paths[0].corridor_ids == ()


def test_an_avoided_zone_touched_by_a_straight_edge_is_not_used() -> None:
    plan = _plan(
        _node("n1", "depot_n", avoid_zone_ids=["connector_e"], corridor_zone_ids=["lane_1"])
    )
    result = compile_plan(plan, _static())
    assert result.counterexamples == ()
    assert result.paths[0].route_nodes == ("sw", "nw", "nm", "ne")


def test_an_avoid_that_blocks_every_route_names_the_zones() -> None:
    plan = _plan(_node("n1", "depot_n", avoid_zone_ids=["connector_e", "lane_1"]))
    found = compile_plan(plan, _static()).counterexamples
    assert {(c.zone, c.rule) for c in found} == {
        ("connector_e", Rule.AVOID_UNSATISFIABLE),
        ("lane_1", Rule.AVOID_UNSATISFIABLE),
    }


def test_an_avoid_that_alone_blocks_the_goal_names_only_that_zone() -> None:
    plan = _plan(_node("n1", "corridor_s", avoid_zone_ids=["corridor_s", "corridor_n"]))
    found = compile_plan(plan, _static()).counterexamples
    assert [(c.zone, c.rule) for c in found] == [("corridor_s", Rule.AVOID_UNSATISFIABLE)]


def test_a_failed_robot_adds_no_later_paths_but_other_robots_still_compile() -> None:
    plan = _plan(
        _node("n1", "aisle_1"),
        _node("n2", "corridor_s"),
        _node("n3", "depot_n", robot_id="R2"),
    )
    result = compile_plan(plan, _static())
    assert [c.node for c in result.counterexamples] == ["n1"]
    assert [p.label for p in result.paths] == ["n3"]


def test_an_invalid_static_map_raises_instead_of_passing() -> None:
    with pytest.raises(ValueError, match="obstacle"):
        compile_plan(_plan(_node("n1", "corridor_s")), _static(clearance_m=3.5))
    with pytest.raises(ValueError, match="clearance"):
        compile_plan(_plan(_node("n1", "corridor_s")), _static(clearance_m=0.0))


def test_the_compiler_is_deterministic() -> None:
    plan = _plan(_node("n1", "station_1", avoid_zone_ids=["lane_1"]))
    assert compile_plan(plan, _static()) == compile_plan(plan, _static())


Compile = Callable[[Plan, StaticMap], CompileResult]


def _accept_everything(plan: Plan, static: StaticMap) -> CompileResult:
    return CompileResult((), ())


def _planted_faults_that_pass(compile_fn: Compile) -> list[str]:
    """Names of planted faulty plans the compiler failed to reject."""
    faulty = {
        "unreachable": _node("n1", "aisle_1"),
        "undeclared_corridor": _node("n1", "station_1"),
        "avoid_unsatisfiable": _node("n1", "depot_n", avoid_zone_ids=["connector_e", "lane_1"]),
    }
    return [
        name
        for name, node in faulty.items()
        if not compile_fn(_plan(node), _static()).counterexamples
    ]


def test_planted_faults_are_rejected_and_the_fixed_plans_are_accepted() -> None:
    assert _planted_faults_that_pass(compile_plan) == []
    fixed = (
        _node("n1", "corridor_s"),
        _node("n1", "station_1", corridor_zone_ids=["lane_1"]),
        _node("n1", "depot_n", avoid_zone_ids=["connector_e"], corridor_zone_ids=["lane_1"]),
    )
    for node in fixed:
        assert compile_plan(_plan(node), _static()).counterexamples == ()


def test_a_mutant_that_accepts_everything_is_caught_by_the_planted_faults() -> None:
    assert _planted_faults_that_pass(_accept_everything) == [
        "unreachable",
        "undeclared_corridor",
        "avoid_unsatisfiable",
    ]
