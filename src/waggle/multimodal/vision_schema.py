"""The closed schema ``vision-v1`` for what a vision model may report about an image.

A model output is data. It is parsed strictly: one JSON object with exactly the three fields
below, a closed obstruction enum, label text bounded by the package-label cap, and a legibility
between 0 and 1. There is deliberately no package id field: the model must never be trusted to
name the package. Any other field is rejected, so nothing printed on a label can set an identity,
a package, an action or a limit. The label text is resolved against the trusted registry in code,
never here.
"""

import json
import math
from dataclasses import dataclass
from typing import Final

SCHEMA_VERSION: Final = "vision-v1"
OBSTRUCTION_CLASSES: Final = frozenset({"none", "package", "human", "vehicle", "debris", "unknown"})
MAX_LABEL_CHARS: Final = 200
_FIELDS: Final = frozenset({"label_text", "obstruction_class", "legibility"})
_MAX_RAW_CHARS: Final = 1024


class LabelError(ValueError):
    """The model output does not match the schema. The caller treats it as unknown."""


@dataclass(frozen=True)
class VisionLabel:
    """A validated model report. ``label_text`` is untrusted data, not an identification."""

    label_text: str
    obstruction_class: str
    legibility: float


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in pairs:
        if key in fields:
            raise LabelError("duplicate field")
        fields[key] = value
    return fields


def _legibility(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):  # type: ignore[arg-type]
        raise LabelError("legibility must be a finite number")
    number = float(value)  # type: ignore[arg-type]
    if not 0.0 <= number <= 1.0:
        raise LabelError("legibility must be between 0 and 1")
    return number


def parse_vision_label(raw: str) -> VisionLabel:
    """Validate a raw model report, or raise LabelError. Nothing is repaired or guessed."""
    if not isinstance(raw, str) or len(raw) > _MAX_RAW_CHARS:
        raise LabelError("report is not text or is too long")
    try:
        payload: object = json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, RecursionError):
        raise LabelError("report is not valid JSON") from None
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise LabelError("report fields do not match the schema")
    label_text = payload["label_text"]
    if not isinstance(label_text, str) or len(label_text) > MAX_LABEL_CHARS:
        raise LabelError("label_text must be bounded text")
    obstruction = payload["obstruction_class"]
    if not isinstance(obstruction, str) or obstruction not in OBSTRUCTION_CLASSES:
        raise LabelError("obstruction_class is outside the closed enum")
    return VisionLabel(label_text, obstruction, _legibility(payload["legibility"]))
