from collections.abc import Mapping
from pathlib import Path

import pytest
from fake_llm_server import Canned, fake_server, ok_body

from waggle.llm.budget import BudgetGuard
from waggle.llm.call_log import InMemoryCallLog
from waggle.llm.client import LlmClient
from waggle.llm.errors import BudgetExceededError, ConfigError, InvalidCapError, ProviderError
from waggle.llm.http_provider import HttpProvider
from waggle.llm.models import LlmRequest
from waggle.llm.provider_factory import build_providers
from waggle.llm.providers import MockProvider
from waggle.llm.routing import load_routes

KEY = "sk-test-0123456789-SECRETVALUE"
VERIFIED = "[{p}]\nverified = true\ninput_per_mtok = 1.0\noutput_per_mtok = 2.0\n"


def _environ(url: str = "https://api.example.test/v1", mode: str = "http") -> dict[str, str]:
    return {
        "WAGGLE_LLM_PROVIDER": mode,
        "META_API_KEY": KEY,
        "META_API_BASE_URL": url,
        "BASETEN_API_KEY": KEY,
        "MODAL_TOKEN_ID": "ak-id-1234",
        "MODAL_TOKEN_SECRET": "mt-secret-9876",
        "MODAL_ENDPOINT_URL": url,
        "META_SPEND_CAP_USD": "1",
        "BASETEN_SPEND_CAP_USD": "1",
        "MODAL_SPEND_CAP_USD": "1",
        "META_MODEL_ID": "meta-text",
        "META_WONDER_MODEL_ID": "meta-wonder",
    }


def _prices(tmp_path: Path, *, verified: bool) -> Path:
    path = tmp_path / "prices.toml"
    if verified:
        text = "\n".join(VERIFIED.format(p=p) for p in ("meta", "baseten", "modal"))
    else:
        text = "[meta]\n[baseten]\n[modal]\n"
    path.write_text(text, encoding="utf-8")
    return path


def test_mock_mode_returns_mock_providers_and_needs_no_key() -> None:
    providers = build_providers({"WAGGLE_LLM_PROVIDER": "mock"})
    assert set(providers) == {"meta", "baseten", "modal", "vertex"}
    assert all(isinstance(p, MockProvider) for p in providers.values())


@pytest.mark.parametrize("environ", [{}, {"WAGGLE_LLM_PROVIDER": "real"}])
def test_unset_or_unknown_mode_fails_closed(environ: Mapping[str, str]) -> None:
    with pytest.raises(ConfigError):
        build_providers(environ)


def test_http_mode_builds_three_routes_and_leaves_vertex_unregistered(tmp_path: Path) -> None:
    providers = build_providers(_environ(), _prices(tmp_path, verified=True))
    assert set(providers) == {"meta", "baseten", "modal"}
    assert all(isinstance(p, HttpProvider) for p in providers.values())


@pytest.mark.parametrize("provider", ["meta", "baseten", "modal"])
def test_http_mode_missing_cap_fails_closed(tmp_path: Path, provider: str) -> None:
    environ = _environ()
    del environ[f"{provider.upper()}_SPEND_CAP_USD"]
    with pytest.raises(InvalidCapError):
        build_providers(environ, _prices(tmp_path, verified=True))


def test_http_mode_missing_key_fails_closed(tmp_path: Path) -> None:
    environ = _environ()
    del environ["META_API_KEY"]
    with pytest.raises(ConfigError):
        build_providers(environ, _prices(tmp_path, verified=True))


def test_shipped_prices_meta_estimates_cost_others_refuse() -> None:
    providers = build_providers(_environ())
    request = LlmRequest("r", "director", "hi")
    assert providers["meta"].estimate_cost(request) > 0
    for name in ("baseten", "modal"):
        with pytest.raises(ConfigError):
            providers[name].estimate_cost(request)


def _client(
    url: str, tmp_path: Path, *, verified: bool = True, cap: str = "1", attempts: int = 3
) -> tuple[LlmClient, InMemoryCallLog]:
    environ = _environ(url)
    environ["META_SPEND_CAP_USD"] = cap
    providers = build_providers(
        environ,
        _prices(tmp_path, verified=verified),
        allow_insecure_loopback=True,
        sleep=lambda _s: None,
        max_attempts=attempts,
    )
    log = InMemoryCallLog()
    client = LlmClient(
        providers=providers,
        table=load_routes(),
        guard=BudgetGuard(environ, log),
        log=log,
        environ=environ,
        fallbacks_enabled=False,
    )
    return client, log


def test_client_end_to_end_logs_cost_from_usage(tmp_path: Path) -> None:
    with fake_server([Canned(body=ok_body("go", 1_000_000, 500_000))]) as (url, state):
        client, log = _client(url, tmp_path)
        result = client.call(LlmRequest("r1", "director", "plan the shift"))
    assert result.text == "go"
    assert result.cost_usd == pytest.approx(1.0 + 1.0)
    record = log.records()[-1]
    assert (record.provider, record.status, record.tokens_in) == ("meta", "ok", 1_000_000)
    assert len(state.seen) == 1


def test_client_budget_denial_makes_no_http_request(tmp_path: Path) -> None:
    with fake_server([Canned(body=ok_body())]) as (url, state):
        client, log = _client(url, tmp_path, cap="0.0001")
        with pytest.raises(BudgetExceededError):
            client.call(LlmRequest("r1", "director", "plan the shift"))
    assert state.seen == []
    assert log.records()[-1].status == "denied"


def test_client_unverified_prices_make_no_http_request(tmp_path: Path) -> None:
    with fake_server([Canned(body=ok_body())]) as (url, state):
        client, _ = _client(url, tmp_path, verified=False)
        with pytest.raises(ConfigError):
            client.call(LlmRequest("r1", "director", "plan the shift"))
    assert state.seen == []


def test_client_provider_failure_is_logged_as_error_and_not_cached(tmp_path: Path) -> None:
    with fake_server([Canned(status=500, body=b"x"), Canned(body=ok_body())]) as (url, state):
        client, log = _client(url, tmp_path, attempts=1)
        request = LlmRequest("r1", "director", "plan the shift")
        with pytest.raises(ProviderError):
            client.call(request)
        assert log.records()[-1].status == "error"
        assert client.call(request).text == "hello"
    assert len(state.seen) == 2
