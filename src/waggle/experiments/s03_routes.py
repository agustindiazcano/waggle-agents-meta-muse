"""Explicit navigation topology for the S03 admission integration fixture."""

import math

from waggle.coordination.corridors import Direction
from waggle.coordination.map_graph import MappedRoute, plan_map_route
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.params import ROBOT_PARAMS, RobotKind
from waggle.sim.world import World


def build_s03_graph() -> AisleGraph:
    """Declare the fixture's staging, transit and parking topology on map A."""
    return AisleGraph(
        (
            AisleNode("south", 3, 2),
            AisleNode("north", 3, 22),
            AisleNode("north_park", 0.9, 23),
            AisleNode("north_east", 9, 22),
            AisleNode("north_entry", 3, 20.5),
            AisleNode("south_park", 9, 2),
        ),
        (
            AisleEdge("south", "north", 20, "lane_1", Direction.FORWARD),
            AisleEdge("north", "north_park", math.hypot(2.1, 1)),
            AisleEdge("north_east", "north_entry", math.hypot(6, 1.5)),
            AisleEdge("north_entry", "south", 18.5, "lane_1", Direction.REVERSE),
            AisleEdge("south", "south_park", 6),
        ),
    )


def plan_s03_routes(box: World) -> tuple[MappedRoute, MappedRoute]:
    """Plan both fixture missions or reject an unreachable or invalid map binding."""
    graph = build_s03_graph()
    params = ROBOT_PARAMS[RobotKind.CARRIER]
    clearance = math.hypot(params.length, params.width) / 2
    routes: list[MappedRoute] = []
    for i, (start, goal) in enumerate((("south", "north_park"), ("north_east", "south_park"))):
        route = plan_map_route(box, graph, start, goal, f"robot-{i}", clearance)
        if route is None:
            raise ValueError("S03 destination is unreachable")
        if route.plan.corridor_request is None:
            raise ValueError("S03 route must reserve its capacity-one corridor")
        routes.append(route)
    return routes[0], routes[1]
