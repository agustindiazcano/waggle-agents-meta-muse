"""Deterministic A* routing over a typed aisle graph."""

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot, isfinite

from waggle.coordination.corridors import CorridorRequest, Direction


def _name(value: str, field: str) -> None:
    """Validate a nonempty graph or resource identifier."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


@dataclass(frozen=True)
class AisleNode:
    """A route graph vertex with map coordinates in metres."""

    node_id: str
    x_m: float
    y_m: float

    def __post_init__(self) -> None:
        _name(self.node_id, "node_id")
        if (
            isinstance(self.x_m, bool)
            or isinstance(self.y_m, bool)
            or not isinstance(self.x_m, (int, float))
            or not isinstance(self.y_m, (int, float))
            or not isfinite(self.x_m)
            or not isfinite(self.y_m)
        ):
            raise ValueError("node coordinates must be finite numbers")


@dataclass(frozen=True)
class AisleEdge:
    """Directed aisle transition; cost must dominate straight-line distance."""

    source: str
    destination: str
    cost: float
    corridor_id: str | None = None
    direction: Direction = Direction.FORWARD

    def __post_init__(self) -> None:
        _name(self.source, "source")
        _name(self.destination, "destination")
        if self.source == self.destination:
            raise ValueError("self edges are not allowed")
        if (
            isinstance(self.cost, bool)
            or not isinstance(self.cost, (int, float))
            or not isfinite(self.cost)
            or self.cost <= 0
        ):
            raise ValueError("edge cost must be a finite positive number")
        if self.corridor_id is not None:
            _name(self.corridor_id, "corridor_id")
            if not isinstance(self.direction, Direction):
                raise ValueError("corridor edges require an explicit direction")


@dataclass(frozen=True)
class AisleGraph:
    """Immutable directed aisle graph with validated geometric lower bounds."""

    nodes: tuple[AisleNode, ...]
    edges: tuple[AisleEdge, ...]

    def __post_init__(self) -> None:
        ids = [node.node_id for node in self.nodes]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("graph nodes must be nonempty and unique")
        coordinates = {node.node_id: (node.x_m, node.y_m) for node in self.nodes}
        for edge in self.edges:
            if edge.source not in coordinates or edge.destination not in coordinates:
                raise ValueError("edge endpoint is missing from graph nodes")
            start = coordinates[edge.source]
            end = coordinates[edge.destination]
            if edge.cost < hypot(end[0] - start[0], end[1] - start[1]):
                raise ValueError("edge cost cannot be less than straight-line distance")
        object.__setattr__(self, "nodes", tuple(sorted(self.nodes, key=lambda n: n.node_id)))
        object.__setattr__(
            self,
            "edges",
            tuple(
                sorted(
                    self.edges,
                    key=lambda e: (
                        e.source,
                        e.destination,
                        e.cost,
                        e.corridor_id or "",
                        e.direction.value,
                    ),
                )
            ),
        )


@dataclass(frozen=True)
class RoutePlan:
    """Shortest graph path and its whole-route corridor reservation request."""

    nodes: tuple[str, ...]
    cost: float
    corridor_request: CorridorRequest | None


def plan_route(
    graph: AisleGraph,
    start: str,
    goal: str,
    holder: str,
) -> RoutePlan | None:
    """Return a deterministic shortest route, or None when the goal is unreachable."""
    _name(holder, "holder")
    coordinates = {node.node_id: (node.x_m, node.y_m) for node in graph.nodes}
    if start not in coordinates or goal not in coordinates:
        raise ValueError("start and goal must exist in the graph")
    if start == goal:
        return RoutePlan((start,), 0.0, None)

    outgoing: dict[str, list[AisleEdge]] = {node_id: [] for node_id in coordinates}
    for edge in graph.edges:
        outgoing[edge.source].append(edge)
    for edges in outgoing.values():
        edges.sort(
            key=lambda edge: (
                edge.destination,
                edge.cost,
                edge.corridor_id or "",
                edge.direction.value,
            )
        )

    def heuristic(node_id: str) -> float:
        x1, y1 = coordinates[node_id]
        x2, y2 = coordinates[goal]
        return hypot(x2 - x1, y2 - y1)

    open_nodes: list[tuple[float, float, str]] = [(heuristic(start), 0.0, start)]
    best_cost = {start: 0.0}
    previous: dict[str, tuple[str, AisleEdge]] = {}
    while open_nodes:
        _, current_cost, current = heappop(open_nodes)
        if current_cost != best_cost.get(current):
            continue
        if current == goal:
            break
        for edge in outgoing[current]:
            candidate = current_cost + edge.cost
            known = best_cost.get(edge.destination)
            if known is not None and candidate >= known:
                continue
            best_cost[edge.destination] = candidate
            previous[edge.destination] = (current, edge)
            heappush(
                open_nodes,
                (candidate + heuristic(edge.destination), candidate, edge.destination),
            )
    if goal not in best_cost:
        return None

    route_nodes = [goal]
    route_edges: list[AisleEdge] = []
    cursor = goal
    while cursor != start:
        parent, edge = previous[cursor]
        route_edges.append(edge)
        route_nodes.append(parent)
        cursor = parent
    route_nodes.reverse()
    route_edges.reverse()

    directions: dict[str, Direction] = {}
    for edge in route_edges:
        if edge.corridor_id is None:
            continue
        old_direction = directions.get(edge.corridor_id)
        if old_direction is not None and old_direction != edge.direction:
            raise ValueError("route has conflicting directions through one corridor")
        directions[edge.corridor_id] = edge.direction
    resources = tuple(sorted(directions))
    request = (
        CorridorRequest(
            holder,
            resources,
            directions[resources[0]],
            tuple((resource, directions[resource]) for resource in resources),
        )
        if resources
        else None
    )
    return RoutePlan(tuple(route_nodes), best_cost[goal], request)
