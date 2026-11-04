import logging
from pathlib import Path

import pytest

from waggle.llm.errors import ConfigError, InvalidCapError
from waggle.llm.provider_config import (
    DEFAULT_PRICES_PATH,
    Price,
    Secret,
    load_prices,
    load_settings,
    select_mode,
)

KEY = "sk-test-0123456789-SECRETVALUE"
SECRET = "mt-SECRET-second-part-9876"
GOOD: dict[str, str] = {
    "META_API_KEY": KEY,
    "META_API_BASE_URL": "https://api.example.test/v1",
    "BASETEN_API_KEY": KEY,
    "MODAL_TOKEN_ID": "ak-id-1234",
    "MODAL_TOKEN_SECRET": SECRET,
    "MODAL_ENDPOINT_URL": "https://modal.example.test/v1",
    "META_SPEND_CAP_USD": "1.5",
    "BASETEN_SPEND_CAP_USD": "1.5",
    "MODAL_SPEND_CAP_USD": "1.5",
}
UNVERIFIED = Price(input_per_mtok=None, output_per_mtok=None, verified=False)


def test_secret_never_shows_its_value() -> None:
    secret = Secret(KEY)
    assert KEY not in repr(secret)
    assert KEY not in str(secret)
    assert KEY not in f"{secret!r} {secret}"
    assert secret.reveal() == KEY


def test_shipped_prices_meta_verified_others_unverified() -> None:
    prices = load_prices(DEFAULT_PRICES_PATH)
    assert set(prices) == {"meta", "baseten", "modal"}
    assert prices["meta"] == Price(input_per_mtok=1.25, output_per_mtok=4.25, verified=True)
    for name in ("baseten", "modal"):
        assert prices[name].verified is False


def test_prices_file_with_a_number_but_no_verified_flag_is_unverified(tmp_path: Path) -> None:
    path = tmp_path / "p.toml"
    path.write_text("[meta]\ninput_per_mtok = 1.0\noutput_per_mtok = 2.0\n", encoding="utf-8")
    assert load_prices(path)["meta"].verified is False


def test_prices_file_verified_without_numbers_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "p.toml"
    path.write_text("[meta]\nverified = true\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_prices(path)


@pytest.mark.parametrize("bad", ["-1.0", '"x"', "nan", "inf"])
def test_prices_file_rejects_bad_numbers(tmp_path: Path, bad: str) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        f"[meta]\nverified = true\ninput_per_mtok = {bad}\noutput_per_mtok = 1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_prices(path)


def test_prices_file_verified_with_numbers_loads(tmp_path: Path) -> None:
    path = tmp_path / "p.toml"
    path.write_text(
        "[meta]\nverified = true\ninput_per_mtok = 1.0\noutput_per_mtok = 2.5\n", encoding="utf-8"
    )
    price = load_prices(path)["meta"]
    assert price == Price(input_per_mtok=1.0, output_per_mtok=2.5, verified=True)


@pytest.mark.parametrize("provider", ["meta", "baseten", "modal"])
def test_settings_load_for_each_route(provider: str) -> None:
    settings = load_settings(provider, GOOD, {provider: UNVERIFIED})
    assert settings.name == provider
    assert settings.base_url.startswith("https://")
    assert settings.cap_usd == 1.5


def test_settings_headers_by_provider() -> None:
    meta = load_settings("meta", GOOD, {"meta": UNVERIFIED})
    modal = load_settings("modal", GOOD, {"modal": UNVERIFIED})
    baseten = load_settings("baseten", GOOD, {"baseten": UNVERIFIED})
    assert [(n, v.reveal()) for n, v in meta.auth] == [("Authorization", f"Bearer {KEY}")]
    assert [(n, v.reveal()) for n, v in baseten.auth] == [("Authorization", f"Bearer {KEY}")]
    assert [(n, v.reveal()) for n, v in modal.auth] == [
        ("Modal-Key", "ak-id-1234"),
        ("Modal-Secret", SECRET),
    ]
    assert baseten.base_url == "https://inference.baseten.co/v1"


@pytest.mark.parametrize("provider", ["meta", "baseten", "modal"])
@pytest.mark.parametrize("bad", [None, "", "  ", "abc", "-1", "nan", "inf"])
def test_missing_or_invalid_cap_fails_closed(provider: str, bad: str | None) -> None:
    environ = dict(GOOD)
    name = f"{provider.upper()}_SPEND_CAP_USD"
    if bad is None:
        del environ[name]
    else:
        environ[name] = bad
    with pytest.raises(InvalidCapError):
        load_settings(provider, environ, {provider: UNVERIFIED})


@pytest.mark.parametrize(
    "missing",
    [
        "META_API_KEY",
        "META_API_BASE_URL",
        "BASETEN_API_KEY",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "MODAL_ENDPOINT_URL",
    ],
)
def test_missing_value_fails_closed_and_names_only_the_variable(missing: str) -> None:
    environ = {k: v for k, v in GOOD.items() if k != missing}
    provider = {"META": "meta", "BASE": "baseten", "MODA": "modal"}[missing[:4]]
    with pytest.raises(ConfigError) as info:
        load_settings(provider, environ, {provider: UNVERIFIED})
    assert missing in str(info.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test/v1",
        "ftp://api.example.test/v1",
        "https://user:pw@api.example.test/v1",
        "https://api.example.test/v1?x=1",
        "https://api.example.test/v1#frag",
        "https:///v1",
        "not a url",
        "http://127.0.0.1:9/v1",
    ],
)
def test_unsafe_base_url_is_rejected_without_echoing_it(url: str) -> None:
    environ = dict(GOOD, META_API_BASE_URL=url)
    with pytest.raises(ConfigError) as info:
        load_settings("meta", environ, {"meta": UNVERIFIED})
    assert url not in str(info.value)


