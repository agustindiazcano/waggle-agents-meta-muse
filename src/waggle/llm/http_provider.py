"""HTTP provider for OpenAI-style chat completions, standard library only.

One class serves Meta, Baseten and Modal; the settings carry the URL and the auth headers.
Failure rules (ADR-070): every failure ends in ProviderError or ConfigError, never in a
partial result. Messages carry the provider name and a status or reason only, never a
header value, a URL or a response body, so a key cannot leak through an exception.
"""

import http.client
import json
import logging
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from waggle.llm.errors import ConfigError, ProviderError
from waggle.llm.models import Completion, LlmRequest
from waggle.llm.provider_config import ProviderSettings

logger = logging.getLogger("waggle.llm")

CHARS_PER_TOKEN = 3
MAX_TIMEOUT_S = 60.0
MAX_ATTEMPTS = 10
MAX_TOKEN_COUNT = 10**9
_RETRY_AFTER = re.compile(r"^\d+(\.\d+)?$")


class _Transient(Exception):
    """An attempt failed in a way that may succeed on retry. Internal to this module."""

    def __init__(self, reason: str, wait_s: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.wait_s = wait_s


@dataclass(frozen=True)
class _Answer:
    status: int
    retry_after: str | None
    content_type: str | None
    body: bytes


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def _reject_constant(name: str) -> object:
    raise ValueError("non-finite number")


def _count(usage: dict[str, object], key: str) -> int:
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_TOKEN_COUNT:
        raise ProviderError("response usage is missing or invalid")
    return value


def parse_chat_completion(body: bytes) -> tuple[str, int, int]:
    """Return text, tokens in and tokens out. Anything unexpected raises ProviderError."""
    try:
        data = json.loads(body, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise ProviderError("response is not valid JSON") from None
    if not isinstance(data, dict):
        raise ProviderError("response is not a JSON object")
    choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProviderError("response needs exactly one choice")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ProviderError("response has no text content")
    usage = data.get("usage")
    if not isinstance(usage, dict):
        raise ProviderError("response usage is missing or invalid")
    return content, _count(usage, "prompt_tokens"), _count(usage, "completion_tokens")


def _retry_after_seconds(raw: str | None, cap_s: float) -> float | None:
    """Seconds to wait from a Retry-After header, capped. Dates and junk give None."""
    if raw is None or not _RETRY_AFTER.match(raw.strip()):
        return None
    value = float(raw.strip())
    return min(value, cap_s) if math.isfinite(value) else None


class HttpProvider:
    """Chat-completions client for one route. Real calls need verified prices."""

    def __init__(
        self,
        settings: ProviderSettings,
        *,
        timeout_s: float = 10.0,
        max_attempts: int = 3,
        backoff_base_s: float = 0.5,
        retry_after_cap_s: float = 5.0,
        max_body_bytes: int = 1_000_000,
        max_output_tokens: int = 512,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 < timeout_s <= MAX_TIMEOUT_S:
            raise ConfigError(f"timeout_s must be above 0 and at most {MAX_TIMEOUT_S:g}")
        if not 1 <= max_attempts <= MAX_ATTEMPTS:
            raise ConfigError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")
        if max_body_bytes < 1 or max_output_tokens < 1 or backoff_base_s < 0:
            raise ConfigError("size and backoff options must be positive")
        if retry_after_cap_s < 0:
            raise ConfigError("retry_after_cap_s must not be negative")
        self.name = settings.name
        self._settings = settings
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._retry_after_cap_s = retry_after_cap_s
        self._max_body_bytes = max_body_bytes
        self._max_output_tokens = max_output_tokens
        self._sleep = sleep
        self._clock = clock
        parts = urlsplit(settings.base_url)
        self._https = parts.scheme == "https"
        self._host = parts.hostname or ""
        self._port = parts.port
        self._path = parts.path.rstrip("/") + "/chat/completions"

    def _rates(self) -> tuple[float, float]:
        price = self._settings.price
        if not price.verified or price.input_per_mtok is None or price.output_per_mtok is None:
            raise ConfigError(f"{self.name}: prices are not verified, real calls are refused")
        return price.input_per_mtok, price.output_per_mtok

    def estimate_cost(self, request: LlmRequest) -> float:
        """Upper estimate: prompt size by characters plus the full output cap."""
        rate_in, rate_out = self._rates()
        tokens_in = len(request.prompt) // CHARS_PER_TOKEN + 1
        return (tokens_in * rate_in + self._max_output_tokens * rate_out) / 1e6

    def complete(self, request: LlmRequest, model_id: str) -> Completion:
        """Call the route. Retries 429, 5xx and transport errors up to the attempt cap."""
        rate_in, rate_out = self._rates()
        payload = json.dumps(
            {
                "model": model_id,
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": self._max_output_tokens,
            }
        ).encode("utf-8")
        started = self._clock()
        body = self._with_retries(payload, request.request_id)
        text, tokens_in, tokens_out = parse_chat_completion(body)
        return Completion(
            text=text,
            model_id=model_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_s=self._clock() - started,
            cost_usd=(tokens_in * rate_in + tokens_out * rate_out) / 1e6,
        )

    def _with_retries(self, payload: bytes, request_id: str) -> bytes:
        reason = "no attempt"
        for attempt in range(1, self._max_attempts + 1):
            try:
                return self._once(payload)
            except _Transient as err:
                reason = err.reason
                if attempt == self._max_attempts:
                    break
                wait = err.wait_s
                if wait is None:
                    wait = min(self._backoff_base_s * 2 ** (attempt - 1), self._retry_after_cap_s)
                logger.warning(
                    "%s attempt %d for request %s failed (%s), waiting %.2fs",
                    self.name,
                    attempt,
                    request_id,
                    reason,
                    wait,
                )
                self._sleep(wait)
        raise ProviderError(f"{self.name}: failed after {self._max_attempts} attempts ({reason})")

    def _once(self, payload: bytes) -> bytes:
        answer = self._exchange(payload)
        status = answer.status
        if status == 429:
            wait = _retry_after_seconds(answer.retry_after, self._retry_after_cap_s)
            raise _Transient("HTTP 429", wait)
        if status >= 500:
            raise _Transient(f"HTTP {status}")
        if status != 200:
            raise ProviderError(f"{self.name}: HTTP {status}")
        content_type = (answer.content_type or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise ProviderError(f"{self.name}: response content type is not JSON")
        return answer.body

    def _exchange(self, payload: bytes) -> _Answer:
        """One request on a fresh connection. Redirects are never followed."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Length": str(len(payload)),
        }
        for name, secret in self._settings.auth:
            headers[name] = secret.reveal()
        conn: http.client.HTTPConnection
        if self._https:
            conn = http.client.HTTPSConnection(self._host, self._port, timeout=self._timeout_s)
        else:
            conn = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout_s)
        deadline = self._clock() + self._timeout_s
        try:
            conn.request("POST", self._path, body=payload, headers=headers)
            response = conn.getresponse()
            status = response.status
            length = response.getheader("Content-Length")
            declared = int(length) if status == 200 and length and length.isdigit() else 0
            if declared > self._max_body_bytes:
                raise ProviderError(f"{self.name}: response over the size cap")
            body = b""
            if status == 200:
                body = self._read_capped(response, deadline)
            return _Answer(
                status=status,
                retry_after=response.getheader("Retry-After"),
                content_type=response.getheader("Content-Type"),
                body=body,
            )
        except (OSError, http.client.HTTPException):
            raise _Transient("transport error") from None
        finally:
            conn.close()

    def _read_capped(self, response: http.client.HTTPResponse, deadline: float) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            if self._clock() > deadline:
                raise _Transient("response too slow")
            chunk = response.read(8192)
            if not chunk:
                return b"".join(chunks)
            total += len(chunk)
            if total > self._max_body_bytes:
                raise ProviderError(f"{self.name}: response over the size cap")
            chunks.append(chunk)
