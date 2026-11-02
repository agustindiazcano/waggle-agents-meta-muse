"""Unit tests for Stage D variant rollout validation and all-pass aggregation (ADR-023, 025).

Tests verify that:
- aggregate requires all K results and zero counterexamples to pass (fail closed).
- fewer than K results, None, or a variant exception rejects.
- a mutant aggregator that accepts on K-1 passes is caught.
- counterexamples are ordered by time, severity, and variant index.
- validate_with_variants is deterministic: workers=1 equals workers=2 on the state hash.
- a planted human variant makes the plan fail in that variant, rejecting the aggregate.
- the plan without the planted fault is accepted.
- no global random or banned imports are used.
"""

import ast
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from waggle.coordination.corridors import Direction
from waggle.coordination.routing import AisleEdge, AisleGraph, AisleNode
from waggle.sim.params import RobotKind
from waggle.sim.scenarios import load_map
from waggle.validation.belief import HumanPrior
from waggle.validation.counterexample import Counterexample, CounterexampleCode, Rule
from waggle.validation.path_compiler import StaticMap, compile_plan
from waggle.validation.plan import Plan, PlanContext, parse_plan
from waggle.validation.plan_rollout import RolloutConfig, RolloutOutcome, run_plan_rollout
from waggle.validation.variants import (
    AggregatedResult,
    aggregate,
    run_variant_rollout,
    validate_with_variants,
)

ZONES = frozenset(
    {"lane_1", "station_1", "depot_n", "corridor_s", "aisle_1", "connector_e", "corridor_n"}
)
CONTEXT = PlanContext({"R1": 1.5, "R2": 1.5}, frozenset({"ITEM-1"}), ZONES)


def _both(a: str, b: str, cost: float, corridor: str | None = None) -> tuple[AisleEdge, ...]:
    back = Direction.REVERSE if corridor else Direction.FORWARD
    return (AisleEdge(a, b, cost, corridor), AisleEdge(b, a, cost, corridor, back))


def _graph() -> AisleGraph:
    points = {
        "sw": (3.0, 2.0),
        "sm": (20.0, 2.0),
        "se": (37.0, 2.0),
        "nw": (3.0, 22.0),
        "nm": (20.0, 22.0),
        "ne": (37.0, 22.0),
        "isle": (20.0, 9.0),
    }
    edges = (
        *_both("sw", "sm", 17.0),
        *_both("sm", "se", 17.0),
        *_both("nw", "nm", 18.0),
        *_both("nm", "ne", 17.0),
        *_both("se", "ne", 20.0),
        *_both("sw", "nw", 20.0, "lane_1"),
    )
    return AisleGraph(tuple(AisleNode(k, *v) for k, v in points.items()), edges)


def _static(robot_start: dict[str, str]) -> StaticMap:
    return StaticMap(
        world=load_map("A"),
        graph=_graph(),
        zone_anchor={
            "station_1": "nw",
            "depot_n": "ne",
            "corridor_s": "sm",
            "aisle_1": "isle",
            "connector_e": "se",
            "lane_1": "sw",
        },
        robot_start=robot_start,
        clearance_m=0.9,
    )


def _config(**over: object) -> RolloutConfig:
    base: dict[str, object] = {
        "robot_kinds": {"R1": RobotKind.CARRIER, "R2": RobotKind.CARRIER},
        "hazard_zone_ids": frozenset(),
        "separation_margin_m": 0.5,
    }
    base.update(over)
    return RolloutConfig(**base)  # type: ignore[arg-type]


def _node(label: str, robot: str, target: str, **over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "label": label,
        "robot_id": robot,
        "item_id": None,
        "target_zone_id": target,
        "action": "MOVE",
        "corridor_zone_ids": [],
        "avoid_zone_ids": [],
        "wait_for": [],
        "speed_cap_mps": None,
    }
    base.update(over)
    return base


def _plan(*nodes: dict[str, object], escalate: bool = False) -> Plan:
    body = {
        "nodes": list(nodes),
        "rationale": "r",
        "escalate": escalate,
        "escalation_reason": "needs_operator" if escalate else None,
    }
    return parse_plan(json.dumps(body), "m-1", CONTEXT)


