"""Build the provider map from the environment: mock for tests, http for real routes.

The mode comes from WAGGLE_LLM_PROVIDER (AGENTS.md 6.1). In http mode a route is
registered only when its settings load: a missing cap, key or URL raises before any
call. ``vertex`` is not registered (see docs/PROVIDER_INTEGRATION.md), so a call routed
to it fails closed with ConfigError in the client.
"""

import time
from collections.abc import Callable, Mapping
from pathlib import Path

from waggle.llm.budget import PROVIDERS
from waggle.llm.http_provider import HttpProvider
from waggle.llm.provider_config import HTTP_PROVIDERS, load_prices, load_settings, select_mode
from waggle.llm.providers import MockProvider, Provider


def build_providers(
    environ: Mapping[str, str],
    prices_path: Path | None = None,
    *,
    allow_insecure_loopback: bool = False,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Provider]:
    """Return the provider map for the selected mode. Fails closed on any bad setting."""
    if select_mode(environ) == "mock":
        return {name: MockProvider(name) for name in PROVIDERS}
    prices = load_prices(prices_path)
    providers: dict[str, Provider] = {}
    for name in HTTP_PROVIDERS:
        settings = load_settings(
            name, environ, prices, allow_insecure_loopback=allow_insecure_loopback
        )
        providers[name] = HttpProvider(settings, max_attempts=max_attempts, sleep=sleep)
    return providers
