"""Provider interface and the mock provider used by tests and CI (no network, no spend)."""

import threading
from collections.abc import Mapping
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

    def __init__(
        self, name: str, cost_usd: float = 0.01, fail: bool = False, media_cost_usd: float = 0.0
    ) -> None:
        self.name = name
        self.cost_usd = cost_usd
        self.media_cost_usd = media_cost_usd
        self.fail = fail
        self.calls = 0
        self.attachments_seen = 0

    def estimate_cost(self, request: LlmRequest) -> float:
        """Return the fixed cost plus the media cost of each attachment."""
        return self.cost_usd + self.media_cost_usd * len(request.attachments)

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        """Return a canned completion, or raise ProviderError when failing."""
        if self.fail:
            raise ProviderError(f"{self.name}: simulated outage")
        self.calls += 1
        self.attachments_seen += len(request.attachments)
        return Completion(
            text="ok",
            model_id=model_id,
            tokens_in=len(request.prompt.split()) + 1,
            tokens_out=1,
            latency_s=0.0,
            cost_usd=self.estimate_cost(request),
        )


Step = str | ProviderError
Entry = Step | tuple[Step, ...]


class ScriptMissingError(RuntimeError):
    """A scripted call has no configured answer. A real error, never an empty result."""


class ScriptedProvider:
    """Test and CI provider that returns configured text per request id or per role.

    An entry is a text, a ``ProviderError`` to raise, or a tuple of those consumed one per call.
    A request id entry wins over a role entry. A call with no entry, or an exhausted tuple,
    raises ``ScriptMissingError``. No network and no spend. Safe to call from several threads.
    """

    def __init__(
        self,
        name: str,
        *,
        by_role: Mapping[str, Entry],
        by_request: Mapping[str, Entry] | None = None,
        cost_usd: float = 0.01,
        media_cost_usd: float = 0.0,
    ) -> None:
        self.name = name
        self.cost_usd = cost_usd
        self.media_cost_usd = media_cost_usd
        self.calls = 0
        self.attachments_seen = 0
        self.calls_by_role: dict[str, int] = {}
        self.request_ids: list[str] = []
        self._by_role = dict(by_role)
        self._by_request = dict(by_request or {})
        self._used: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def estimate_cost(self, request: LlmRequest) -> float:
        """Return the fixed cost plus the media cost of each attachment."""
        return self.cost_usd + self.media_cost_usd * len(request.attachments)

    def _next(self, request: LlmRequest) -> Step:
        if request.request_id in self._by_request:
            key, entry = ("request", request.request_id), self._by_request[request.request_id]
        elif request.role in self._by_role:
            key, entry = ("role", request.role), self._by_role[request.role]
        else:
            raise ScriptMissingError(f"{self.name}: no script for {request.role}")
        if not isinstance(entry, tuple):
            return entry
        used = self._used.get(key, 0)
        if used >= len(entry):
            raise ScriptMissingError(f"{self.name}: no script left for {key[1]}")
        self._used[key] = used + 1
        return entry[used]

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        """Return the scripted text, or raise the scripted ProviderError."""
        with self._lock:
            step = self._next(request)
            self.calls += 1
            self.attachments_seen += len(request.attachments)
            self.calls_by_role[request.role] = self.calls_by_role.get(request.role, 0) + 1
            self.request_ids.append(request.request_id)
        if isinstance(step, ProviderError):
            raise step
        return Completion(
            text=step,
            model_id=model_id,
            tokens_in=len(request.prompt.split()) + 1,
            tokens_out=len(step.split()) + 1,
            latency_s=0.0,
            cost_usd=self.estimate_cost(request),
        )
