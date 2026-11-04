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


@pytest.mark.parametrize("route", sorted(MODEL_ENV_BY_ROUTE))
def test_shipped_verified_prices_build(route: str) -> None:
    provider, model_id = smoke_provider(route, FULL)
    assert isinstance(provider, HttpProvider)
    assert model_id == FULL[MODEL_ENV_BY_ROUTE[route]]


@pytest.mark.parametrize("route", sorted(MODEL_ENV_BY_ROUTE))
def test_unverified_prices_are_refused(route: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import llm_smoke_support
    from waggle.llm.provider_config import Price

    monkeypatch.setattr(
        llm_smoke_support,
        "load_prices",
        lambda: {r: Price(None, None, False) for r in MODEL_ENV_BY_ROUTE},
    )
    with pytest.raises(ConfigError, match="not verified"):
        smoke_provider(route, FULL)


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