SAFE_START = {"R1": "sw", "R2": "ne"}
SAFE = (_node("a", "R1", "connector_e"), _node("b", "R2", "station_1"))


def test_aggregate_all_pass_accepts() -> None:
    outcomes = [RolloutOutcome((), f"hash_{i}", 100) for i in range(5)]
    res = aggregate(outcomes, k=5)
    assert isinstance(res, AggregatedResult)
    assert res.accepted
    assert res.counterexamples == ()
    assert len(res.variant_hashes) == 5


def test_aggregate_fewer_than_k_results_rejects() -> None:
    outcomes = [RolloutOutcome((), f"hash_{i}", 100) for i in range(4)]
    res = aggregate(outcomes, k=5)
    assert not res.accepted


def test_aggregate_none_or_exception_rejects() -> None:
    # A None in results
    outcomes_none: list[object] = [RolloutOutcome((), f"hash_{i}", 100) for i in range(4)]
    outcomes_none.append(None)
    assert not aggregate(outcomes_none, k=5).accepted

    # An exception in results
    outcomes_exc: list[object] = [RolloutOutcome((), f"hash_{i}", 100) for i in range(4)]
    outcomes_exc.append(RuntimeError("worker failed"))
    assert not aggregate(outcomes_exc, k=5).accepted


def test_mutant_aggregator_caught_when_k_minus_1_pass() -> None:
    # A mutant aggregator that accepts when at least K-1 variants pass
    def mutant_aggregate(results: Sequence[object], k: int = 5) -> AggregatedResult:
        failures = sum(
            1
            for r in results
            if r is None or isinstance(r, Exception) or bool(getattr(r, "counterexamples", ()))
        )
        if failures <= 1:
            return AggregatedResult(accepted=True, counterexamples=())
        return AggregatedResult(accepted=False, counterexamples=())

    cx = Counterexample(CounterexampleCode.COLLISION, rule=Rule.COLLISION_FREE)
    # 4 clean variants, 1 failing variant
    results = [RolloutOutcome((), f"hash_{i}", 100) for i in range(4)]
    results.append(RolloutOutcome((cx,), "hash_fail", 100))

    # Real aggregator must reject
    real_verdict = aggregate(results, k=5)
    assert not real_verdict.accepted

    # Mutant aggregator accepts, so an assertion checking it fails must be triggered
    with pytest.raises(AssertionError):
        mutant_verdict = mutant_aggregate(results, k=5)
        assert not mutant_verdict.accepted


def test_aggregate_orders_counterexamples_by_time_severity_variant() -> None:
    cx_late_collision = Counterexample(
        CounterexampleCode.COLLISION, time_s=10.0, rule=Rule.COLLISION_FREE
    )
    cx_early_collision = Counterexample(
        CounterexampleCode.COLLISION, time_s=2.0, rule=Rule.COLLISION_FREE
    )
    cx_early_separation = Counterexample(
        CounterexampleCode.SEPARATION_VIOLATION, time_s=2.0, rule=Rule.SEPARATION_MIN
    )

    # Variant 0: late collision at 10.0
    # Variant 1: early separation at 2.0
    # Variant 2: early collision at 2.0
    v0 = RolloutOutcome((cx_late_collision,), "h0", 100)
    v1 = RolloutOutcome((cx_early_separation,), "h1", 100)
    v2 = RolloutOutcome((cx_early_collision,), "h2", 100)

    res = aggregate([v0, v1, v2], k=3)
    assert not res.accepted
    assert len(res.counterexamples) == 3

    # Time order first: 2.0 comes before 10.0
    # At 2.0: COLLISION is higher severity than SEPARATION_VIOLATION
    assert res.counterexamples[0].code == CounterexampleCode.COLLISION
    assert res.counterexamples[0].time_s == 2.0
    assert res.counterexamples[0].variant == 2

    assert res.counterexamples[1].code == CounterexampleCode.SEPARATION_VIOLATION
    assert res.counterexamples[1].time_s == 2.0
    assert res.counterexamples[1].variant == 1

    assert res.counterexamples[2].code == CounterexampleCode.COLLISION
    assert res.counterexamples[2].time_s == 10.0
    assert res.counterexamples[2].variant == 0


