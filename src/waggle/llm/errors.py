"""Typed errors for the LLM layer. Every one of them fails closed."""


class LlmError(Exception):
    """Base class for all LLM layer errors."""


class InvalidCapError(LlmError):
    """A provider spend cap is missing or invalid."""


class BudgetExceededError(LlmError):
    """A call would pass the provider spend cap."""

    def __init__(self, provider: str, spent: float, estimate: float, cap: float) -> None:
        super().__init__(
            f"{provider}: spent {spent:.4f} + estimate {estimate:.4f} would pass cap {cap:.4f}"
        )
        self.provider = provider
        self.spent = spent
        self.estimate = estimate
        self.cap = cap


class TaskCapExceededError(LlmError):
    """A task reached its call or cost cap."""


class UnknownRoleError(LlmError):
    """The role is not in the routing table."""


class ConfigError(LlmError):
    """A route needs a configuration value that is missing."""


class ProviderError(LlmError):
    """The provider call failed (outage, timeout, rejected request)."""
