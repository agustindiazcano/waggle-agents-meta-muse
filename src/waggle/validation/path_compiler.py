"""Static geometry stage of the plan validator: plan nodes to paths, before any rollout.

Each plan node becomes a route on the typed aisle graph (A* of ``waggle.coordination``). The
stage reports ROUTE_INFEASIBLE when a node cannot be reached, when its route needs a capacity-1
corridor the node did not declare, or when its avoid zones leave no route. A trusted map graph
that fails ``validate_map_graph`` (blocked edge, bad clearance, wrong corridor declaration)
raises ValueError: a broken input is an error, never an empty pass. Nodes of one robot are
compiled in plan order, each starting where the previous one ended. Dependencies between robots
(``wait_for``) are not geometry and are left to the rollout.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from waggle.coordination.map_graph import validate_map_graph
from waggle.coordination.routing import AisleGraph, RoutePlan, plan_route
from waggle.sim.world import World
from waggle.validation.counterexample import Counterexample, CounterexampleCode, Rule
from waggle.validation.geometry import Box, Point, polygon_box, segment_box_distance
from waggle.validation.plan import Plan, PlanNode


@dataclass(frozen=True)
class StaticMap:
    """Trusted static inputs. ``zone_anchor`` maps a zone id to its graph node, and
    ``robot_start`` maps a robot id to the graph node it starts on."""

    world: World
    graph: AisleGraph
    zone_anchor: Mapping[str, str]
    robot_start: Mapping[str, str]
    clearance_m: float


@dataclass(frozen=True)
class CompiledPath:
    """The route of one plan node. ``min_clearance_m`` is to walls and racks, None if none."""

    label: str
    robot_id: str
    route_nodes: tuple[str, ...]
    waypoints: tuple[Point, ...]
    cost: float
    corridor_ids: tuple[str, ...]
    min_clearance_m: float | None


@dataclass(frozen=True)
class CompileResult:
    """Paths of the nodes that compiled and the counterexamples of those that did not."""

    paths: tuple[CompiledPath, ...]
    counterexamples: tuple[Counterexample, ...]


def _infeasible(node: PlanNode, zone: str, rule: Rule) -> Counterexample:
    return Counterexample(
        CounterexampleCode.ROUTE_INFEASIBLE,
        node.label,
        zone,
        entities=(node.robot_id,),
        rule=rule,
    )


def _route(graph: AisleGraph, start: str, goal: str, holder: str) -> RoutePlan | None:
    try:
        return plan_route(graph, start, goal, holder)
    except ValueError:
        return None


def _without(graph: AisleGraph, avoid: Mapping[str, Box]) -> AisleGraph:
    """The graph minus edges that use an avoided corridor or touch an avoided zone."""
    at = {n.node_id: (n.x_m, n.y_m) for n in graph.nodes}
    kept = tuple(
        edge
        for edge in graph.edges
        if edge.corridor_id not in avoid
        and all(
            segment_box_distance(at[edge.source], at[edge.destination], box) > 0.0
            for box in avoid.values()
        )
    )
    return AisleGraph(graph.nodes, kept)


def _clearance(
    route_nodes: Sequence[str], graph: AisleGraph, obstacles: Sequence[Box]
) -> float | None:
    if not obstacles:
        return None
    at = {n.node_id: (n.x_m, n.y_m) for n in graph.nodes}
    pairs = list(pairwise(route_nodes)) or [(route_nodes[0],) * 2]
    return min(segment_box_distance(at[a], at[b], box) for a, b in pairs for box in obstacles)


def _blockers(
    graph: AisleGraph, avoid: Mapping[str, Box], start: str, goal: str, holder: str
) -> list[str]:
    """Avoid zones that alone cut the goal off, or all of them when only the set does."""
    single = [
        z
        for z, box in avoid.items()
        if _route(_without(graph, {z: box}), start, goal, holder) is None
    ]
    return single or list(avoid)


def _compile_node(
    node: PlanNode, start: str, static: StaticMap, obstacles: Sequence[Box]
) -> tuple[CompiledPath | None, tuple[Counterexample, ...]]:
    goal = static.zone_anchor.get(node.target_zone_id)
    known = {n.node_id for n in static.graph.nodes}
    if goal is None or goal not in known:
        return None, (_infeasible(node, node.target_zone_id, Rule.NO_ROUTE),)
    zones = {z.id: polygon_box(z.polygon.points) for z in static.world.zones}
    unknown = [z for z in node.avoid_zone_ids if z not in zones]
    if unknown:
        return None, tuple(_infeasible(node, z, Rule.AVOID_UNSATISFIABLE) for z in unknown)
    avoid = {z: zones[z] for z in node.avoid_zone_ids}
    route = _route(_without(static.graph, avoid), start, goal, node.robot_id)
    if route is None:
        if _route(static.graph, start, goal, node.robot_id) is None:
            return None, (_infeasible(node, node.target_zone_id, Rule.NO_ROUTE),)
        blocked = _blockers(static.graph, avoid, start, goal, node.robot_id)
        return None, tuple(_infeasible(node, z, Rule.AVOID_UNSATISFIABLE) for z in blocked)
    needed = route.corridor_request.resource_ids if route.corridor_request else ()
    missing = [c for c in needed if c not in node.corridor_zone_ids]
    if missing:
        return None, tuple(_infeasible(node, c, Rule.UNDECLARED_CORRIDOR) for c in missing)
    at = {n.node_id: (n.x_m, n.y_m) for n in static.graph.nodes}
    path = CompiledPath(
        node.label,
        node.robot_id,
        route.nodes,
        tuple(at[n] for n in route.nodes[1:]),
        route.cost,
        tuple(needed),
        _clearance(route.nodes, static.graph, obstacles),
    )
    return path, ()


def compile_plan(plan: Plan, static: StaticMap) -> CompileResult:
    """Compile every node to a path or a ROUTE_INFEASIBLE counterexample.

    Raises ValueError when the static map graph itself is invalid. After a robot's first
    failure its later nodes are skipped, because its position is no longer known.
    """
    validate_map_graph(static.world, static.graph, static.clearance_m)
    obstacles = [polygon_box(p.points) for p in (*static.world.walls, *static.world.racks)]
    known = {n.node_id for n in static.graph.nodes}
    position = dict(static.robot_start)
    failed: set[str] = set()
    paths: list[CompiledPath] = []
    found: list[Counterexample] = []
    for node in plan.nodes:
        if node.robot_id in failed:
            continue
        start = position.get(node.robot_id)
        if start is None or start not in known:
            result: tuple[CompiledPath | None, tuple[Counterexample, ...]] = (
                None,
                (_infeasible(node, node.target_zone_id, Rule.NO_ROUTE),),
            )
        else:
            result = _compile_node(node, start, static, obstacles)
        path, errors = result
        if path is None:
            failed.add(node.robot_id)
            found.extend(errors)
        else:
            paths.append(path)
            position[node.robot_id] = path.route_nodes[-1]
    return CompileResult(tuple(paths), tuple(found))
