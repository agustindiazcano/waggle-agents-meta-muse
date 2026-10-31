"""Map binding rejects unreserved corridors and blocked straight route segments."""

from dataclasses import replace

import pytest

from waggle.coordination.corridors import Direction
from waggle.coordination.map_graph import plan_map_route, validate_map_graph
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.scenarios import load_map
from waggle.sim.world import Polygon


def _crossing(resource: str | None = "lane_1") -> AisleGraph:
    return AisleGraph(
        (AisleNode("south", 3, 2), AisleNode("north", 3, 22)),
        (AisleEdge("south", "north", 20, resource),),
    )


def test_loaded_map_route_returns_coordinates_and_reservation() -> None:
    result = plan_map_route(load_map("A"), _crossing(), "south", "north", "robot-0", 0.9)
    assert result is not None
    assert result.waypoints == ((3, 22),)
    assert result.plan.cost == 20
    request = result.plan.corridor_request
    assert request is not None
    assert request.resource_ids == ("lane_1",)
    assert request.directions_by_resource == (("lane_1", Direction.FORWARD),)


@pytest.mark.parametrize("resource", [None, "missing", "station_1"])
def test_crossing_without_exact_capacity_one_resource_is_rejected(resource: str | None) -> None:
    with pytest.raises(ValueError, match="corridor"):
        validate_map_graph(load_map("A"), _crossing(resource), 0.9)


def test_resource_must_not_be_attached_to_an_unrelated_edge() -> None:
    graph = AisleGraph(
        (AisleNode("a", 10, 2), AisleNode("b", 15, 2)),
        (AisleEdge("a", "b", 5, "lane_1"),),
    )
    with pytest.raises(ValueError, match="corridor"):
        validate_map_graph(load_map("A"), graph, 0.9)


@pytest.mark.parametrize("y", [6, 4.5])
def test_wall_or_rack_clearance_is_checked_for_the_whole_segment(y: float) -> None:
    graph = AisleGraph(
        (AisleNode("a", 5, y), AisleNode("b", 35, y)),
        (AisleEdge("a", "b", 30),),
    )
    with pytest.raises(ValueError, match="obstacle"):
        validate_map_graph(load_map("A"), graph, 0.5)


def test_footprint_contact_with_corridor_requires_reservation() -> None:
    graph = AisleGraph(
        (AisleNode("a", 1, 4.5), AisleNode("b", 5, 4.5)),
        (AisleEdge("a", "b", 4),),
    )
    with pytest.raises(ValueError, match="corridor"):
        validate_map_graph(load_map("A"), graph, 0.5)


@pytest.mark.parametrize("clearance", [0, -1, float("nan"), float("inf"), True])
def test_invalid_clearance_is_rejected(clearance: float) -> None:
    with pytest.raises(ValueError, match="clearance"):
        validate_map_graph(load_map("A"), _crossing(), clearance)


def test_nodes_need_full_clearance_inside_bounds_even_without_edges() -> None:
    graph = AisleGraph((AisleNode("edge", 0.2, 2),), ())
    with pytest.raises(ValueError, match="bounds"):
        validate_map_graph(load_map("A"), graph, 0.9)


def test_isolated_node_inside_obstacle_is_rejected() -> None:
    graph = AisleGraph((AisleNode("inside", 10, 6),), ())
    with pytest.raises(ValueError, match="obstacle"):
        validate_map_graph(load_map("A"), graph, 0.5)


def test_unsupported_map_geometry_is_rejected_without_guessing() -> None:
    box = replace(load_map("A"), walls=(Polygon(((10, 1), (12, 1), (11, 3))),))
    with pytest.raises(ValueError, match="rectangle"):
        validate_map_graph(box, _crossing(), 0.9)


def test_unreachable_route_returns_none_and_start_equals_goal_has_no_waypoints() -> None:
    graph = AisleGraph(_crossing().nodes, ())
    box = load_map("A")
    assert plan_map_route(box, graph, "south", "north", "robot-0", 0.9) is None
    same = plan_map_route(box, graph, "south", "south", "robot-0", 0.9)
    assert same is not None and same.waypoints == ()
