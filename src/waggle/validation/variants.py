"""Stage D of the plan validator: K human variants and all-pass aggregation (ADR-023, 025).

The validator compiles the plan, checks geofences, and then runs K seeded rollouts with
hidden humans sampled from the belief state. The plan passes only if every one of the K
variants executes without a counterexample. A variant that raises or times out fails closed.
The rollout itself is ``run_plan_rollout``: there is no second copy of it here.
"""

import dataclasses
import logging
import math
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field

from waggle.sim import params
from waggle.validation.belief import HumanState, sample_humans, variant_seeds
from waggle.validation.belief_builder import Belief
from waggle.validation.counterexample import Counterexample, CounterexampleCode
from waggle.validation.geofence import check_geofence
from waggle.validation.path_compiler import CompiledPath, StaticMap, compile_plan
from waggle.validation.plan import Plan
from waggle.validation.plan_rollout import RolloutConfig, RolloutOutcome, run_plan_rollout

logger = logging.getLogger("waggle.validation.variants")

_SEVERITY = {code: index for index, code in enumerate(CounterexampleCode)}


@dataclass(frozen=True)
class AggregatedResult:
    """The aggregated verdict across K variant rollouts (ADR-023)."""

    accepted: bool
    counterexamples: tuple[Counterexample, ...] = ()
    escalated: bool = False
    stage: str = "variants"
    variant_hashes: tuple[str | None, ...] = ()
    notes: tuple[str, ...] = field(default=())


def run_variant_rollout(
    paths: Sequence[CompiledPath],
    static: StaticMap,
    config: RolloutConfig,
    human_states: Sequence[HumanState],
    seed: int,
) -> RolloutOutcome:
    """Run the one plan rollout with these humans and the variant ``seed``."""
    return run_plan_rollout(paths, static, dataclasses.replace(config, seed=seed), human_states)


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


def _collect(
    futures: Sequence[Future[RolloutOutcome]], timeout_s: float
) -> tuple[list[object], list[str]]:
    """Wait for each variant for at most ``timeout_s``; a late or failed one is a rejection.

    After the first timeout the rest are read without waiting, because one rejection already
    rejects the plan.
    """
    results: list[object] = []
    notes: list[str] = []
    timed_out = False
    for i, future in enumerate(futures):
        try:
            results.append(future.result(timeout=0.0 if timed_out else timeout_s))
        except FutureTimeout:
            timed_out = True
            logger.warning("variant %d timed out after %.3f s", i, timeout_s)
            results.append(TimeoutError(f"variant {i}"))
            notes.append(f"variant {i}: timeout")
        except Exception as exc:
            logger.warning("variant %d failed: %s", i, type(exc).__name__)
            results.append(exc)
            notes.append(f"variant {i}: {type(exc).__name__}")
    return results, notes


def validate_with_variants(
    plan: Plan,
    static: StaticMap,
    config: RolloutConfig,
    belief: Belief,
    *,
    k: int,
    max_attempts: int,
    variant_timeout_s: float,
    workers: int = 1,
) -> AggregatedResult:
    """Run K human variants and aggregate. Fails closed on any error or timeout (ADR-023).

    ``k`` (5 in ADR-023), the sampler attempt cap and the per-variant timeout are chosen by the
    caller. Every variant holds the tracked humans of the belief plus the humans sampled from its
    prior; a sampled human starts no closer to a robot than that robot's stopping distance from
    top speed. A variant that does not return within ``variant_timeout_s`` is a rejection and the
    call does not wait for it: the pool is left without waiting (the abandoned thread ends on its
    own and its result is dropped).
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if (
        isinstance(variant_timeout_s, bool)
        or not isinstance(variant_timeout_s, int | float)
        or not math.isfinite(variant_timeout_s)
        or variant_timeout_s <= 0
    ):
        raise ValueError("variant_timeout_s must be a positive finite number")

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

    seeds = variant_seeds(config.seed, belief.snapshot_digest, k)
    stop_m = _stopping_distance_m(config)

    def run_one_variant(index: int) -> RolloutOutcome:
        v_seed = seeds[index]
        sampled = sample_humans(
            belief.prior,
            static,
            static.robot_start,
            v_seed,
            min_stop_distance_m=stop_m,
            max_attempts=max_attempts,
        )
        everyone = (*belief.known_humans, *sampled.humans)
        return run_variant_rollout(compiled.paths, static, config, everyone, v_seed)

    # No ``with`` block: leaving it would wait for a stuck worker and the timeout would not
    # bound the wait (ADR-080).
    pool = ThreadPoolExecutor(max_workers=min(workers, k))
    try:
        futures = [pool.submit(run_one_variant, i) for i in range(k)]
        results, notes = _collect(futures, variant_timeout_s)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return dataclasses.replace(aggregate(results, k=k), notes=tuple(notes))
