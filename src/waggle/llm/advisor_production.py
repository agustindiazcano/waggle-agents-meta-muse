"""Production assembly for per-robot advisors with a database call log.

Mirrors ``build_production_maintenance``: the caller supplies policy and
limits, this module owns the remaining production wiring. The call log is
``PostgresCallLog`` over the caller's database, its mode read from the
environment with ``select_mode`` so a missing or unknown mode fails closed
before any call. The shared client is built by ``build_client`` (provider
overrides stay mock-only there), the guard classifier is the production
``LlmGuardClassifier`` over that same client, and the caution log is a fresh
``CautionLog`` under the caller's config. Building makes no model call and
holds no database transaction around one: each call-log row is its own
transaction inside ``PostgresCallLog``.
"""

from collections.abc import Mapping

from waggle.db.connection import Database
from waggle.db.llm_calls import PostgresCallLog
from waggle.governance.advisor_input import AdvisorInputLimits, InboundMessage, TrustedFacts
from waggle.governance.caution import CautionConfig
from waggle.governance.caution_log import CautionLog
from waggle.llm.advisor_runtime import AdvisorResult, AdvisorRuntime
from waggle.llm.client_factory import build_client
from waggle.llm.guard_adapter import LlmGuardClassifier
from waggle.llm.provider_config import select_mode
from waggle.llm.providers import Provider


class ProductionAdvisors:
    """One advisor runtime wired to the production client and Postgres call log."""

    def __init__(
        self, runtime: AdvisorRuntime, call_log: PostgresCallLog, caution_log: CautionLog
    ) -> None:
        self._runtime = runtime
        self.call_log = call_log
        self.caution_log = caution_log

    @property
    def runtime(self) -> AdvisorRuntime:
        """The wired advisor runtime."""
        return self._runtime

    def advise(
        self,
        facts: TrustedFacts,
        *,
        tick: int,
        current_cap: float,
        class_max: float,
        run_id: str,
        task_id: str,
        messages: list[InboundMessage] | None = None,
        latency_ticks: int = 0,
    ) -> AdvisorResult:
        """Run one advisor step; advisors can only add caution."""
        return self._runtime.advise(
            facts,
            tick=tick,
            current_cap=current_cap,
            class_max=class_max,
            run_id=run_id,
            task_id=task_id,
            messages=messages,
            latency_ticks=latency_ticks,
        )


def build_production_advisors(
    database: Database,
    environ: Mapping[str, str],
    *,
    caution_config: CautionConfig,
    input_limits: AdvisorInputLimits,
    timeout_s: float,
    max_response_chars: int,
    rate_limit_ticks: int,
    fallbacks_enabled: bool,
    providers: Mapping[str, Provider] | None = None,
) -> ProductionAdvisors:
    """Assemble the production advisor service over a database. Makes no call."""
    call_log = PostgresCallLog(database, select_mode(environ))
    client = build_client(
        environ, call_log, fallbacks_enabled=fallbacks_enabled, providers=providers
    )
    caution_log = CautionLog(caution_config)
    runtime = AdvisorRuntime(
        client=client,
        caution_log=caution_log,
        config=caution_config,
        timeout_s=timeout_s,
        max_response_chars=max_response_chars,
        rate_limit_ticks=rate_limit_ticks,
        classifier=LlmGuardClassifier(client),
        input_limits=input_limits,
    )
    return ProductionAdvisors(runtime, call_log, caution_log)
