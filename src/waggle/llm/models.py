"""Plain data types shared by the LLM layer."""

from dataclasses import dataclass
from typing import Literal

CallStatus = Literal["ok", "denied", "error", "cached"]


@dataclass(frozen=True)
class LlmRequest:
    """One request to a role. ``request_id`` is checked before any model call."""

    request_id: str
    role: str
    prompt: str
    task_id: str | None = None


@dataclass(frozen=True)
class Completion:
    """Result of a provider call."""

    text: str
    model_id: str
    tokens_in: int
    tokens_out: int
    latency_s: float
    cost_usd: float


@dataclass(frozen=True)
class CallRecord:
    """One row of the call log (the future llm_calls table)."""

    request_id: str
    task_id: str | None
    role: str
    provider: str
    model_id: str
    status: CallStatus
    tokens_in: int
    tokens_out: int
    latency_s: float
    cost_usd: float
    fallback_label: str | None = None
