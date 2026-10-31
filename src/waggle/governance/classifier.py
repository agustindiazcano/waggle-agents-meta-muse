"""Offline guard contract and fail-closed screening after sanitization (ADR-032)."""

import asyncio
import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Protocol

from waggle.governance.guard import GuardLabel, GuardOutcome, screen
from waggle.governance.sanitizers import (
    Sanitized,
    SanitizeError,
    UntrustedSource,
    fence,
    sanitize,
)

_LOGGER = logging.getLogger(__name__)
_REASON_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}", re.ASCII)
_MAX_RESPONSE_CHARS = 1024


class GuardClassifier(Protocol):
    """Classify fenced data with strict JSON containing label and reason_code.

    Adapters must cooperate with asyncio cancellation and never block the event loop.
    Network/model adapters belong in waggle.llm, with their own transport timeouts.
    """

    async def classify(self, fenced_text: str) -> str:
        """Return raw output, without trusting or parsing it in the adapter."""
        ...


@dataclass(frozen=True)
class GuardResult:
    """Screening decision; cleaned text is available only after a benign verdict."""

    outcome: GuardOutcome
    label: GuardLabel | None
    reason_code: str
    sanitized: Sanitized | None = None


@dataclass
class MockClassifier:
    """Configured offline response and recorded fenced inputs for tests, not a detector."""

    response: str = '{"label":"uncertain","reason_code":"mock_unconfigured"}'
    inputs: list[str] = field(default_factory=list)

    async def classify(self, fenced_text: str) -> str:
        """Record the input and return the fixed response without I/O."""
        self.inputs.append(fenced_text)
        return self.response


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("duplicate classifier field")
        fields[key] = value
    return fields


def _parse(raw: str) -> tuple[GuardLabel, str]:
    if not isinstance(raw, str) or len(raw) > _MAX_RESPONSE_CHARS:
        raise ValueError("invalid classifier response")
    payload: object = json.loads(raw, object_pairs_hook=_unique_fields)
    if not isinstance(payload, dict) or set(payload) != {"label", "reason_code"}:
        raise ValueError("invalid classifier fields")
    label, reason = payload["label"], payload["reason_code"]
    if not isinstance(label, str) or not isinstance(reason, str):
        raise ValueError("invalid classifier field types")
    if _REASON_CODE.fullmatch(reason) is None:
        raise ValueError("invalid classifier reason code")
    return GuardLabel(label), reason


def _reject(reason_code: str) -> GuardResult:
    return GuardResult(screen(None), None, reason_code)


async def classify_input(
    text: str,
    source: UntrustedSource,
    classifier: GuardClassifier,
    *,
    timeout_s: float = 2.0,
) -> GuardResult:
    """Sanitize, fence, classify and apply screen(); failures reject and escalate.

    The timeout bounds a cooperative adapter. Caller cancellation propagates. No
    input or provider error text is logged, and rejected text is never returned.
    The caller is responsible for delivering the escalation to the operator inbox.
    """
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("timeout_s must be finite and positive")
    try:
        clean = sanitize(text, source)
    except SanitizeError as exc:
        return _reject(f"sanitize_{exc.code}")
    try:
        async with asyncio.timeout(timeout_s) as deadline:
            raw = await classifier.classify(fence(clean))
        if deadline.expired():
            raise TimeoutError
    except TimeoutError:
        _LOGGER.warning("classifier_timeout")
        return _reject("classifier_timeout")
    except Exception:
        # Adapter failures must not let untrusted input reach another model.
        _LOGGER.warning("classifier_error")
        return _reject("classifier_error")
    try:
        label, reason = _parse(raw)
    except (ValueError, RecursionError):
        return _reject("classifier_parse_error")
    outcome = screen(label)
    return GuardResult(outcome, label, reason, clean if outcome is GuardOutcome.PASS else None)
