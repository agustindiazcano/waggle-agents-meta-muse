"""Build the one production ``LlmClient`` from the environment (ADR-077).

Providers come from ``build_providers`` (mock or http, chosen by WAGGLE_LLM_PROVIDER, failing
closed on any missing key, URL or price), routes from ``routes.toml``, caps from the
``*_SPEND_CAP_USD`` variables read by the budget guard at each call. The client's own retry is
left at zero: the HTTP provider already retries 429 and 5xx, and enabling both would multiply
the attempts. This builds objects and makes no call.
"""

from collections.abc import Mapping
from pathlib import Path

from waggle.llm.budget import BudgetGuard
from waggle.llm.call_log import CallLog
from waggle.llm.client import LlmClient
from waggle.llm.errors import ConfigError
from waggle.llm.provider_config import select_mode
from waggle.llm.provider_factory import build_providers
from waggle.llm.providers import Provider
from waggle.llm.routing import load_routes
from waggle.llm.task_caps import TaskCaps


def build_client(
    environ: Mapping[str, str],
    log: CallLog,
    *,
    fallbacks_enabled: bool,
    prices_path: Path | None = None,
    routes_path: Path | None = None,
    task_caps: TaskCaps | None = None,
    timeout_s: float | None = None,
    providers: Mapping[str, Provider] | None = None,
) -> LlmClient:
    """Return a client over the providers of the selected mode and the given call log.

    ``fallbacks_enabled`` has no default: held-out runs pass False (AGENTS.md 6.9). ``providers``
    replaces the built map for tests and scripted runs, and only in mock mode: an override with
    real routes selected raises ConfigError.
    """
    if providers is not None and select_mode(environ) != "mock":
        raise ConfigError("a provider override is allowed only in mock mode")
    built = build_providers(environ, prices_path) if providers is None else dict(providers)
    return LlmClient(
        providers=built,
        table=load_routes(routes_path),
        guard=BudgetGuard(environ, log),
        log=log,
        environ=environ,
        fallbacks_enabled=fallbacks_enabled,
        task_caps=task_caps,
        max_retries=0,
        timeout_s=timeout_s,
    )
