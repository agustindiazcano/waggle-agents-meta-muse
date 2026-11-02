import json
import logging
import traceback
from collections.abc import Mapping

import pytest
from fake_llm_server import Canned, fake_server, ok_body

from waggle.llm.errors import ConfigError, ProviderError
from waggle.llm.http_provider import HttpProvider
from waggle.llm.models import LlmRequest
from waggle.llm.provider_config import Price, ProviderSettings, load_settings

KEY = "sk-test-0123456789-SECRETVALUE"
MODAL_SECRET = "mt-SECRET-second-part-9876"
PRICE = Price(input_per_mtok=2.0, output_per_mtok=10.0, verified=True)
REQUEST = LlmRequest(request_id="r1", role="director", prompt="say hello to the fleet")


def _environ(url: str) -> Mapping[str, str]:
    return {
        "META_API_KEY": KEY,
        "META_API_BASE_URL": url,
        "MODAL_TOKEN_ID": "ak-id-1234",
        "MODAL_TOKEN_SECRET": MODAL_SECRET,
        "MODAL_ENDPOINT_URL": url,
        "META_SPEND_CAP_USD": "1",
        "MODAL_SPEND_CAP_USD": "1",
    }


def _settings(url: str, provider: str = "meta", price: Price = PRICE) -> ProviderSettings:
    return load_settings(provider, _environ(url), {provider: price}, allow_insecure_loopback=True)


