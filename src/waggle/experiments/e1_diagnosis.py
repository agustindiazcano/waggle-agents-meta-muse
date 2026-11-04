"""Cause classification for the remaining E1 stops and collisions in S03, S06 and S11.

Diagnosis only: this module reads scenario geometry and finished E1 run records and
labels each stop or collision. It never calls the control layer, never changes a
threshold and never writes a result file. Seeds outside the development set are
refused, so a held-out seed cannot be diagnosed by accident. A stop with no
geometric cause in the scenario is labelled ``UNEXPLAINED_STOP`` instead of being
silently passed.
"""

import itertools
import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from waggle.sim import scenarios

Point = tuple[float, float]
ON_ROUTE_M = 0.75
"""A stopped human within this distance of a robot route counts as on the route."""


class Cause(StrEnum):
    """Closed set of causes for an E1 stop or collision in the target scenarios."""

    NO_STOP_OR_COLLISION = "no_stop_or_collision"
    HEAD_ON_ONE_LANE = "head_on_one_lane"
    HUMAN_STOPPED_ON_ROUTE = "human_stopped_on_route"
    ROBOT_ROBOT_COLLISION_HEAD_ON = "robot_robot_collision_head_on"
    ROBOT_ROBOT_COLLISION_OTHER = "robot_robot_collision_other"
    HUMAN_COLLISION_INSIDE_STOPPING_DISTANCE = "human_collision_inside_stopping_distance"
    HUMAN_COLLISION_OUTSIDE_STOPPING_DISTANCE = "human_collision_outside_stopping_distance"
    UNEXPLAINED_STOP = "unexplained_stop"
    UNEXPLAINED_COLLISION = "unexplained_collision"


@dataclass(frozen=True)
class ScenarioFacts:
    """Geometry of one generated scenario, read without running it."""

    scenario: str
    seed: int
    robot_count: int
    human_count: int
    head_on_pair: bool
    human_final_point: Point | None
    human_route_distance_m: float | None
    human_stopped_on_route: bool
    adversarial_fraction: float | None


@dataclass(frozen=True)
class Diagnosis:
    """One classified run record with the evidence for the label."""

    configuration: str
    scenario: str
    seed: int
    cause: Cause
    stop_episodes: int
    false_stops: int
    human_collisions: int
    robot_collisions: int
    tasks_completed: int
    evidence: str


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    denom = dx * dx + dy * dy
    f = (
        0.0
        if denom == 0.0
        else max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom))
    )
    return math.hypot(point[0] - (start[0] + f * dx), point[1] - (start[1] + f * dy))


def _route_distance(point: Point, scenario: scenarios.Scenario) -> float:
    best = math.inf
    for robot in scenario.robots:
        chain = [(robot.pose[0], robot.pose[1]), *robot.route]
        for start, end in itertools.pairwise(chain):
            best = min(best, _point_segment_distance(point, start, end))
    return best


def _head_on(scenario: scenarios.Scenario) -> bool:
    if len(scenario.robots) != 2:
        return False
    first, second = scenario.robots
    first_start = (first.pose[0], first.pose[1])
    second_start = (second.pose[0], second.pose[1])
    return bool(
        first.route
        and second.route
        and first.route[-1] == second_start
        and second.route[-1] == first_start
    )


def scenario_facts(scenario_id: str, seed: int) -> ScenarioFacts:
    """Geometry facts of one scenario and seed, generated but never run."""
    scenario = scenarios.generate(scenario_id, seed)
    final_point: Point | None = None
    distance: float | None = None
    stopped_on_route = False
    if scenario.humans:
        plan = scenario.humans[0].plan
        final_point = plan.path[-1] if plan.path else scenario.humans[0].start
        distance = _route_distance(final_point, scenario)
        stopped_on_route = distance <= ON_ROUTE_M
    fraction: float | None = None
    for _, text in scenario.events:
        match = re.search(r"fraction ([0-9.]+)", text)
        if match:
            fraction = float(match.group(1))
    return ScenarioFacts(
        scenario=scenario_id,
        seed=seed,
        robot_count=len(scenario.robots),
        human_count=len(scenario.humans),
        head_on_pair=_head_on(scenario),
        human_final_point=final_point,
        human_route_distance_m=distance,
        human_stopped_on_route=stopped_on_route,
        adversarial_fraction=fraction,
    )


def _counts(record: dict[str, Any]) -> dict[str, int]:
    counts = record.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("run record has no counts mapping")
    return {str(k): int(v) for k, v in counts.items()}


