"""Shared setup for the cloud-only llm smoke tests.

``smoke_provider`` refuses to build a provider unless the mode, the key, the cap, the model
id and verified prices are all present. It raises a real error, never skips, so a missing
secret in the cloud workflow shows as a failure and not as a pass (AGENTS.md 11.2).
"""

from collections.abc import Mapping

from waggle.llm.errors import ConfigError
from waggle.llm.http_provider import HttpProvider
from waggle.llm.provider_config import load_prices, load_settings, select_mode

MODEL_ENV_BY_ROUTE = {
    "meta": "META_MODEL_ID",
    "baseten": "BASETEN_MODEL_ID",
    "modal": "MODAL_GLIMMER_MODEL_ID",
}
SMOKE_PROMPT = "Reply with the single word: ok"
SMOKE_MAX_OUTPUT_TOKENS = 16
SMOKE_COST_LIMIT_USD = 0.02


def smoke_provider(route: str, environ: Mapping[str, str]) -> tuple[HttpProvider, str]:
    """Return the provider and model id for a route, or raise a typed error."""
    if select_mode(environ) != "http":
        raise ConfigError("llm smoke tests need WAGGLE_LLM_PROVIDER=http")
    model_env = MODEL_ENV_BY_ROUTE[route]
    model_id = environ.get(model_env, "").strip()
    if not model_id:
        raise ConfigError(f"{model_env} is not set")
    settings = load_settings(route, environ, load_prices())
    if not settings.price.verified:
        raise ConfigError(f"prices for {route} are not verified")
    provider = HttpProvider(settings, max_attempts=2, max_output_tokens=SMOKE_MAX_OUTPUT_TOKENS)
    return provider, model_id
