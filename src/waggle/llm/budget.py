"""Budget guard: reject any call that would pass the provider cap (AGENTS.md section 14)."""

import logging
import math
from collections.abc import Mapping

from waggle.llm.call_log import CallLog
from waggle.llm.errors import BudgetExceededError, InvalidCapError
from waggle.llm.models import CallRecord

PROVIDERS = ("meta", "baseten", "modal", "vertex")

logger = logging.getLogger("waggle.llm")


def cap_env_name(provider: str) -> str:
    """Name of the environment variable that holds the cap for a provider."""
    return f"{provider.upper()}_SPEND_CAP_USD"


def parse_cap(provider: str, environ: Mapping[str, str]) -> float:
    """Read a cap in USD. A missing or invalid value raises InvalidCapError."""
    if provider not in PROVIDERS:
        raise InvalidCapError(f"unknown provider {provider!r}")
    name = cap_env_name(provider)
    raw = environ.get(name)
    if raw is None or not raw.strip():
        raise InvalidCapError(f"{name} is missing")
    try:
        cap = float(raw)
    except ValueError:
        raise InvalidCapError(f"{name} is not a number") from None
    if not math.isfinite(cap) or cap < 0:
        raise InvalidCapError(f"{name} must be a finite number >= 0")
    return cap


class BudgetGuard:
    """Checks accumulated cost plus the call estimate against the provider cap."""

    def __init__(self, environ: Mapping[str, str], log: CallLog) -> None:
        self._environ = environ
        self._log = log

    def spent(self, provider: str) -> float:
        """Accumulated cost of successful calls to a provider."""
        return sum(
            r.cost_usd for r in self._log.records() if r.provider == provider and r.status == "ok"
        )

    def remaining(self, provider: str) -> float:
        """Cap minus accumulated cost."""
        return parse_cap(provider, self._environ) - self.spent(provider)

    def check(self, provider: str, estimate: float, *, request_id: str, role: str) -> None:
        """Allow the call or raise. A denial is logged and makes no provider call."""
        cap = parse_cap(provider, self._environ)
        spent = self.spent(provider)
        if spent + estimate > cap:
            logger.warning(
                "denied: %s call %s for role %s would pass the cap", provider, request_id, role
            )
            self._log.record(
                CallRecord(
                    request_id=request_id,
                    task_id=None,
                    role=role,
                    provider=provider,
                    model_id="",
                    status="denied",
                    tokens_in=0,
                    tokens_out=0,
                    latency_s=0.0,
                    cost_usd=0.0,
                )
            )
            raise BudgetExceededError(provider, spent, estimate, cap)
