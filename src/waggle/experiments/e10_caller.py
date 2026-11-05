"""Production crisis caller for one E10 template (mock wiring only in experiments).

This is the minimal caller the existing interfaces expose: it builds the trusted
inputs of a template and calls ``CrisisRuntime.replan``, which already composes
``LlmPlanProposer`` with the deterministic crisis loop. It adds no motion authority:
an accepted plan still goes through the authenticated tool boundary elsewhere.
"""

from waggle.experiments.e10_cases import (
    CONTEXT,
    CrisisTemplate,
    template_belief,
    template_config,
    template_static,
)
from waggle.llm.crisis_runtime import CrisisRuntime
from waggle.validation.crisis_loop import CrisisResult

K_VARIANTS: int = 2
MAX_ATTEMPTS: int = 1000
VARIANT_TIMEOUT_S: float = 60.0


class CrisisCaller:
    """Calls the production crisis runtime for one template at a time."""

    def __init__(self, runtime: CrisisRuntime) -> None:
        self._runtime = runtime

    def replan(self, template: CrisisTemplate, *, max_rounds: int) -> CrisisResult:
        """Replan one template incident under the caller policy above."""
        return self._runtime.replan(
            mission_id=template.mission_id,
            context=CONTEXT,
            static=template_static(template),
            config=template_config(template),
            belief=template_belief(template),
            k=K_VARIANTS,
            max_attempts=MAX_ATTEMPTS,
            variant_timeout_s=VARIANT_TIMEOUT_S,
            max_rounds=max_rounds,
            task_id=f"crisis-{template.id}",
        )
