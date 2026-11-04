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
import logging
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest
from validation_rig import (
    SAFE,
    SAFE_START,
    _config,
    _node,
    _plan,
    _static,
)

from waggle.sim.params import RobotKind
from waggle.validation.belief import HumanPrior, HumanState
from waggle.validation.belief_builder import (
    Belief,
    TrackedEntity,
    TrackSnapshot,
    build_belief,
)
from waggle.validation.counterexample import Counterexample, CounterexampleCode, Rule
from waggle.validation.path_compiler import compile_plan
from waggle.validation.plan_rollout import RolloutOutcome, run_plan_rollout
from waggle.validation.variants import (
    AggregatedResult,
    aggregate,
    run_variant_rollout,
    validate_with_variants,
)


def _entity(eid: int, x: float, y: float) -> TrackedEntity:
    return TrackedEntity(eid, x, y, 0.0, 0.0, 0.1, 5)


def _b(prior: HumanPrior) -> Belief:
    return build_belief(TrackSnapshot(tick=0, entities=()), prior)


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

    res1 = validate_with_variants(
        plan, static, config, _b(prior), k=3, max_attempts=1000, workers=1, variant_timeout_s=60.0
    )
    res2 = validate_with_variants(
        plan, static, config, _b(prior), k=3, max_attempts=1000, workers=2, variant_timeout_s=60.0
    )

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
        plan,
        static,
        config,
        _b(prior_with_human),
        k=3,
        max_attempts=1000,
        workers=1,
        variant_timeout_s=60.0,
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
    # Density 0 places no human. With density above 0 a sampled human walks straight for 45 s
    # and may cross the robots, so acceptance would depend on the digest seeds, not on the plan.
    prior_clean = HumanPrior("p_clean", "v1", {"aisle_2": 0.0})
    res = validate_with_variants(
        plan,
        static,
        config,
        _b(prior_clean),
        k=3,
        max_attempts=1000,
        workers=1,
        variant_timeout_s=60.0,
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
        validate_with_variants(
            plan, _static(SAFE_START), _config(), _b(prior), max_attempts=10, variant_timeout_s=60.0
        )  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        validate_with_variants(
            plan, _static(SAFE_START), _config(), _b(prior), k=2, variant_timeout_s=60.0
        )  # type: ignore[call-arg]


def test_the_plan_rollout_takes_walkers_and_the_variant_rollout_is_the_same_function() -> None:
    plan = _plan(_node("a", "R1", "connector_e"))
    static = _static({"R1": "sw"})
    config = _config(robot_kinds={"R1": RobotKind.CARRIER})
    paths = compile_plan(plan, static).paths
    blocker = [HumanState((20.0, 2.0), (0.0, 0.0))]
    clear = run_plan_rollout(paths, static, config)
    assert run_plan_rollout(paths, static, config, walkers=()) == clear
    hit = run_plan_rollout(paths, static, config, walkers=blocker)
    codes = {c.code for c in hit.counterexamples}
    assert codes & {CounterexampleCode.COLLISION, CounterexampleCode.SEPARATION_VIOLATION}
    assert hit.final_hash != clear.final_hash
    assert run_variant_rollout(paths, static, config, blocker, config.seed) == hit


def test_the_variant_seed_reaches_the_engine_through_the_one_rollout() -> None:
    plan = _plan(_node("a", "R1", "connector_e"))
    static = _static({"R1": "sw"})
    config = _config(robot_kinds={"R1": RobotKind.CARRIER})
    paths = compile_plan(plan, static).paths
    walker = [HumanState((20.0, 8.0), (0.0, 1.4))]
    seeded = run_variant_rollout(paths, static, config, walker, 7)
    assert seeded == run_plan_rollout(
        paths, static, _config(robot_kinds=config.robot_kinds, seed=7), walkers=walker
    )


def test_variants_module_has_no_second_rollout_loop() -> None:
    source = Path(__file__).parents[3] / "src" / "waggle" / "validation" / "variants.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not names & {"engine", "detector", "scripted", "robots", "humans"}


def _blocked_rollout(release: threading.Event) -> object:
    def blocked(*_args: object, **_kwargs: object) -> RolloutOutcome:
        release.wait(timeout=8.0)
        return RolloutOutcome((), "late", 1)

    return blocked


@pytest.mark.parametrize("workers", [1, 2])
def test_a_variant_that_never_returns_is_a_rejection_and_does_not_block(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, workers: int
) -> None:
    release = threading.Event()
    monkeypatch.setattr("waggle.validation.variants.run_variant_rollout", _blocked_rollout(release))
    prior = HumanPrior("p", "v1", {"aisle_2": 0.01})
    caplog.set_level(logging.WARNING, logger="waggle.validation.variants")
    started = time.monotonic()
    try:
        res = validate_with_variants(
            _plan(*SAFE),
            _static(SAFE_START),
            _config(),
            _b(prior),
            k=2,
            max_attempts=1000,
            workers=workers,
            variant_timeout_s=0.3,
        )
        elapsed = time.monotonic() - started
    finally:
        release.set()
    assert elapsed < 3.0
    assert not res.accepted
    assert any("timed out" in r.getMessage() for r in caplog.records)
    assert any("timeout" in n for n in res.notes)


def test_the_variant_timeout_is_required_and_must_be_positive() -> None:
    prior = HumanPrior("p", "v1", {"aisle_2": 0.01})
    with pytest.raises(TypeError):
        validate_with_variants(
            _plan(*SAFE), _static(SAFE_START), _config(), _b(prior), k=1, max_attempts=10
        )  # type: ignore[call-arg]
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            validate_with_variants(
                _plan(*SAFE),
                _static(SAFE_START),
                _config(),
                _b(prior),
                k=1,
                max_attempts=10,
                variant_timeout_s=bad,
            )


def test_known_tracked_humans_are_part_of_every_variant() -> None:
    snapshot = TrackSnapshot(tick=5, entities=(_entity(1, 20.0, 2.0),))
    belief = build_belief(snapshot, HumanPrior("p", "v1", {"aisle_2": 0.01}))
    res = validate_with_variants(
        _plan(_node("a", "R1", "connector_e")),
        _static({"R1": "sw"}),
        _config(robot_kinds={"R1": RobotKind.CARRIER}),
        belief,
        k=2,
        max_attempts=1000,
        variant_timeout_s=60.0,
    )
    assert not res.accepted
