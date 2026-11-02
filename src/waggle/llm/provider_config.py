"""Provider settings read from environment variables by name, and the price table.

Nothing here prints, logs or puts a secret value in an exception message. Missing or
invalid values fail closed with a typed error.
"""

import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from waggle.llm.budget import parse_cap
from waggle.llm.errors import ConfigError

DEFAULT_PRICES_PATH = Path(__file__).with_name("prices.toml")
MODE_VAR = "WAGGLE_LLM_PROVIDER"
HTTP_PROVIDERS = ("meta", "baseten", "modal")
BASETEN_BASE_URL = "https://inference.baseten.co/v1"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

Mode = Literal["mock", "http"]


class Secret:
    """Holds a secret string. Its repr and str never show the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """Return the value. Call it only when building a request header."""
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    def __str__(self) -> str:
        return "***"


@dataclass(frozen=True)
class Price:
    """USD per million tokens. Real calls need ``verified`` and both numbers."""

    input_per_mtok: float | None
    output_per_mtok: float | None
    verified: bool


@dataclass(frozen=True)
class ProviderSettings:
    """Everything an HTTP provider needs. Header values are Secret objects."""

    name: str
    base_url: str
    auth: tuple[tuple[str, Secret], ...]
    price: Price
    cap_usd: float
    allow_insecure_loopback: bool = False


def select_mode(environ: Mapping[str, str]) -> Mode:
    """Read the provider mode from the environment. Anything but mock or http fails closed."""
    raw = environ.get(MODE_VAR, "").strip()
    if raw == "mock":
        return "mock"
    if raw == "http":
        return "http"
    raise ConfigError(f"{MODE_VAR} must be 'mock' or 'http'")


def _number(provider: str, key: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"prices: {provider}.{key} is not a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ConfigError(f"prices: {provider}.{key} must be a finite number >= 0")
    return number


def load_prices(path: Path | None = None) -> dict[str, Price]:
    """Load the price table. A missing flag means unverified."""
    data = tomllib.loads((path or DEFAULT_PRICES_PATH).read_text(encoding="utf-8"))
    prices: dict[str, Price] = {}
    for provider, entry in data.items():
        if not isinstance(entry, dict):
            raise ConfigError(f"prices: {provider} must be a table")
        verified = entry.get("verified", False)
        if not isinstance(verified, bool):
            raise ConfigError(f"prices: {provider}.verified must be true or false")
        price_in = entry.get("input_per_mtok")
        price_out = entry.get("output_per_mtok")
        if verified and (price_in is None or price_out is None):
            raise ConfigError(f"prices: {provider} is verified but a price is missing")
        prices[provider] = Price(
            input_per_mtok=None if price_in is None else _number(provider, "input", price_in),
            output_per_mtok=None if price_out is None else _number(provider, "output", price_out),
            verified=verified,
        )
    return prices


def _read(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "")
    if not value.strip():
        raise ConfigError(f"{name} is missing")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ConfigError(f"{name} has control characters")
    return value.strip()


def _checked_url(name: str, url: str, *, allow_loopback: bool) -> str:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018  (raises ValueError on a bad port)
    except ValueError:
        raise ConfigError(f"{name} is not a valid URL") from None
    secure = parts.scheme == "https"
    loopback = parts.scheme == "http" and allow_loopback and host in LOOPBACK_HOSTS
    if not (secure or loopback) or not host:
        raise ConfigError(f"{name} must be an https URL")
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ConfigError(f"{name} must not hold credentials, a query or a fragment")
    return url.rstrip("/")


def load_settings(
    provider: str,
    environ: Mapping[str, str],
    prices: Mapping[str, Price],
    *,
    allow_insecure_loopback: bool = False,
) -> ProviderSettings:
    """Build the settings of one route. A missing cap, key or URL fails closed."""
    if provider not in HTTP_PROVIDERS:
        raise ConfigError(f"no HTTP settings for provider {provider!r}")
    cap = parse_cap(provider, environ)
    price = prices.get(provider)
    if price is None:
        raise ConfigError(f"prices: no entry for {provider}")
    auth: tuple[tuple[str, Secret], ...]
    if provider == "meta":
        key = _read(environ, "META_API_KEY")
        url = _checked_url(
            "META_API_BASE_URL",
            _read(environ, "META_API_BASE_URL"),
            allow_loopback=allow_insecure_loopback,
        )
        auth = (("Authorization", Secret(f"Bearer {key}")),)
    elif provider == "baseten":
        key = _read(environ, "BASETEN_API_KEY")
        url = BASETEN_BASE_URL
        auth = (("Authorization", Secret(f"Bearer {key}")),)
    else:
        token_id = _read(environ, "MODAL_TOKEN_ID")
        token_secret = _read(environ, "MODAL_TOKEN_SECRET")
        url = _checked_url(
            "MODAL_ENDPOINT_URL",
            _read(environ, "MODAL_ENDPOINT_URL"),
            allow_loopback=allow_insecure_loopback,
        )
        auth = (("Modal-Key", Secret(token_id)), ("Modal-Secret", Secret(token_secret)))
    return ProviderSettings(
        name=provider,
        base_url=url,
        auth=auth,
        price=price,
        cap_usd=cap,
        allow_insecure_loopback=allow_insecure_loopback,
    )
