"""Stage D of the plan validator: K human variants and all-pass aggregation (ADR-023, 025).

The validator compiles the plan, checks geofences, and then runs K seeded rollouts with
hidden humans sampled from the belief state. The plan passes only if every one of the K
variants executes without a counterexample. A variant that raises or times out fails closed.
"""

import dataclasses
import logging
import math
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from waggle.sim import detector, engine, humans, params, robots, scripted
from waggle.validation.belief import HumanPrior, HumanState, sample_humans, variant_seeds
from waggle.validation.counterexample import Counterexample, CounterexampleCode, Rule
from waggle.validation.geofence import check_geofence
from waggle.validation.geometry import polygon_box, segment_box_distance
from waggle.validation.path_compiler import CompiledPath, StaticMap, compile_plan
from waggle.validation.plan import Plan
from waggle.validation.plan_rollout import RolloutConfig, RolloutOutcome

logger = logging.getLogger("waggle.validation.variants")

_SEVERITY = {code: index for index, code in enumerate(CounterexampleCode)}
_CONTACT, _VIOLATION = 0, 1


@dataclass(frozen=True)
class AggregatedResult:
    """The aggregated verdict across K variant rollouts (ADR-023)."""

    accepted: bool
    counterexamples: tuple[Counterexample, ...] = ()
    escalated: bool = False
    stage: str = "variants"
    variant_hashes: tuple[str | None, ...] = ()
    notes: tuple[str, ...] = field(default=())


def _hazard_boxes(static: StaticMap, hazard: frozenset[str]) -> dict[str, tuple[float, ...]]:
    zones = {z.id: polygon_box(z.polygon.points) for z in static.world.zones}
    unknown = sorted(hazard - set(zones))
    if unknown:
        raise ValueError("a hazard zone is not in the map")
    return {z: zones[z] for z in sorted(hazard)}


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


