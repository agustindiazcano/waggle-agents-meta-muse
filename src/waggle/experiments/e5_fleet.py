"""C4 fleet planning for E5, implemented, not evaluated, with MOVE-only execution.

A single proposal at run start uses planner-v1 and the existing plan validator. The
caller supplies topology and rollout policy explicitly. Accepted routes replace the
scripted driver's routes; the original dynamics and fast layer still run. Non-MOVE
actions, wait_for dependencies and capacity-one corridors are refused. Production
dispatch, online replanning and general fleet scheduling are outside this adapter.
Original work destinations must remain in order and the terminal must match. Only
original destinations count as work; intermediate navigation nodes do not.
"""

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict

import numpy as np

from waggle.governance.organizer_fleet import FleetPlanResult, validate_fleet_plan
from waggle.llm.client import LlmClient
from waggle.llm.crisis_adapter import PLANNER_PROMPT_HASH, PLANNER_PROMPT_VERSION, LlmPlanProposer
from waggle.llm.errors import LlmError
from waggle.sim import engine, robots, scenarios, scripted, state
from waggle.validation.path_compiler import CompiledPath, StaticMap
from waggle.validation.plan import PlanContext
from waggle.validation.plan_rollout import RolloutConfig

logger = logging.getLogger("waggle.experiments.e5.fleet")


def fleet_record(
    result: FleetPlanResult | None, routes: dict[str, list[list[float]]]
) -> dict[str, object]:
    """Report the planner outcome and prompt identity alongside the usual E5 record."""
    return {
        "fleet_planner_calls": int(result is not None),
        "fleet_prompt_version": PLANNER_PROMPT_VERSION if result is not None else None,
        "fleet_prompt_hash": PLANNER_PROMPT_HASH if result is not None else None,
        "fleet_planner_status": (
            "disabled"
            if result is None
            else "accepted"
            if result.plan is not None
            else "error"
            if result.reason == "planner_error"
            else "rejected"
        ),
        "fleet_planner_reason": None if result is None else result.reason,
        "fleet_routes": routes,
        "fleet_execution": "one_shot" if result is not None and result.plan is not None else None,
        "fleet_evaluation_note": (
            None
            if result is None
            else "Implemented, not evaluated. Accepted C4 plans execute one-shot; "
            "the baseline loops. "
            "Tasks completed and throughput are not directly comparable after the terminal "
            "without an aligned evaluation protocol. Rejected plans retain the baseline driver."
        ),
    }