def test_loopback_http_needs_the_explicit_switch() -> None:
    environ = dict(GOOD, META_API_BASE_URL="http://127.0.0.1:9/v1")
    settings = load_settings("meta", environ, {"meta": UNVERIFIED}, allow_insecure_loopback=True)
    assert settings.base_url == "http://127.0.0.1:9/v1"
    remote = dict(GOOD, META_API_BASE_URL="http://api.example.test/v1")
    with pytest.raises(ConfigError):
        load_settings("meta", remote, {"meta": UNVERIFIED}, allow_insecure_loopback=True)


@pytest.mark.parametrize("bad", ["a\r\nX-Evil: 1", "a\nb", "a\x00b"])
def test_key_with_control_characters_is_rejected(bad: str) -> None:
    environ = dict(GOOD, META_API_KEY=bad)
    with pytest.raises(ConfigError) as info:
        load_settings("meta", environ, {"meta": UNVERIFIED})
    assert "X-Evil" not in str(info.value)


def test_unknown_provider_fails_closed() -> None:
    with pytest.raises(ConfigError):
        load_settings("vertex", GOOD, {})


def test_missing_price_entry_fails_closed() -> None:
    with pytest.raises(ConfigError):
        load_settings("meta", GOOD, {})


def test_no_secret_in_repr_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for provider in ("meta", "baseten", "modal"):
        settings = load_settings(provider, GOOD, {provider: UNVERIFIED})
        text = repr(settings) + str(settings)
        for secret in (KEY, SECRET, "ak-id-1234"):
            assert secret not in text
    for secret in (KEY, SECRET):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    ("environ", "expected"),
    [({"WAGGLE_LLM_PROVIDER": "mock"}, "mock"), ({"WAGGLE_LLM_PROVIDER": " http "}, "http")],
)
def test_select_mode(environ: dict[str, str], expected: str) -> None:
    assert select_mode(environ) == expected


@pytest.mark.parametrize("environ", [{}, {"WAGGLE_LLM_PROVIDER": ""}, {"WAGGLE_LLM_PROVIDER": "x"}])
def test_select_mode_fails_closed(environ: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        select_mode(environ)