def classify_record_with_facts(
    configuration: str, record: dict[str, Any], facts: ScenarioFacts
) -> Diagnosis:
    """Classify one run record against precomputed scenario geometry."""
    counts = _counts(record)
    stops_raw = record.get("stop_episodes") or {}
    stops = sum(int(v) for v in stops_raw.values()) if isinstance(stops_raw, dict) else 0
    false_stops = int(record.get("false_stops") or 0)
    tasks = int(record.get("tasks_completed") or 0)
    human_hits = counts.get("human_collisions", 0)
    robot_hits = counts.get("robot_collisions", 0)
    detail = (
        f"stops={stops} false_stops={false_stops} tasks={tasks} "
        f"human_final={facts.human_final_point} route_distance_m={facts.human_route_distance_m} "
        f"fraction={facts.adversarial_fraction}"
    )
    if human_hits > 0:
        if facts.adversarial_fraction is None:
            cause, evidence = Cause.UNEXPLAINED_COLLISION, f"human collision, no timing {detail}"
        elif facts.adversarial_fraction < 1.0:
            cause = Cause.HUMAN_COLLISION_INSIDE_STOPPING_DISTANCE
            evidence = f"human arrives inside the stopping distance {detail}"
        else:
            cause = Cause.HUMAN_COLLISION_OUTSIDE_STOPPING_DISTANCE
            evidence = f"human arrives outside the stopping distance {detail}"
    elif robot_hits > 0:
        if facts.head_on_pair:
            cause = Cause.ROBOT_ROBOT_COLLISION_HEAD_ON
            evidence = f"two robots swap ends of the same one-lane aisle {detail}"
        else:
            cause, evidence = Cause.ROBOT_ROBOT_COLLISION_OTHER, f"robot contact {detail}"
    elif stops > 0 and facts.head_on_pair and facts.human_count == 0:
        cause = Cause.HEAD_ON_ONE_LANE
        evidence = (
            "two robots meet head-on in the one-lane aisle and each is static "
            f"structure for the other; no humans, so every stop reads false {detail}"
        )
    elif stops > 0 and facts.human_stopped_on_route:
        cause = Cause.HUMAN_STOPPED_ON_ROUTE
        evidence = (
            "scripted human walks onto the route and stands there for the rest "
            f"of the run; the robot holds in front of it {detail}"
        )
    elif stops > 0:
        cause, evidence = Cause.UNEXPLAINED_STOP, f"stop with no geometric cause {detail}"
    else:
        cause, evidence = Cause.NO_STOP_OR_COLLISION, f"no stop and no collision {detail}"
    return Diagnosis(
        configuration=configuration,
        scenario=str(record.get("scenario", facts.scenario)),
        seed=int(record.get("seed", facts.seed)),
        cause=cause,
        stop_episodes=stops,
        false_stops=false_stops,
        human_collisions=human_hits,
        robot_collisions=robot_hits,
        tasks_completed=tasks,
        evidence=evidence,
    )


def classify_run(
    configuration: str,
    record: dict[str, Any],
    allowed_seeds: dict[str, list[int]] | None = None,
) -> Diagnosis:
    """Classify one record, optionally refusing seeds outside the development set."""
    scenario_id = str(record.get("scenario", ""))
    seed = int(record.get("seed", -1))
    if allowed_seeds is not None and seed not in allowed_seeds.get(scenario_id, []):
        raise ValueError(f"seed {seed} for {scenario_id} is not in the development seed set")
    return classify_record_with_facts(configuration, record, scenario_facts(scenario_id, seed))


def diagnose_document(
    document: dict[str, Any], allowed_seeds: dict[str, list[int]]
) -> list[Diagnosis]:
    """Classify every run of one committed E1 result document."""
    configuration = str(document["configuration"])
    return [
        classify_run(configuration, run, allowed_seeds)
        for run in document["runs"]
        if str(run.get("scenario", "")) in allowed_seeds
    ]


def summarize_committed(
    results_dir: Path, allowed_seeds: dict[str, list[int]]
) -> dict[str, dict[str, int]]:
    """Per-scenario cause counts over the latest committed file of each configuration.

    Only target scenarios present in ``allowed_seeds`` are counted. When two files
    of one configuration exist, the one with the later document date wins.
    """
    latest: dict[str, dict[str, Any]] = {}
    for path in sorted(results_dir.glob("*.json")):
        document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        name = str(document.get("configuration", ""))
        if name and (name not in latest or str(document["date"]) > str(latest[name]["date"])):
            latest[name] = document
    summary: dict[str, dict[str, int]] = {sid: {} for sid in allowed_seeds}
    for document in latest.values():
        for item in diagnose_document(document, allowed_seeds):
            if item.scenario in summary:
                bucket = summary[item.scenario]
                bucket[item.cause.name] = bucket.get(item.cause.name, 0) + 1
    return summary