def test_determinism_workers_1_equals_workers_2() -> None:
    plan = _plan(*SAFE)
    static = _static(SAFE_START)
    config = _config()
    prior = HumanPrior("p1", "v1", {"station_1": 0.01})

    res1 = validate_with_variants(plan, static, config, prior, k=3, max_attempts=1000, workers=1)
    res2 = validate_with_variants(plan, static, config, prior, k=3, max_attempts=1000, workers=2)

    assert res1.accepted == res2.accepted
    assert res1.counterexamples == res2.counterexamples
    assert res1.variant_hashes == res2.variant_hashes


def test_planted_human_fails_in_one_variant_and_aggregate_rejects() -> None:
    # Robot R1 moves from "sw" (3,2) to "connector_e" (37,2) across corridor_s
    plan = _plan(_node("a", "R1", "connector_e"))
    static = _static({"R1": "sw"})
    config = _config(robot_kinds={"R1": RobotKind.CARRIER})

    # Planted human prior: corridor_s has density that spawns humans along R1's path
    # Area of corridor_s is [0, 0, 40, 5] = 200 m^2. Density 0.02 -> 4 humans.
    prior_with_human = HumanPrior("p_plant", "v1", {"corridor_s": 0.05})
    res_plant = validate_with_variants(
        plan, static, config, prior_with_human, k=3, max_attempts=1000, workers=1
    )

    assert not res_plant.accepted
    assert len(res_plant.counterexamples) > 0
    codes = {c.code for c in res_plant.counterexamples}
    assert (CounterexampleCode.COLLISION in codes) or (
        CounterexampleCode.SEPARATION_VIOLATION in codes
    )


def test_plan_without_planted_fault_is_accepted() -> None:
    plan = _plan(*SAFE)
    static = _static(SAFE_START)
    config = _config()
    # A clean prior where humans are placed in unused aisle_2 (y in [13, 17])
    prior_clean = HumanPrior("p_clean", "v1", {"aisle_2": 0.01})
    res = validate_with_variants(
        plan, static, config, prior_clean, k=3, max_attempts=1000, workers=1
    )
    assert res.accepted
    assert res.counterexamples == ()


def test_variants_imports_no_banned_modules() -> None:
    source_path = (
        Path(__file__).parents[3] / "src" / "waggle" / "validation" / "variants.py"
    ).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    direct_imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    all_imports = imported | set(direct_imports)
    banned = ("waggle.llm", "waggle.governance", "waggle.mcp_server", "random", "secrets")
    for b in banned:
        assert not any(m.startswith(b) for m in all_imports)


def test_aggregate_needs_k_and_a_short_list_is_a_rejection() -> None:
    ok = RolloutOutcome((), "h", 100)
    with pytest.raises(TypeError):
        aggregate([ok])  # type: ignore[call-arg]
    assert not aggregate([ok], k=2).accepted
    assert not aggregate([], k=1).accepted
    assert not aggregate([ok], k=0).accepted


@pytest.mark.parametrize("hazard", [frozenset(), frozenset({"corridor_s"})])
def test_the_variant_rollout_without_humans_equals_the_plan_rollout(
    hazard: frozenset[str],
) -> None:
    """The variant rollout copies the plan rollout: with no humans they must agree exactly.

    The seed cannot differ here (nothing is random without humans), so this guards the
    dynamics, the detector and the hazard scan, not the seed. The second case has a hazard
    zone on the path, so the counterexamples are not empty.
    """
    plan = _plan(*SAFE)
    static = _static(SAFE_START)
    config = _config(hazard_zone_ids=hazard)
    paths = compile_plan(plan, static).paths
    base = run_plan_rollout(paths, static, config)
    variant = run_variant_rollout(paths, static, config, [], config.seed)
    assert variant.final_hash == base.final_hash
    assert variant.counterexamples == base.counterexamples
    assert variant.ticks == base.ticks
    assert bool(base.counterexamples) == bool(hazard)


def test_validate_requires_k_and_the_attempt_cap() -> None:
    plan = _plan(*SAFE)
    prior = HumanPrior("p", "v1", {"aisle_2": 0.01})
    with pytest.raises(TypeError):
        validate_with_variants(plan, _static(SAFE_START), _config(), prior, max_attempts=10)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        validate_with_variants(plan, _static(SAFE_START), _config(), prior, k=2)  # type: ignore[call-arg]
