"""Stage C of the plan validator: one deterministic rollout of the compiled plan (ADR-023, 078).

After the schema, the geofence check and the static geometry stage pass, the compiled paths are
driven in the simulator dynamics with no humans, over the horizon H (45 s, the ADR-025 design
basis). The rollout reports robot-robot collisions, hazard zone entries along the real path,
and robots that made no progress. It is a pure function of its inputs: the same plan, map and
config give the same counterexamples and state hash.

Not in this stage, stated plainly: human variants (stage D), the reflex layer inside the rollout
(a plan that only survives because the reflex layer would brake is rejected here, which is
stricter than the design), lease and deadlock checks, the recoverable terminal state check, and
``wait_for`` ordering between robots (every robot starts at tick 0). Bad input raises
ValueError: an error is never an empty pass.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from waggle.sim import detector, engine, humans, params, robots, scripted
from waggle.validation.counterexample import Counterexample, CounterexampleCode, Rule
from waggle.validation.geofence import check_geofence
from waggle.validation.geometry import polygon_box, segment_box_distance
from waggle.validation.path_compiler import CompiledPath, StaticMap, compile_plan
from waggle.validation.plan import Plan

_SEVERITY = {code: index for index, code in enumerate(CounterexampleCode)}
_CONTACT = 0


@dataclass(frozen=True)
class RolloutConfig:
    """Trusted inputs of the rollout. ``horizon_s`` must be a whole number of ticks."""

    robot_kinds: Mapping[str, params.RobotKind]
    hazard_zone_ids: frozenset[str]
    separation_margin_m: float
    horizon_s: float = 45.0
    seed: int = 0

    def __post_init__(self) -> None:
        """Refuse values that would make the rollout meaningless."""
        for name in ("horizon_s", "separation_margin_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{name} must be a number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.horizon_s <= 0 or self.separation_margin_m < 0:
            raise ValueError("horizon must be positive and the margin not negative")
        params.ticks_for(self.horizon_s)
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")


@dataclass(frozen=True)
class RolloutOutcome:
    """Counterexamples in time order, the final state hash and the ticks run."""

    counterexamples: tuple[Counterexample, ...]
    final_hash: str
    ticks: int


@dataclass(frozen=True)
class ValidationResult:
    """The verdict of the staged validator. ``stage`` is the last stage that ran."""

    accepted: bool
    escalated: bool
    stage: str
    counterexamples: tuple[Counterexample, ...] = ()
    final_hash: str | None = None
    notes: tuple[str, ...] = field(default=())


def _routes(paths: Sequence[CompiledPath], ids: Sequence[str]) -> list[list[tuple[float, float]]]:
    routes: dict[str, list[tuple[float, float]]] = {rid: [] for rid in ids}
    for path in paths:
        if path.robot_id not in routes:
            raise ValueError("a compiled path belongs to a robot with no start")
        routes[path.robot_id].extend(path.waypoints)
    return [routes[rid] for rid in ids]


def _poses(
    ids: Sequence[str], routes: Sequence[Sequence[tuple[float, float]]], static: StaticMap
) -> np.ndarray:
    at = {n.node_id: (n.x_m, n.y_m) for n in static.graph.nodes}
    rows = []
    for rid, route in zip(ids, routes, strict=True):
        node = static.robot_start[rid]
        if node not in at:
            raise ValueError("a robot starts on an unknown graph node")
        x, y = at[node]
        heading = math.atan2(route[0][1] - y, route[0][0] - x) if route else 0.0
        rows.append((x, y, heading))
    return np.array(rows, dtype=np.float64).reshape(len(ids), 3)


def _hazard_boxes(static: StaticMap, hazard: frozenset[str]) -> dict[str, tuple[float, ...]]:
    zones = {z.id: polygon_box(z.polygon.points) for z in static.world.zones}
    unknown = sorted(hazard - set(zones))
    if unknown:
        raise ValueError("a hazard zone is not in the map")
    return {z: zones[z] for z in sorted(hazard)}


def run_plan_rollout(
    paths: Sequence[CompiledPath], static: StaticMap, config: RolloutConfig
) -> RolloutOutcome:
    """Drive the compiled paths over the horizon and collect counterexamples.

    Every robot in ``static.robot_start`` is simulated; one with no path stands still, so it
    can be hit. Raises ValueError for a robot with no kind or no start, or an unknown hazard.
    """
    ids = sorted(static.robot_start)
    missing = [rid for rid in ids if rid not in config.robot_kinds]
    if missing:
        raise ValueError("a robot has no robot kind")
    boxes = _hazard_boxes(static, config.hazard_zone_ids)
    routes = _routes(paths, ids)
    pose = _poses(ids, routes, static)
    fleet = robots.RobotFleet([config.robot_kinds[rid] for rid in ids])
    crowd = humans.Crowd([], static.world)
    driver = scripted.WaypointDriver(fleet, routes, loop=False)
    det = detector.Detector(
        fleet.params,
        separation_margin=config.separation_margin_m,
        near_miss_margin=config.separation_margin_m,
    )
    no_humans = np.zeros((0, 2), dtype=np.float64)
    arrays = {
        **fleet.initial_arrays(pose, np.zeros(len(ids))),
        **crowd.initial_arrays(no_humans),
        **driver.initial_arrays(),
        **det.initial_arrays(pose, no_humans),
    }
    systems = [driver.system(), fleet.system(), crowd.system(), det.system()]
    sim = engine.Engine(config.seed, arrays, systems, {"humans": 0})
    found: list[Counterexample] = []
    hit_zones: set[tuple[str, str]] = set()
    reported: set[tuple[int, int]] = set()
    half_width = [p.width / 2.0 for p in fleet.params]
    ticks = params.ticks_for(config.horizon_s)

    def scan_hazards() -> None:
        now = sim.state.tick * params.DT
        poses = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)
        for i, rid in enumerate(ids):
            point = (float(poses[i, 0]), float(poses[i, 1]))
            for zone, box in boxes.items():
                if (rid, zone) in hit_zones:
                    continue
                if segment_box_distance(point, point, box) <= half_width[i]:  # type: ignore[arg-type]
                    hit_zones.add((rid, zone))
                    found.append(
                        Counterexample(
                            CounterexampleCode.GEOFENCE_INTRUSION,
                            zone=zone,
                            time_s=now,
                            entities=(rid,),
                            place_xy_m=point,
                            rule=Rule.GEOFENCE_NO_ENTRY,
                        )
                    )

    def scan_contacts() -> None:
        flags = np.asarray(sim.state.arrays["det_flags"], dtype=np.int64)
        poses = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)
        for i in range(len(ids)):
            for k in range(i + 1, len(ids)):
                if flags[i, k, _CONTACT] and (i, k) not in reported:
                    reported.add((i, k))
                    found.append(
                        Counterexample(
                            CounterexampleCode.COLLISION,
                            time_s=sim.state.tick * params.DT,
                            entities=(ids[i], ids[k]),
                            place_xy_m=(
                                float((poses[i, 0] + poses[k, 0]) / 2),
                                float((poses[i, 1] + poses[k, 1]) / 2),
                            ),
                            rule=Rule.COLLISION_FREE,
                        )
                    )

    scan_hazards()
    for _ in range(ticks):
        sim.step()
        scan_hazards()
        scan_contacts()
    waypoint = np.asarray(sim.state.arrays["script_wp"], dtype=np.int64)
    for i, rid in enumerate(ids):
        if routes[i] and waypoint[i] == 0:
            found.append(
                Counterexample(
                    CounterexampleCode.NO_PROGRESS,
                    time_s=ticks * params.DT,
                    entities=(rid,),
                    rule=Rule.PROGRESS_REQUIRED,
                )
            )
    found.sort(key=lambda c: (c.time_s or 0.0, _SEVERITY[CounterexampleCode(c.code)], c.entities))
    return RolloutOutcome(tuple(found), sim.state_hash(), ticks)


def validate_plan(plan: Plan, static: StaticMap, config: RolloutConfig) -> ValidationResult:
    """Run the stages in order and stop at the first that fails.

    A plan with ``escalate`` set goes to the operator and is not validated as motion. Accepted
    means no counterexample at any stage, under the stated assumptions of this module.
    """
    if plan.escalate:
        return ValidationResult(False, True, "escalated")
    geofence = check_geofence(plan, config.hazard_zone_ids)
    if geofence:
        return ValidationResult(False, False, "geofence", geofence)
    compiled = compile_plan(plan, static)
    if compiled.counterexamples:
        return ValidationResult(False, False, "static", compiled.counterexamples)
    outcome = run_plan_rollout(compiled.paths, static, config)
    return ValidationResult(
        not outcome.counterexamples, False, "rollout", outcome.counterexamples, outcome.final_hash
    )
