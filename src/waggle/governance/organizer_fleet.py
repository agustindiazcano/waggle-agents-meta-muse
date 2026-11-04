"""Validate fleet MOVE proposals with the existing plan contract and staged validator.

This bounded harness adapter rejects dependencies and non-MOVE actions rather than
discarding their semantics. It grants no MCP identity or motion authority.
"""

from dataclasses import dataclass

from waggle.validation.path_compiler import CompiledPath, StaticMap, compile_plan
from waggle.validation.plan import Plan, PlanContext, PlanRejected, parse_plan
from waggle.validation.plan_rollout import RolloutConfig, validate_plan


@dataclass(frozen=True)
class FleetPlanResult:
    """A fully validated executable proposal, or a refusal without paths."""

    plan: Plan | None
    paths: tuple[CompiledPath, ...] = ()
    reason: str | None = None


def validate_fleet_plan(
    raw: str,
    *,
    mission_id: str,
    context: PlanContext,
    static: StaticMap,
    config: RolloutConfig,
    max_response_chars: int,
) -> FleetPlanResult:
    """Require strict schema, executable MOVE semantics and a passing staged rollout.

    Inherits Stage C's documented assumptions, including zero initial speed and no
    humans. Passing is not a guarantee about the later E5 trajectory; the fast layer
    still controls every command. Trusted map/configuration errors propagate.
    """
    if len(raw) > max_response_chars:
        return FleetPlanResult(None, reason="too_long")
    try:
        plan = parse_plan(raw, mission_id, context)
    except (PlanRejected, RecursionError) as exc:
        reason = exc.code if isinstance(exc, PlanRejected) else "not_an_object"
        return FleetPlanResult(None, reason=reason)
    if any(n.action != "MOVE" or n.wait_for for n in plan.nodes):
        return FleetPlanResult(None, reason="unsupported_execution")
    verdict = validate_plan(plan, static, config)
    if not verdict.accepted:
        return FleetPlanResult(None, reason=verdict.stage)
    compiled = compile_plan(plan, static)
    if compiled.counterexamples:
        return FleetPlanResult(None, reason="static")
    # This harness has no corridor lease executor. A route needing one cannot run here.
    if any(path.corridor_ids for path in compiled.paths):
        return FleetPlanResult(None, reason="unsupported_execution")
    return FleetPlanResult(plan, compiled.paths)
