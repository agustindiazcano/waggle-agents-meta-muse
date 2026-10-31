"""Bind explicit navigation graphs to rectangular simulator maps.

This adapter checks straight segments with a square clearance expansion, which
conservatively contains a circular chassis bound. It does not certify curved
tracking, dynamic clearance, or a robot's ability to turn at a waypoint.
"""

import math
from dataclasses import dataclass

from waggle.coordination.routing import AisleGraph, RoutePlan, plan_route
from waggle.sim.world import Bounds, Point, Polygon, World


def _rectangle(polygon: Polygon) -> Bounds:
    xs, ys = zip(*polygon.points, strict=True)
    bounds = min(xs), min(ys), max(xs), max(ys)
    expected = {(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])}
    if len(polygon.points) != 4 or len(expected) != 4 or set(polygon.points) != expected:
        raise ValueError("map graph requires axis-aligned rectangle geometry")
    # Reject crossed vertex order even if its vertex set describes a rectangle.
    for a, b in zip(polygon.points, polygon.points[1:] + polygon.points[:1], strict=True):
        if (a[0] == b[0]) == (a[1] == b[1]):
            raise ValueError("map graph requires ordered rectangle geometry")
    return bounds


def _expanded(bounds: Bounds, clearance: float) -> Bounds:
    x0, y0, x1, y1 = bounds
    return x0 - clearance, y0 - clearance, x1 + clearance, y1 + clearance


def _touches(start: Point, end: Point, bounds: Bounds) -> bool:
    """Closed segment/box intersection, including exact boundary contact."""
    first, last = 0.0, 1.0
    for origin, target, lower, upper in (
        (start[0], end[0], bounds[0], bounds[2]),
        (start[1], end[1], bounds[1], bounds[3]),
    ):
        delta = target - origin
        if delta == 0:
            if not lower <= origin <= upper:
                return False
            continue
        near, far = sorted(((lower - origin) / delta, (upper - origin) / delta))
        first, last = max(first, near), min(last, far)
        if first > last:
            return False
    return True


def validate_map_graph(box: World, graph: AisleGraph, clearance_m: float) -> None:
    """Reject unsupported maps, blocked segments or missing corridor reservations.

    Clearance must enclose the chassis footprint for every heading. Map bounds
    contain the expanded nodes; every straight edge avoids expanded obstacles.
    Each touched capacity-one zone must be the edge's declared resource. Edges
    touching multiple resources must be split; no reservation is guessed.
    """
    if (
        isinstance(clearance_m, bool)
        or not isinstance(clearance_m, int | float)
        or not math.isfinite(clearance_m)
        or clearance_m <= 0
    ):
        raise ValueError("clearance must be a finite positive distance")
    obstacles = tuple(_expanded(_rectangle(p), clearance_m) for p in (*box.walls, *box.racks))
    corridors = {
        zone.id: _expanded(_rectangle(zone.polygon), clearance_m)
        for zone in box.zones
        if zone.capacity == 1
    }
    coordinates = {node.node_id: (node.x_m, node.y_m) for node in graph.nodes}
    x0, y0, x1, y1 = box.bounds
    for point in coordinates.values():
        if not (
            x0 + clearance_m <= point[0] <= x1 - clearance_m
            and y0 + clearance_m <= point[1] <= y1 - clearance_m
        ):
            raise ValueError("graph node clearance exceeds map bounds")
        if any(_touches(point, point, obstacle) for obstacle in obstacles):
            raise ValueError("graph node clearance touches an obstacle")
    for edge in graph.edges:
        start, end = coordinates[edge.source], coordinates[edge.destination]
        if any(_touches(start, end, obstacle) for obstacle in obstacles):
            raise ValueError("graph edge clearance touches an obstacle")
        touched = {name for name, bounds in corridors.items() if _touches(start, end, bounds)}
        declared = set() if edge.corridor_id is None else {edge.corridor_id}
        if touched != declared:
            raise ValueError("graph edge corridor declaration does not match map intersections")


@dataclass(frozen=True)
class MappedRoute:
    """Graph plan with waypoint coordinates, excluding the robot's start node."""

    plan: RoutePlan
    waypoints: tuple[Point, ...]


def plan_map_route(
    box: World,
    graph: AisleGraph,
    start: str,
    goal: str,
    holder: str,
    clearance_m: float,
) -> MappedRoute | None:
    """Validate the complete graph and return a mapped route, or None if unreachable."""
    validate_map_graph(box, graph, clearance_m)
    plan = plan_route(graph, start, goal, holder)
    if plan is None:
        return None
    coordinates = {node.node_id: (node.x_m, node.y_m) for node in graph.nodes}
    return MappedRoute(plan, tuple(coordinates[node] for node in plan.nodes[1:]))