def fleet_feedback(scenario: scenarios.Scenario, static: StaticMap, config: RolloutConfig) -> str:
    """Canonical trusted mission data through the proposer's existing feedback input.

    Includes original tasks, topology, poses and rollout policy in the prompt and
    request digest. A topology or mission change must not reuse an old cached plan.
    """
    return json.dumps(
        {
            "scenario": scenario.to_dict(),
            "static": asdict(static),
            "policy": {**asdict(config), "hazard_zone_ids": sorted(config.hazard_zone_ids)},
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def fleet_context(
    scenario: scenarios.Scenario, static: StaticMap, config: RolloutConfig
) -> PlanContext:
    """Bind trusted topology, robot ids, map and safety margin to this exact scenario."""
    ids = tuple(f"robot-{i}" for i in range(len(scenario.robots)))
    if static.world != scenarios.load_map(scenario.map_name):
        raise ValueError("fleet map differs from scenario")
    if set(static.robot_start) != set(ids) or set(config.robot_kinds) != set(ids):
        raise ValueError("fleet robots differ from scenario")
    if config.separation_margin_m != scenario.separation_margin:
        raise ValueError("fleet separation margin differs from scenario")
    at = {n.node_id: (n.x_m, n.y_m) for n in static.graph.nodes}
    fleet = robots.RobotFleet(
        [r.kind for r in scenario.robots], load_raised=[r.load_raised for r in scenario.robots]
    )
    for rid, spec in zip(ids, scenario.robots, strict=True):
        point = at.get(static.robot_start[rid])
        if point is None or not all(
            math.isclose(a, b, abs_tol=1e-9) for a, b in zip(point, spec.pose[:2], strict=True)
        ):
            raise ValueError("fleet start differs from scenario")
        if config.robot_kinds[rid] != spec.kind:
            raise ValueError("fleet robot kind differs from scenario")
    return PlanContext(
        dict(zip(ids, map(float, fleet.max_speed), strict=True)),
        frozenset(p.package_id for p in scenario.packages),
        frozenset(z.id for z in static.world.zones),
    )


def propose_fleet_plan(
    client: LlmClient,
    *,
    scenario: scenarios.Scenario,
    mission_id: str,
    context: PlanContext,
    static: StaticMap,
    config: RolloutConfig,
    timeout_s: float,
    max_response_chars: int,
) -> FleetPlanResult:
    """Make one bounded planner call; errors leave the pre-existing scenario unchanged."""
    proposer = LlmPlanProposer(client, mission_id=mission_id, context=context, task_id=mission_id)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        raw = pool.submit(proposer.propose, fleet_feedback(scenario, static, config)).result(
            timeout=timeout_s
        )
    except (FutureTimeout, LlmError) as exc:
        logger.warning("fleet planner failed: %s", type(exc).__name__)
        return FleetPlanResult(None, reason="planner_error")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    result = validate_fleet_plan(
        raw,
        mission_id=mission_id,
        context=context,
        static=static,
        config=config,
        max_response_chars=max_response_chars,
    )
    if result.plan is not None and _mission_work_indices(result.paths, scenario) is None:
        return FleetPlanResult(None, reason="mission_mismatch")
    return result


def _same_point(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return all(math.isclose(x, y, abs_tol=1e-9) for x, y in zip(a, b, strict=True))


def _mission_work_indices(
    paths: tuple[CompiledPath, ...], scenario: scenarios.Scenario
) -> tuple[frozenset[int], ...] | None:
    """Require all original work destinations in order, with the same terminal."""
    work: list[frozenset[int]] = []
    for i, robot in enumerate(scenario.robots):
        route = [
            point for path in paths if path.robot_id == f"robot-{i}" for point in path.waypoints
        ]
        if not robot.route:
            if route:
                return None
            work.append(frozenset())
            continue
        if not route or not _same_point(route[-1], robot.route[-1]):
            return None
        indices: list[int] = []
        cursor = 0
        for destination in robot.route:
            match = next(
                (j for j in range(cursor, len(route)) if _same_point(route[j], destination)), None
            )
            if match is None:
                return None
            indices.append(match)
            cursor = match + 1
        work.append(frozenset(indices))
    return tuple(work)


def apply_fleet_plan(
    result: FleetPlanResult, sim: engine.Engine, scenario: scenarios.Scenario
) -> dict[str, list[list[float]]]:
    """Replace only the driver's route system before tick zero, after full acceptance.

    Each robot preserves its original ordered work destinations and terminal. Only
    those destinations count as completed tasks; navigation nodes do not count.
    Each robot uses the minimum of its node speed caps for the entire one-shot route.
    The driver's private fleet is separate from both the dynamics and the control rig,
    so this cap can only reduce requested speed and cannot change physical limits.
    """
    if result.plan is None:
        return {}
    if sim.state.tick != 0:
        raise ValueError("fleet plan must be applied before the first tick")
    work_indices = _mission_work_indices(result.paths, scenario)
    if work_indices is None:
        raise ValueError("fleet plan changes the original mission")
    ids = tuple(f"robot-{i}" for i in range(len(scenario.robots)))
    routes: dict[str, list[tuple[float, float]]] = {rid: [] for rid in ids}
    for path in result.paths:
        routes[path.robot_id].extend(path.waypoints)
    driver_fleet = robots.RobotFleet(
        [r.kind for r in scenario.robots], load_raised=[r.load_raised for r in scenario.robots]
    )
    for i, rid in enumerate(ids):
        caps = [
            n.speed_cap_mps
            for n in result.plan.nodes
            if n.robot_id == rid and n.speed_cap_mps is not None
        ]
        driver_fleet.max_speed[i] = min([float(driver_fleet.max_speed[i]), *caps])
    # The existing loop=False driver stops after its first waypoint. Use its sequential
    # loop=True transition, then stop explicitly at the terminal without restarting.
    driver = scripted.WaypointDriver(driver_fleet, [routes[rid] for rid in ids], loop=True)
    drive = driver.system()

    def step(sim_state: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        waypoint = np.asarray(sim_state.arrays["script_wp"], dtype=np.int64)
        tasks = np.asarray(sim_state.arrays["script_tasks"], dtype=np.int64)
        before_wp, before_tasks = waypoint.copy(), tasks.copy()
        drive(sim_state, rngs)
        arrived = tasks > before_tasks
        tasks[:] = before_tasks
        for i, rid in enumerate(ids):
            if arrived[i]:
                if int(before_wp[i]) in work_indices[i]:
                    tasks[i] += 1
                if before_wp[i] == len(routes[rid]) - 1:
                    waypoint[i] = len(routes[rid])

    sim.systems[0] = step
    return {rid: [[float(x), float(y)] for x, y in route] for rid, route in routes.items()}
