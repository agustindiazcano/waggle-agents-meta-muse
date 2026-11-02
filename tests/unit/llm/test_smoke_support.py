import pytest
from llm_smoke_support import MODEL_ENV_BY_ROUTE, smoke_provider

from waggle.llm.errors import ConfigError, InvalidCapError
from waggle.llm.http_provider import HttpProvider

FULL = {
    "WAGGLE_LLM_PROVIDER": "http",
    "META_API_KEY": "k",
    "META_API_BASE_URL": "https://api.example.test/v1",
    "BASETEN_API_KEY": "k",
    "MODAL_TOKEN_ID": "i",
    "MODAL_TOKEN_SECRET": "s",
    "MODAL_ENDPOINT_URL": "https://modal.example.test/v1",
    "META_SPEND_CAP_USD": "1",
    "BASETEN_SPEND_CAP_USD": "1",
    "MODAL_SPEND_CAP_USD": "1",
    "META_MODEL_ID": "a",
    "BASETEN_MODEL_ID": "b",
    "MODAL_GLIMMER_MODEL_ID": "c",
}


@pytest.mark.parametrize("route", sorted(MODEL_ENV_BY_ROUTE))
def test_empty_environment_is_refused(route: str) -> None:
    with pytest.raises(ConfigError):
        smoke_provider(route, {})


@pytest.mark.parametrize("route", ["baseten", "modal"])
def test_shipped_unverified_prices_are_refused(route: str) -> None:
    with pytest.raises(ConfigError, match="not verified"):
        smoke_provider(route, FULL)


def test_shipped_verified_meta_price_builds() -> None:
    provider, model_id = smoke_provider("meta", FULL)
    assert isinstance(provider, HttpProvider)
    assert model_id == "a"


@pytest.mark.parametrize("route", sorted(MODEL_ENV_BY_ROUTE))
def test_missing_cap_is_refused(route: str) -> None:
    environ = {k: v for k, v in FULL.items() if k != f"{route.upper()}_SPEND_CAP_USD"}
    with pytest.raises(InvalidCapError):
        smoke_provider(route, environ)


@pytest.mark.parametrize("route", sorted(MODEL_ENV_BY_ROUTE))
def test_missing_model_id_is_refused(route: str) -> None:
    environ = {k: v for k, v in FULL.items() if k != MODEL_ENV_BY_ROUTE[route]}
    with pytest.raises(ConfigError, match="MODEL_ID"):
        smoke_provider(route, environ)
