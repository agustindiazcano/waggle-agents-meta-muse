"""LLM client: routes a role to a provider, enforces caps, logs every call.

Fallbacks come only from the routing table, are labeled in the call log, and can be
switched off (held-out runs). Nothing else moves a call to another provider.
"""

import logging
from collections.abc import Mapping

from waggle.llm.budget import BudgetGuard
from waggle.llm.call_log import CallLog
from waggle.llm.errors import BudgetExceededError, ConfigError, ProviderError
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
    ) -> None:
        self._providers = providers
        self._table = table
        self._guard = guard
        self._log = log
        self._environ = environ
        self._fallbacks_enabled = fallbacks_enabled
        self._ledger = TaskLedger(task_caps) if task_caps else None
        self._cache: dict[str, Completion] = {}

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

    def _attempt(self, request: LlmRequest, spec: RouteSpec, label: str | None) -> Completion:
        provider = self._providers.get(spec.provider)
        if provider is None:
            raise ConfigError(f"no provider registered for {spec.provider}")
        model_id = resolve_model_id(spec, self._environ)
        estimate = provider.estimate_cost(request)
        if self._ledger is not None and request.task_id is not None:
            self._ledger.check(request.task_id, estimate)
        self._guard.check(spec.provider, estimate, request_id=request.request_id, role=request.role)
        try:
            completion = provider.complete(request, model_id)
        except ProviderError:
            self._record(request, spec.provider, model_id, "error", label, None)
            raise
        self._record(request, spec.provider, model_id, "ok", label, completion)
        if self._ledger is not None and request.task_id is not None:
            self._ledger.record(request.task_id, completion.cost_usd)
        return completion

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
