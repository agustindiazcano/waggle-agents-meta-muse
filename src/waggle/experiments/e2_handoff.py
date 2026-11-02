"""E2 handoff chaos runner: one scene, one arm, one seed in a fresh schema, and the summary.

``run_scene`` runs a scene of ``waggle.experiments.e2_handoff_scenes`` on a migrated schema and
lets the oracles judge the event log, never the answers the repositories gave. A log the oracle
cannot judge is an undecided record and never a pass. ``run_fresh`` creates the schema, migrates
it and drops it on every path, like the chaos runner. ``aggregate_scenes`` gives raw counts and
Wilson 95 percent intervals over decided runs per arm and scene, with the failing seeds listed
(AGENTS.md 9.5); fewer than 30 decided runs are marked small.

The scenes are scripted, not random in time: the seed picks the kill point and the replay mode.
Two runs with the same seed give the same record. This is a handoff-path complement to the chaos
runner of ``e2_chaos``, not a replacement, and nothing here has been run as an experiment.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import uuid4

from psycopg import sql

from waggle.db.connection import Database
from waggle.db.schema import migrate
from waggle.experiments.e1_stats import wilson
from waggle.experiments.e2_handoff_oracle import judge_handoffs
from waggle.experiments.e2_handoff_scenes import (
    ARMS,
    SCENE_FUNCTIONS,
    SCENES,
    TARGET_LAYERS,
    Bench,
    plan_for,
    scene_schedule,
)
from waggle.experiments.e2_log import load_oracle_inputs
from waggle.experiments.e2_oracle import OracleError, judge_tasks, judge_zones

SMALL_SAMPLE = 30
METRICS = (
    "double_deliveries",
    "stale_handoffs_accepted",
    "dependents_unblocked_early",
    "stale_writes_accepted",
    "double_assignments",
    "violation_samples",
    "tasks_stuck",
)


@dataclass(frozen=True)
class MetricSummary:
    """One metric over the decided runs of one arm and scene."""

    runs_with_event: int
    events: int
    wilson95: tuple[float, float]
    failing_seeds: tuple[int, ...]


@dataclass(frozen=True)
class SceneSummary:
    """Counts of one arm and scene over all its seeds."""

    runs: int
    decided_runs: int
    undecided_seeds: tuple[int, ...]
    small_sample: bool
    metrics: dict[str, MetricSummary]


def _record(arm: str, scene: str, seed: int) -> dict[str, object]:
    plan = plan_for(seed, scene)
    return {
        "arm": arm,
        "scene": scene,
        "seed": seed,
        "target_layer": TARGET_LAYERS[scene],
        "kill_point": plan.kill_point.value,
        "replay_mode": plan.replay_mode.value,
        "undecided": False,
        "reason": None,
        "report": None,
        "outcomes": {},
    }


def run_scene(database: Database, arm: str, scene: str, seed: int) -> dict[str, object]:
    """Run ``scene`` for ``arm`` and ``seed`` on a migrated schema and return its record."""
    if arm not in ARMS or scene not in SCENES:
        raise ValueError("unknown arm or scene")
    record = _record(arm, scene, seed)
    bench = Bench(database, arm, scene_schedule(seed), SCENES.index(scene))
    SCENE_FUNCTIONS[scene](bench, plan_for(seed, scene))
    try:
        events, states = load_oracle_inputs(database)
        tasks = judge_tasks(events, states)
        handoffs = judge_handoffs(events, bench.result.dependencies)
        zones = judge_zones(bench.result.samples)
    except OracleError as error:
        record["undecided"] = True
        record["reason"] = str(error)
        return record
    record["report"] = {
        "double_deliveries": handoffs.double_deliveries,
        "stale_handoffs_accepted": handoffs.stale_handoffs_accepted,
        "dependents_unblocked_early": handoffs.dependents_unblocked_early,
        "handoffs_accepted": handoffs.handoffs_accepted,
        "stale_writes_accepted": tasks.stale_writes_accepted,
        "double_assignments": tasks.double_assignments,
        "violation_samples": zones.violation_samples,
        "undecided_samples": zones.undecided_samples,
        "tasks_done": tasks.tasks_done,
        "tasks_total": tasks.tasks_total,
        "tasks_stuck": len(tasks.tasks_stuck),
    }
    record["outcomes"] = dict(bench.result.outcomes)
    return record


def run_fresh(root: Database, arm: str, scene: str, seed: int) -> dict[str, object]:
    """Run one scene in its own schema; the schema is dropped on every path."""
    name = f"e2h_{arm}_{scene.lower()}_{seed}_{uuid4().hex[:8]}"
    with root.transaction() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        database = Database(root.dsn, schema=name)
        migrate(database, expected_revision=0)
        return run_scene(database, arm, scene, seed)
    finally:
        with root.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def _count(report: Mapping[str, object], name: str) -> int:
    value = report[name]
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _summarize(records: Sequence[Mapping[str, object]]) -> SceneSummary:
    decided = [r for r in records if not r["undecided"]]
    metrics: dict[str, MetricSummary] = {}
    for name in METRICS:
        counts: list[tuple[int, int]] = []
        for record in decided:
            report = record["report"]
            seed = record["seed"]
            if not isinstance(report, dict) or type(seed) is not int:
                raise ValueError("a decided record needs a report and an integer seed")
            counts.append((seed, _count(report, name)))
        failing = tuple(seed for seed, value in counts if value > 0)
        metrics[name] = MetricSummary(
            len(failing),
            sum(value for _, value in counts),
            wilson(len(failing), len(counts)),
            failing,
        )
    undecided = tuple(seed for r in records if r["undecided"] if type(seed := r["seed"]) is int)
    return SceneSummary(len(records), len(decided), undecided, len(decided) < SMALL_SAMPLE, metrics)


def aggregate_scenes(
    records: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, SceneSummary]]:
    """Summaries per arm and scene. An undecided run is counted apart, never as a pass."""
    summary: dict[str, dict[str, SceneSummary]] = {}
    for arm in ARMS:
        for scene in SCENES:
            chosen = [r for r in records if r["arm"] == arm and r["scene"] == scene]
            if chosen:
                summary.setdefault(arm, {})[scene] = _summarize(chosen)
    return summary
