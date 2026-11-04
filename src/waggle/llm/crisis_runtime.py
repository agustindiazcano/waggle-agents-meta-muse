"""Compose the production planner route with the deterministic crisis validator.

The caller supplies trusted map, fleet, belief and rollout policy. This service returns
an accepted plan or an escalation; it has no motion authority. A caller still sends
accepted work through the authenticated tool boundary. The supplied call log can be
PostgresCallLog; no database transaction is held around model calls here.
"""

from collections.abc import Mapping

from waggle.llm.call_log import CallLog
from waggle.llm.client import LlmClient
from waggle.llm.client_factory import build_client
from waggle.llm.crisis_adapter import LlmPlanProposer
from waggle.llm.providers import Provider
from waggle.validation.belief_builder import Belief
from waggle.validation.crisis_loop import CrisisResult, run_crisis_loop
from waggle.validation.path_compiler import StaticMap
from waggle.validation.plan import PlanContext
from waggle.validation.plan_rollout import RolloutConfig


class CrisisRuntime:
    """One routed planner client, with validation required on every proposal."""

    def __init__(self, client: LlmClient) -> None:
        self._client = client

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        log: CallLog,
        *,
        fallbacks_enabled: bool,
        providers: Mapping[str, Provider] | None = None,
    ) -> "CrisisRuntime":
        """Build without a call; provider overrides are restricted to mock mode."""
        return cls(
            build_client(environ, log, fallbacks_enabled=fallbacks_enabled, providers=providers)
        )

    def replan(
        self,
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
        task_id: str | None = None,
    ) -> CrisisResult:
        """Propose and validate under caller policy, with no motion side effects.

        Use a distinct mission id for each recovery incident. Request caching is
        scoped by that id, context, prompt and feedback, so an incident must never
        reuse an old mission id for a different physical situation.
        """
        proposer = LlmPlanProposer(
            self._client, mission_id=mission_id, context=context, task_id=task_id
        )
        return run_crisis_loop(
            proposer,
            mission_id=mission_id,
            context=context,
            static=static,
            config=config,
            belief=belief,
            k=k,
            max_attempts=max_attempts,
            variant_timeout_s=variant_timeout_s,
            max_rounds=max_rounds,
        )
