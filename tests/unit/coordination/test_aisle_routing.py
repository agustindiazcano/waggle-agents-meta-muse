"""Deterministic aisle routing tests."""

import pytest

from waggle.coordination.corridors import (
    CorridorReason,
    CorridorState,
    CorridorZone,
    Direction,
    ZoneObservation,
    request_corridor,
)
from waggle.coordination.leases import LeaseState
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode, plan_route


def test_astar_returns_route_and_atomic_per_zone_corridor_request() -> None:
    graph = AisleGraph(
        nodes=(AisleNode("start", 0, 0), AisleNode("junction", 1, 0), AisleNode("goal", 1, 2)),
        edges=(
            AisleEdge("start", "junction", 1.0, "east", Direction.FORWARD),
            AisleEdge("junction", "goal", 2.0, "west", Direction.REVERSE),
        ),
    )

    result = plan_route(graph, "start", "goal", "robot-1")

    assert result is not None
    assert result.nodes == ("start", "junction", "goal")
    assert result.cost == 3.0
    assert result.corridor_request is not None
    assert result.corridor_request.resource_ids == ("east", "west")
    assert result.corridor_request.directions_by_resource == (
        ("east", Direction.FORWARD),
        ("west", Direction.REVERSE),
    )

    state = CorridorState((CorridorZone(LeaseState("east")), CorridorZone(LeaseState("west"))))
    observations = (
        ZoneObservation("east", 0, ()),
        ZoneObservation("west", 0, ()),
    )
    admitted = request_corridor(state, result.corridor_request, 0, observations, 20)
    assert admitted.granted and admitted.reason == CorridorReason.GRANTED
    assert tuple(zone.direction for zone in admitted.state.zones) == (
        Direction.FORWARD,
        Direction.REVERSE,
    )


def test_astar_uses_lowest_cost_path_not_fewest_edges() -> None:
    graph = AisleGraph(
        nodes=(
            AisleNode("start", 0, 0),
            AisleNode("slow", 1, 0),
            AisleNode("fast", 0, 1),
            AisleNode("goal", 2, 1),
        ),
        edges=(
            AisleEdge("start", "slow", 1.0),
            AisleEdge("slow", "goal", 9.0),
            AisleEdge("start", "fast", 2.0),
            AisleEdge("fast", "goal", 2.0),
        ),
    )

    result = plan_route(graph, "start", "goal", "robot-1")

    assert result is not None
    assert result.nodes == ("start", "fast", "goal")
    assert result.cost == 4.0


def test_astar_tie_break_is_stable_independent_of_edge_order() -> None:
    edges = (
        AisleEdge("start", "b", 1.0),
        AisleEdge("b", "goal", 1.0),
        AisleEdge("start", "a", 1.0),
        AisleEdge("a", "goal", 1.0),
    )
    nodes = (
        AisleNode("start", 0, 0),
        AisleNode("a", 1, 0),
        AisleNode("b", 0, 1),
        AisleNode("goal", 1, 1),
    )
    left = AisleGraph(nodes=nodes, edges=edges)
    right = AisleGraph(nodes=tuple(reversed(nodes)), edges=tuple(reversed(edges)))

    one = plan_route(left, "start", "goal", "robot-1")
    two = plan_route(right, "start", "goal", "robot-1")

    assert one == two
    assert one is not None and one.nodes == ("start", "a", "goal")


def test_astar_reports_unreachable_and_zero_length_routes() -> None:
    graph = AisleGraph(nodes=(AisleNode("start", 0, 0), AisleNode("goal", 1, 0)), edges=())

    assert plan_route(graph, "start", "goal", "robot-1") is None
    same = plan_route(graph, "start", "start", "robot-1")
    assert same is not None
    assert same.nodes == ("start",)
    assert same.cost == 0.0
    assert same.corridor_request is None


def test_graph_rejects_bad_weights_edges_and_missing_nodes() -> None:
    with pytest.raises(ValueError):
        AisleEdge("a", "b", 0.0)
    with pytest.raises(ValueError):
        AisleEdge("a", "b", float("inf"))
    with pytest.raises(ValueError):
        AisleGraph(nodes=(AisleNode("a", 0, 0),), edges=(AisleEdge("a", "b", 1.0),))
    with pytest.raises(ValueError):
        AisleGraph(nodes=(AisleNode("a", 0, 0), AisleNode("a", 1, 0)), edges=())


def test_plan_route_rejects_unknown_endpoints_and_repeated_corridor_ids() -> None:
    graph = AisleGraph(nodes=(AisleNode("start", 0, 0), AisleNode("goal", 1, 0)), edges=())
    with pytest.raises(ValueError):
        plan_route(graph, "missing", "goal", "robot-1")
    with pytest.raises(ValueError):
        plan_route(graph, "start", "goal", "")

    repeated = AisleGraph(
        nodes=(
            AisleNode("start", 0, 0),
            AisleNode("middle", 1, 0),
            AisleNode("goal", 2, 0),
        ),
        edges=(
            AisleEdge("start", "middle", 1.0, "lane", Direction.FORWARD),
            AisleEdge("middle", "goal", 1.0, "lane", Direction.REVERSE),
        ),
    )
    with pytest.raises(ValueError, match="conflicting directions"):
        plan_route(repeated, "start", "goal", "robot-1")