class Sleeper:
    """Records waits instead of sleeping."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def _provider(
    url: str, sleeper: Sleeper | None = None, *, provider: str = "meta", **kwargs: object
) -> HttpProvider:
    options: dict[str, object] = {"timeout_s": 2.0, "max_attempts": 3}
    options.update(kwargs)
    return HttpProvider(
        _settings(url, provider),
        sleep=sleeper or Sleeper(),
        **options,  # type: ignore[arg-type]  # test helper passes keyword options through
    )


def _failure_text(err: BaseException) -> str:
    return "".join(traceback.format_exception(err)) + repr(err) + str(err)


def test_success_parses_text_usage_and_cost() -> None:
    with fake_server([Canned(body=ok_body("fleet ready", 1000, 200))]) as (url, state):
        result = _provider(url).complete(REQUEST, "model-x")
    assert result.text == "fleet ready"
    assert result.model_id == "model-x"
    assert (result.tokens_in, result.tokens_out) == (1000, 200)
    assert result.cost_usd == pytest.approx(1000 * 2.0 / 1e6 + 200 * 10.0 / 1e6)
    assert result.latency_s >= 0
    seen = state.seen[0]
    assert seen.path == "/v1/chat/completions"
    body = json.loads(seen.body)
    assert body["model"] == "model-x"
    assert body["messages"] == [{"role": "user", "content": REQUEST.prompt}]
    assert body["max_tokens"] > 0
    assert seen.headers["authorization"] == f"Bearer {KEY}"
    assert seen.headers["content-type"] == "application/json"


def test_modal_sends_its_two_headers() -> None:
    with fake_server([Canned(body=ok_body())]) as (url, state):
        _provider(url, provider="modal").complete(REQUEST, "m")
    headers = state.seen[0].headers
    assert headers["modal-key"] == "ak-id-1234"
    assert headers["modal-secret"] == MODAL_SECRET
    assert "authorization" not in headers


def test_content_type_with_charset_is_accepted() -> None:
    canned = Canned(body=ok_body(), content_type="application/json; charset=utf-8")
    with fake_server([canned]) as (url, _):
        assert _provider(url).complete(REQUEST, "m").text == "hello"


def test_retry_after_on_429_is_honored_then_succeeds() -> None:
    script = [
        Canned(status=429, body=b"{}", headers=(("Retry-After", "2"),)),
        Canned(body=ok_body()),
    ]
    sleeper = Sleeper()
    with fake_server(script) as (url, state):
        result = _provider(url, sleeper).complete(REQUEST, "m")
    assert result.text == "hello"
    assert sleeper.waits == [2.0]
    assert len(state.seen) == 2


def test_retry_after_is_capped() -> None:
    script = [
        Canned(status=429, body=b"{}", headers=(("Retry-After", "86400"),)),
        Canned(body=ok_body()),
    ]
    sleeper = Sleeper()
    with fake_server(script) as (url, _):
        _provider(url, sleeper, retry_after_cap_s=5.0).complete(REQUEST, "m")
    assert sleeper.waits == [5.0]


@pytest.mark.parametrize("header", ["soon", "-3", "nan", "Wed, 21 Oct 2026 07:28:00 GMT", ""])
def test_unusable_retry_after_falls_back_to_backoff(header: str) -> None:
    script = [
        Canned(status=429, body=b"{}", headers=(("Retry-After", header),)),
        Canned(200, ok_body()),
    ]
    sleeper = Sleeper()
    with fake_server(script) as (url, _):
        _provider(url, sleeper, backoff_base_s=0.25).complete(REQUEST, "m")
    assert sleeper.waits == [0.25]


def test_429_forever_ends_in_provider_error_after_the_attempt_cap() -> None:
    sleeper = Sleeper()
    with fake_server([Canned(status=429, body=b"{}")]) as (url, state):  # noqa: SIM117
        with pytest.raises(ProviderError):
            _provider(url, sleeper, max_attempts=3).complete(REQUEST, "m")
    assert len(state.seen) == 3
    assert len(sleeper.waits) == 2


def test_500_is_retried_with_exponential_backoff() -> None:
    script = [
        Canned(status=500, body=b"boom"),
        Canned(status=503, body=b"x"),
        Canned(200, ok_body()),
    ]
    sleeper = Sleeper()
    with fake_server(script) as (url, state):
        _provider(url, sleeper, backoff_base_s=0.5).complete(REQUEST, "m")
    assert sleeper.waits == [0.5, 1.0]
    assert len(state.seen) == 3


def test_persistent_500_raises_provider_error() -> None:
    with fake_server([Canned(status=500, body=b"boom")]) as (url, state):  # noqa: SIM117
        with pytest.raises(ProviderError):
            _provider(url, max_attempts=2).complete(REQUEST, "m")
    assert len(state.seen) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retried(status: int) -> None:
    with fake_server([Canned(status=status, body=b'{"error": "nope"}')]) as (url, state):  # noqa: SIM117
        with pytest.raises(ProviderError) as info:
            _provider(url).complete(REQUEST, "m")
    assert len(state.seen) == 1
    assert str(status) in str(info.value)


def test_redirect_is_never_followed() -> None:
    script = [Canned(status=302, headers=(("Location", "http://127.0.0.1:1/steal"),))]
    with fake_server(script) as (url, state), pytest.raises(ProviderError):
        _provider(url).complete(REQUEST, "m")
    assert len(state.seen) == 1


def test_hang_times_out_and_is_retried_then_fails() -> None:
    with fake_server([Canned(body=ok_body(), hang_s=5.0)]) as (url, state):  # noqa: SIM117
        with pytest.raises(ProviderError):
            _provider(url, timeout_s=0.3, max_attempts=2).complete(REQUEST, "m")
    assert len(state.seen) == 2


def test_connection_refused_raises_provider_error() -> None:
    from fake_llm_server import closed_port_url

    with pytest.raises(ProviderError):
        _provider(closed_port_url(), max_attempts=1).complete(REQUEST, "m")


GOOD_USAGE = '{"prompt_tokens": 1, "completion_tokens": 1}'
GOOD_CHOICE = '[{"message": {"content": "a"}}]'


def _raw(choices: str = GOOD_CHOICE, usage: str = GOOD_USAGE) -> bytes:
    return f'{{"choices": {choices}, "usage": {usage}}}'.encode()


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"",
        b"[]",
        b'"text"',
        b"{}",
        b'{"choices": []}',
        _raw("[{}]"),
        _raw('[{"message": {}}]'),
        _raw('[{"message": {"content": null}}]'),
        _raw('[{"message": {"content": 5}}]'),
        _raw('[{"message": {"content": "a"}}, {"message": {"content": "b"}}]'),
        _raw('[{"message": {"content": "a"}, "message": {"content": "b"}}]'),
        _raw(usage='{"prompt_tokens": 1, "prompt_tokens": 2, "completion_tokens": 1}'),
        _raw(usage='{"prompt_tokens": 1}'),
        _raw(usage='{"prompt_tokens": -1, "completion_tokens": 1}'),
        _raw(usage='{"prompt_tokens": "1", "completion_tokens": 1}'),
        _raw(usage='{"prompt_tokens": 1.5, "completion_tokens": 1}'),
        _raw(usage='{"prompt_tokens": true, "completion_tokens": 1}'),
        _raw(usage="null"),
        _raw(usage='{"prompt_tokens": NaN, "completion_tokens": 1}'),
    ],
)
def test_malformed_or_incomplete_body_is_rejected_without_retry(body: bytes) -> None:
    with fake_server([Canned(body=body)]) as (url, state), pytest.raises(ProviderError):
        _provider(url).complete(REQUEST, "m")
    assert len(state.seen) == 1


def test_missing_usage_is_rejected_because_cost_cannot_be_known() -> None:
    with fake_server([Canned(body=ok_body(usage=False))]) as (url, _):  # noqa: SIM117
        with pytest.raises(ProviderError) as info:
            _provider(url).complete(REQUEST, "m")
    assert "usage" in str(info.value)


def test_extra_envelope_fields_are_ignored() -> None:
    body = json.loads(ok_body())
    body["system_fingerprint"] = "fp"
    body["usage"]["total_tokens"] = 15
    with fake_server([Canned(body=json.dumps(body).encode())]) as (url, _):
        assert _provider(url).complete(REQUEST, "m").text == "hello"


def test_oversized_body_is_rejected() -> None:
    big = ok_body("x" * 5000)
    with fake_server([Canned(body=big)]) as (url, _), pytest.raises(ProviderError) as info:
        _provider(url, max_body_bytes=1000).complete(REQUEST, "m")
    assert "size" in str(info.value)


@pytest.mark.parametrize("ctype", ["text/html", "text/plain", None, "application/xml"])
def test_wrong_content_type_is_rejected(ctype: str | None) -> None:
    with fake_server([Canned(body=ok_body(), content_type=ctype)]) as (url, state):  # noqa: SIM117
        with pytest.raises(ProviderError):
            _provider(url).complete(REQUEST, "m")
    assert len(state.seen) == 1


def test_estimate_cost_uses_prompt_size_and_the_output_cap() -> None:
    provider = _provider("http://127.0.0.1:9/v1", max_output_tokens=1000)
    short = provider.estimate_cost(LlmRequest("a", "director", "hi"))
    long = provider.estimate_cost(LlmRequest("b", "director", "word " * 4000))
    assert short >= 1000 * 10.0 / 1e6
    assert long > short


@pytest.mark.parametrize(
    "price",
    [
        Price(None, None, False),
        Price(2.0, 10.0, False),
        Price(None, 10.0, True),
        Price(2.0, None, True),
    ],
)
def test_unverified_or_missing_price_refuses_estimate_and_call_without_any_request(
    price: Price,
) -> None:
    with fake_server([Canned(body=ok_body())]) as (url, state):
        provider = HttpProvider(_settings(url, price=price), sleep=Sleeper())
        with pytest.raises(ConfigError):
            provider.estimate_cost(REQUEST)
        with pytest.raises(ConfigError):
            provider.complete(REQUEST, "m")
    assert state.seen == []


def test_bad_options_fail_closed() -> None:
    settings = _settings("http://127.0.0.1:9/v1")
    for bad in ({"timeout_s": 0}, {"max_attempts": 0}, {"max_body_bytes": 0}, {"timeout_s": 999}):
        with pytest.raises(ConfigError):
            HttpProvider(settings, **bad)  # type: ignore[arg-type]  # deliberate bad values


@pytest.mark.parametrize(
    "canned",
    [
        Canned(status=401, body=b'{"error": "bad key ' + KEY.encode() + b'"}'),
        Canned(status=500, body=KEY.encode()),
        Canned(status=429, body=KEY.encode(), headers=(("X-Echo", KEY),)),
        Canned(body=b"not json " + KEY.encode()),
        Canned(body=KEY.encode(), content_type="text/plain"),
        Canned(body=ok_body(usage=False)),
    ],
)
def test_key_never_appears_in_exception_log_or_repr(
    canned: Canned, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with fake_server([canned]) as (url, _):
        provider = _provider(url, max_attempts=2)
        with pytest.raises(ProviderError) as info:
            provider.complete(REQUEST, "m")
        texts = [_failure_text(info.value), caplog.text, repr(provider), str(provider)]
        texts += [repr(provider.__dict__)]
    for text in texts:
        assert KEY not in text
        assert MODAL_SECRET not in text


def test_refused_connection_error_text_has_no_key(caplog: pytest.LogCaptureFixture) -> None:
    from fake_llm_server import closed_port_url

    caplog.set_level(logging.DEBUG)
    provider = _provider(closed_port_url(), max_attempts=1)
    with pytest.raises(ProviderError) as info:
        provider.complete(REQUEST, "m")
    assert KEY not in _failure_text(info.value) + caplog.text


def test_modal_secrets_not_in_failure_text() -> None:
    with fake_server([Canned(status=401, body=MODAL_SECRET.encode())]) as (url, _):  # noqa: SIM117
        with pytest.raises(ProviderError) as info:
            _provider(url, provider="modal").complete(REQUEST, "m")
    text = _failure_text(info.value)
    assert MODAL_SECRET not in text
    assert "ak-id-1234" not in text


def test_each_attempt_uses_a_fresh_connection() -> None:
    script = [Canned(status=500, body=b"x"), Canned(body=ok_body())]
    with fake_server(script) as (url, state):
        _provider(url).complete(REQUEST, "m")
    assert len(state.seen) == 2
