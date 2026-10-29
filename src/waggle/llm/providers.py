"""Provider interface and the mock provider used by tests and CI (no network, no spend)."""

from typing import Protocol

from waggle.llm.errors import ProviderError
from waggle.llm.models import Completion, LlmRequest


class Provider(Protocol):
    """One model provider behind the common interface."""

    name: str

    def estimate_cost(self, request: LlmRequest) -> float:
        """Estimated cost in USD of the call, used by the budget guard before the call."""

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        """Run the call. Raises ProviderError on failure."""


class MockProvider:
    """Deterministic provider with a fixed cost and an optional outage switch."""

    def __init__(self, name: str, cost_usd: float = 0.01, fail: bool = False) -> None:
        self.name = name
        self.cost_usd = cost_usd
        self.fail = fail
        self.calls = 0

    def estimate_cost(self, request: LlmRequest) -> float:
        """Return the fixed cost."""
        return self.cost_usd

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        """Return a canned completion, or raise ProviderError when failing."""
        if self.fail:
            raise ProviderError(f"{self.name}: simulated outage")
        self.calls += 1
        return Completion(
            text="ok",
            model_id=model_id,
            tokens_in=len(request.prompt.split()) + 1,
            tokens_out=1,
            latency_s=0.0,
            cost_usd=self.cost_usd,
        )
