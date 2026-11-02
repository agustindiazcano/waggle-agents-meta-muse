"""LLM client: routes a role to a provider, enforces caps, logs every call.

Fallbacks come only from the routing table, are labeled in the call log, and can be
switched off (held-out runs). Nothing else moves a call to another provider.
"""

import logging
import math
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from waggle.llm.budget import BudgetGuard
from waggle.llm.call_log import CallLog
from waggle.llm.errors import (
    BudgetExceededError,
    ConfigError,
    ProviderError,
    ProviderTimeoutError,
)
from waggle.llm.models import CallRecord, CallStatus, Completion, LlmRequest
from waggle.llm.providers import Provider
from waggle.llm.routing import RouteSpec, RoutingTable, resolve_model_id
from waggle.llm.task_caps import TaskCaps, TaskLedger

logger = logging.getLogger("waggle.llm")


class LlmClient:
    """Single entry point for model calls."""

    def __init__(
        self,
        *,
        providers: Mapping[str, Provider],
        table: RoutingTable,
        guard: BudgetGuard,
        log: CallLog,
        environ: Mapping[str, str],
        fallbacks_enabled: bool,
        task_caps: TaskCaps | None = None,
        max_retries: int = 0,
        backoff_s: float = 0.0,
        timeout_s: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0 or not math.isfinite(backoff_s) or backoff_s < 0:
            raise ConfigError("max_retries and backoff_s must be finite and >= 0")
        if timeout_s is not None and (not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ConfigError("timeout_s must be finite and > 0")
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._timeout_s = timeout_s
        self._sleep = sleep
        self._providers = providers
        self._table = table
        self._guard = guard
        self._log = log
        self._environ = environ
        self._fallbacks_enabled = fallbacks_enabled
        self._ledger = TaskLedger(task_caps) if task_caps else None
        self._cache: dict[str, Completion] = {}

    @property
    def max_retries(self) -> int:
        """Retries after the first attempt. The HTTP provider retries on its own."""
        return self._max_retries

    def call(self, request: LlmRequest) -> Completion:
        """Run a request. Raises a typed LlmError when it cannot be served."""
        route = self._table.get(request.role)
        cached = self._cache.get(request.request_id)
        if cached is not None:
            self._record(request, route.primary.provider, cached.model_id, "cached", None, None)
            return cached
        try:
            result = self._attempt(request, route.primary, None)
        except (BudgetExceededError, ProviderError) as err:
            fallback = route.fallback
            if not self._fallbacks_enabled or fallback is None:
                raise
            reason = "budget" if isinstance(err, BudgetExceededError) else "error"
            label = f"fallback:{route.primary.provider}->{fallback.provider}:{reason}"
            logger.warning("using %s for request %s", label, request.request_id)
            result = self._attempt(request, fallback, label)
        self._cache[request.request_id] = result
        return result

    def preflight(self, requests: Sequence[LlmRequest]) -> None:
        """Check that all requests fit their provider caps together, making no call.

        Uses the primary route of each role. Cached requests cost nothing. Raises the same typed
        errors as ``call`` (``BudgetExceededError``, ``InvalidCapError``, ``UnknownRoleError``,
        ``ConfigError``), so a caller can refuse a whole set before any partial work starts.
        """
        planned: dict[str, float] = {}
        for request in requests:
            spec = self._table.get(request.role).primary
            provider = self._providers.get(spec.provider)
            if provider is None:
                raise ConfigError(f"no provider registered for {spec.provider}")
            if request.request_id in self._cache:
                continue
            planned[spec.provider] = planned.get(spec.provider, 0.0) + provider.estimate_cost(
                request
            )
        for name, estimate in planned.items():
            remaining = self._guard.remaining(name)
            if estimate > remaining:
                cap = remaining + self._guard.spent(name)
                raise BudgetExceededError(name, self._guard.spent(name), estimate, cap)

    def _attempt(self, request: LlmRequest, spec: RouteSpec, label: str | None) -> Completion:
        provider = self._providers.get(spec.provider)
        if provider is None:
            raise ConfigError(f"no provider registered for {spec.provider}")
        model_id = resolve_model_id(spec, self._environ)
        estimate = provider.estimate_cost(request)
        if self._ledger is not None and request.task_id is not None:
            self._ledger.check(request.task_id, estimate)
        self._guard.check(spec.provider, estimate, request_id=request.request_id, role=request.role)
        completion = self._complete_with_retries(request, spec, provider, model_id, label)
        self._record(request, spec.provider, model_id, "ok", label, completion)
        if self._ledger is not None and request.task_id is not None:
            self._ledger.record(request.task_id, completion.cost_usd)
        return completion

    def _complete_with_retries(
        self,
        request: LlmRequest,
        spec: RouteSpec,
        provider: Provider,
        model_id: str,
        label: str | None,
    ) -> Completion:
        """Retry transport errors only, with exponential backoff and a hard cap."""
        for attempt in range(self._max_retries + 1):
            try:
                return self._complete_once(provider, request, model_id)
            except ProviderError:
                self._record(request, spec.provider, model_id, "error", label, None)
                if attempt == self._max_retries:
                    raise
                self._sleep(self._backoff_s * 2**attempt)
        raise AssertionError("unreachable: the last attempt returns or raises")

    def _complete_once(self, provider: Provider, request: LlmRequest, model_id: str) -> Completion:
        if self._timeout_s is None:
            return provider.complete(request, model_id)
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(provider.complete, request, model_id)
        try:
            return future.result(timeout=self._timeout_s)
        except FutureTimeout:
            raise ProviderTimeoutError(
                f"{provider.name}: timeout after {self._timeout_s}s"
            ) from None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _record(
        self,
        request: LlmRequest,
        provider: str,
        model_id: str,
        status: CallStatus,
        label: str | None,
        completion: Completion | None,
    ) -> None:
        self._log.record(
            CallRecord(
                request_id=request.request_id,
                task_id=request.task_id,
                role=request.role,
                provider=provider,
                model_id=model_id,
                status=status,
                tokens_in=completion.tokens_in if completion else 0,
                tokens_out=completion.tokens_out if completion else 0,
                latency_s=completion.latency_s if completion else 0.0,
                cost_usd=completion.cost_usd if completion else 0.0,
                fallback_label=label,
            )
        )
