"""Crisis planner loop: propose, validate, feed counterexamples back, at most three rounds.

Each round the proposer returns raw text. The text is data: ``parse_plan`` checks it against the
strict plan schema, and only a parsed plan reaches ``validate_with_variants``. The feedback to
the next round is built by code from typed counterexamples (``build_feedback``) and never
contains plan text or the text of an exception. After the last rejected round the result is an
escalation to the operator and carries no plan. A plan is returned only when every variant passed.

``PlanProposer`` is a Protocol. The adapter that talks to a model lives in ``waggle.llm`` (this
package must not import it) and is not written yet: tests use a scripted proposer.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol

from waggle.validation.belief_builder import Belief
from waggle.validation.counterexample import Counterexample
from waggle.validation.feedback import TrustedIds, build_feedback
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan import Plan, PlanContext, PlanRejected, parse_plan
from waggle.validation.plan_rollout import RolloutConfig
from waggle.validation.variants import validate_with_variants

logger = logging.getLogger("waggle.validation.crisis_loop")

MAX_ROUNDS: Final = 3
Outcome = Literal["accepted", "rejected", "unparseable", "proposer_error", "escalated_by_plan"]


class PlanProposer(Protocol):
    """Anything that can propose a plan as raw text, given the feedback of the last round."""

    def propose(self, feedback: str | None) -> str:
        """Return raw plan text; ``feedback`` is None in the first round and JSON after."""
        ...


@dataclass(frozen=True)
class RoundRecord:
    """What happened in one round."""

    round: int
    outcome: Outcome
    stage: str
    counterexamples: int


@dataclass(frozen=True)
class CrisisResult:
    """An accepted plan, or an escalation to the operator with no plan."""

    status: Literal["accepted", "escalated"]
    plan: Plan | None
    rounds: int
    reason: str | None
    history: tuple[RoundRecord, ...]


def _rejection_feedback(code: str) -> str:
    return json.dumps({"kind": "plan_rejected", "code": code}, separators=(",", ":"))


def _trusted(static: StaticMap, config: RolloutConfig, plan: Plan) -> TrustedIds:
    zones = frozenset(z.id for z in static.world.zones)
    return TrustedIds(frozenset(config.robot_kinds), zones, tuple(n.label for n in plan.nodes))


def _feedback(
    counterexamples: Sequence[Counterexample], static: StaticMap, config: RolloutConfig, plan: Plan
) -> str:
    return build_feedback(counterexamples, _trusted(static, config, plan))


def run_crisis_loop(
    proposer: PlanProposer,
    *,
    mission_id: str,
    context: PlanContext,
    static: StaticMap,
    config: RolloutConfig,
    belief: Belief,
    k: int,
    max_attempts: int,
    variant_timeout_s: float,
    max_rounds: int,
) -> CrisisResult:
    """Run up to ``max_rounds`` (1 to 3) rounds; return an accepted plan or an escalation."""
    if isinstance(max_rounds, bool) or not 1 <= max_rounds <= MAX_ROUNDS:
        raise ValueError(f"max_rounds must be between 1 and {MAX_ROUNDS}")
    history: list[RoundRecord] = []
    feedback: str | None = None
    for number in range(1, max_rounds + 1):
        try:
            raw = proposer.propose(feedback)
        except Exception as exc:
            logger.warning("round %d: proposer failed: %s", number, type(exc).__name__)
            history.append(RoundRecord(number, "proposer_error", "propose", 0))
            feedback = _rejection_feedback("proposer_error")
            continue
        try:
            plan = parse_plan(raw, mission_id, context)
        except PlanRejected as err:
            logger.info("round %d: plan refused: %s", number, err.code)
            history.append(RoundRecord(number, "unparseable", "schema", 0))
            feedback = _rejection_feedback(err.code)
            continue
        verdict = validate_with_variants(
            plan,
            static,
            config,
            belief,
            k=k,
            max_attempts=max_attempts,
            variant_timeout_s=variant_timeout_s,
        )
        count = len(verdict.counterexamples)
        if verdict.escalated:
            history.append(RoundRecord(number, "escalated_by_plan", verdict.stage, 0))
            return CrisisResult("escalated", None, number, "plan_requested", tuple(history))
        if verdict.accepted:
            history.append(RoundRecord(number, "accepted", verdict.stage, 0))
            return CrisisResult("accepted", plan, number, None, tuple(history))
        history.append(RoundRecord(number, "rejected", verdict.stage, count))
        feedback = _feedback(verdict.counterexamples, static, config, plan)
    return CrisisResult("escalated", None, max_rounds, "rounds_exhausted", tuple(history))