def run_variant_rollout(
    paths: Sequence[CompiledPath],
    static: StaticMap,
    config: RolloutConfig,
    human_states: Sequence[HumanState],
    seed: int,
) -> RolloutOutcome:
    """Drive compiled paths with the simulator dynamics and human walkers over horizon H."""
    ids = sorted(static.robot_start)
    missing = [rid for rid in ids if rid not in config.robot_kinds]
    if missing:
        raise ValueError("a robot has no robot kind")

    boxes = _hazard_boxes(static, config.hazard_zone_ids)
    routes = _routes(paths, ids)
    pose = _poses(ids, routes, static)
    fleet = robots.RobotFleet([config.robot_kinds[rid] for rid in ids])

    num_humans = len(human_states)
    if num_humans > 0:
        human_starts = np.array([h.position for h in human_states], dtype=np.float64)
        human_plans: list[humans.HumanPlan] = []
        for h in human_states:
            speed = math.hypot(h.velocity[0], h.velocity[1])
            if speed > 0.0:
                human_plans.append(humans.HumanPlan.walker(speed, turn_sigma=0.0))
            else:
                human_plans.append(
                    humans.HumanPlan(
                        kind="scripted",
                        speed=1.0,
                        path=(h.position, h.position),
                        start_tick=999999999,
                    )
                )
    else:
        human_starts = np.zeros((0, 2), dtype=np.float64)
        human_plans = []

    crowd = humans.Crowd(human_plans, static.world)
    driver = scripted.WaypointDriver(fleet, routes, loop=False)
    det = detector.Detector(
        fleet.params,
        separation_margin=config.separation_margin_m,
        near_miss_margin=config.separation_margin_m,
    )

    arrays = {
        **fleet.initial_arrays(pose, np.zeros(len(ids))),
        **crowd.initial_arrays(human_starts),
        **driver.initial_arrays(),
        **det.initial_arrays(pose, human_starts),
    }
    if num_humans > 0:
        headings = np.array(
            [
                math.atan2(h.velocity[1], h.velocity[0])
                if (h.velocity[0] != 0.0 or h.velocity[1] != 0.0)
                else 0.0
                for h in human_states
            ],
            dtype=np.float64,
        )
        arrays["human_heading"] = headings

    systems = [driver.system(), fleet.system(), crowd.system(), det.system()]
    sim = engine.Engine(seed, arrays, systems, {"humans": num_humans})

    found: list[Counterexample] = []
    hit_zones: set[tuple[str, str]] = set()
    reported_robot_pairs: set[tuple[int, int]] = set()
    reported_human_contacts: set[tuple[int, int]] = set()
    reported_human_violations: set[tuple[int, int]] = set()

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
                # segment_box_distance accepts point coordinates as a tuple
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
        now = sim.state.tick * params.DT
        flags = np.asarray(sim.state.arrays["det_flags"], dtype=np.int64)
        poses = np.asarray(sim.state.arrays["robot_pose"], dtype=np.float64)
        h_poses = (
            np.asarray(sim.state.arrays["human_pos"], dtype=np.float64)
            if num_humans > 0
            else np.zeros((0, 2))
        )

        # Robot - human contacts and violations
        for i in range(len(ids)):
            for h in range(num_humans):
                if flags[i, h, _CONTACT] and (i, h) not in reported_human_contacts:
                    reported_human_contacts.add((i, h))
                    found.append(
                        Counterexample(
                            CounterexampleCode.COLLISION,
                            time_s=now,
                            entities=(ids[i], "human"),
                            place_xy_m=(float(h_poses[h, 0]), float(h_poses[h, 1])),
                            rule=Rule.COLLISION_FREE,
                        )
                    )
                if flags[i, h, _VIOLATION] and (i, h) not in reported_human_violations:
                    reported_human_violations.add((i, h))
                    found.append(
                        Counterexample(
                            CounterexampleCode.SEPARATION_VIOLATION,
                            time_s=now,
                            entities=(ids[i], "human"),
                            place_xy_m=(float(h_poses[h, 0]), float(h_poses[h, 1])),
                            min_clearance_m=0.0,
                            rule=Rule.SEPARATION_MIN,
                        )
                    )

        # Robot - robot contacts
        offset = num_humans
        for i in range(len(ids)):
            for k in range(i + 1, len(ids)):
                if flags[i, offset + k, _CONTACT] and (i, k) not in reported_robot_pairs:
                    reported_robot_pairs.add((i, k))
                    found.append(
                        Counterexample(
                            CounterexampleCode.COLLISION,
                            time_s=now,
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


def aggregate(results: Sequence[object], k: int) -> AggregatedResult:
    """Aggregate K variant rollout outcomes. Rejects if any variant failed or raised (ADR-023).

    ``k`` is the number of variants that were required, not the length of ``results``, so a
    short list is a rejection and never a pass.
    """
    target_k = k
    if len(results) < target_k or target_k < 1:
        return AggregatedResult(accepted=False, counterexamples=(), stage="variants")

    all_cxs: list[Counterexample] = []
    hashes: list[str | None] = []
    has_failure = False

    for v, r in enumerate(results):
        if r is None or isinstance(r, BaseException):
            has_failure = True
            hashes.append(None)
            continue

        cxs = getattr(r, "counterexamples", None)
        final_hash = getattr(r, "final_hash", None)
        hashes.append(str(final_hash) if final_hash is not None else None)

        if cxs is None or not isinstance(cxs, Sequence):
            has_failure = True
            continue

        if len(cxs) > 0:
            has_failure = True
            for c in cxs:
                if isinstance(c, Counterexample):
                    all_cxs.append(dataclasses.replace(c, variant=v))

    # Ordered by time then severity then variant, with the variant index set
    all_cxs.sort(
        key=lambda c: (
            c.time_s if c.time_s is not None else 0.0,
            _SEVERITY[CounterexampleCode(c.code)],
            c.variant if c.variant is not None else 0,
            c.entities,
        )
    )

    accepted = (not has_failure) and (len(all_cxs) == 0) and (len(results) == target_k)
    return AggregatedResult(
        accepted=accepted,
        counterexamples=tuple(all_cxs),
        variant_hashes=tuple(hashes),
        stage="variants",
    )


def _stopping_distance_m(config: RolloutConfig) -> float:
    """Largest distance a fleet robot needs to stop from its top speed, from the robot params.

    Braking distance v^2 / (2 a) plus the distance covered during the actuation delay.
    """
    worst = 0.0
    for kind in config.robot_kinds.values():
        p = params.ROBOT_PARAMS[kind]
        worst = max(worst, p.max_speed**2 / (2.0 * p.decel) + p.max_speed * p.actuation_delay)
    return worst


def validate_with_variants(
    plan: Plan,
    static: StaticMap,
    config: RolloutConfig,
    prior: HumanPrior,
    *,
    k: int,
    max_attempts: int,
    workers: int = 1,
) -> AggregatedResult:
    """Run K human variants in order and aggregate. Fails closed on any error (ADR-023).

    ``k`` (5 in ADR-023) and the sampler attempt cap are chosen by the caller. A human starts
    no closer to a robot than that robot's stopping distance from top speed.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    if plan.escalate:
        return AggregatedResult(accepted=False, escalated=True, stage="escalated")

    geofence = check_geofence(plan, config.hazard_zone_ids)
    if geofence:
        return AggregatedResult(accepted=False, counterexamples=geofence, stage="geofence")

    compiled = compile_plan(plan, static)
    if compiled.counterexamples:
        return AggregatedResult(
            accepted=False, counterexamples=compiled.counterexamples, stage="static"
        )

    seeds = variant_seeds(config.seed, 0, k)
    stop_m = _stopping_distance_m(config)

    def run_one_variant(index: int) -> RolloutOutcome:
        v_seed = seeds[index]
        sampled = sample_humans(
            prior,
            static,
            static.robot_start,
            v_seed,
            min_stop_distance_m=stop_m,
            max_attempts=max_attempts,
        )
        return run_variant_rollout(compiled.paths, static, config, sampled.humans, v_seed)

    results: list[object]
    if workers == 1 or k == 1:
        results = []
        for i in range(k):
            try:
                results.append(run_one_variant(i))
            except Exception as exc:
                logger.warning("variant %d failed: %s", i, type(exc).__name__)
                results.append(exc)
    else:
        with ThreadPoolExecutor(max_workers=min(workers, k)) as pool:
            futures = [pool.submit(run_one_variant, i) for i in range(k)]
            results = []
            for i, f in enumerate(futures):
                try:
                    results.append(f.result())
                except Exception as exc:
                    logger.warning("variant %d failed: %s", i, type(exc).__name__)
                    results.append(exc)

    return aggregate(results, k=k)
