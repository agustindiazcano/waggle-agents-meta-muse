"""The closed schema ``voice-intent-v1`` for what a spoken command may ask for.

A proposal, from code or from a model, is data. It is parsed strictly: one JSON object with
exactly the four fields below, a closed intent enum, short lists of plain id strings that are only
candidates, and a confidence between 0 and 1. Any other field is rejected, so nothing said in the
audio can set an identity, a chassis, a zone, a speed or a limit. Ids are resolved against the
trusted order and catalog in code, never here.
"""

import json
import math
import re
from dataclasses import dataclass
from typing import Final

SCHEMA_VERSION: Final = "voice-intent-v1"
INTENTS: Final = frozenset(
    {"pick_item", "deliver_item", "report_obstruction", "status_query", "cancel_last"}
)
CONSEQUENTIAL: Final = frozenset({"pick_item", "deliver_item"})
MAX_IDS: Final = 5
_MAX_RAW_CHARS: Final = 1024
_FIELDS: Final = frozenset({"intent", "item_ids", "zone_ids", "confidence"})
_ID: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", re.ASCII)


class IntentError(ValueError):
    """The proposal does not match the schema. The caller rejects it."""


@dataclass(frozen=True)
class VoiceIntent:
    """A validated proposal. The ids are candidates, not authority."""

    intent: str
    item_ids: tuple[str, ...]
    zone_ids: tuple[str, ...]
    confidence: float


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in pairs:
        if key in fields:
            raise IntentError("duplicate field")
        fields[key] = value
    return fields


def _ids(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_IDS:
        raise IntentError(f"{name} must be a short list")
    found: list[str] = []
    for item in value:
        if not isinstance(item, str) or _ID.fullmatch(item) is None:
            raise IntentError(f"{name} holds an invalid id")
        found.append(item)
    if len(set(found)) != len(found):
        raise IntentError(f"{name} holds a repeated id")
    return tuple(found)


def _confidence(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):  # type: ignore[arg-type]
        raise IntentError("confidence must be a finite number")
    number = float(value)  # type: ignore[arg-type]
    if not 0.0 <= number <= 1.0:
        raise IntentError("confidence must be between 0 and 1")
    return number


def parse_voice_intent(raw: str) -> VoiceIntent:
    """Validate a raw proposal, or raise IntentError. Nothing is repaired or guessed."""
    if not isinstance(raw, str) or len(raw) > _MAX_RAW_CHARS:
        raise IntentError("proposal is not text or is too long")
    try:
        payload: object = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, RecursionError):
        raise IntentError("proposal is not valid JSON") from None
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise IntentError("proposal fields do not match the schema")
    intent = payload["intent"]
    if not isinstance(intent, str) or intent not in INTENTS:
        raise IntentError("intent is outside the closed enum")
    return VoiceIntent(
        intent,
        _ids(payload["item_ids"], "item_ids"),
        _ids(payload["zone_ids"], "zone_ids"),
        _confidence(payload["confidence"]),
    )
