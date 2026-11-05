"""Vision pipeline: model report, strict schema, sanitizer, guard, registry lookup in code.

The vision model is only a reader. Its raw output is validated against ``vision-v1`` (which has
no package id field), the label text is sanitized and screened by the guard as an untrusted
package label, and only then is the sanitized text resolved against the trusted set of known
package ids in code. Exactly one match identifies the package; zero or several matches, a low
legibility, a guard rejection or an unreadable report all give ``unknown`` or ``rejected`` with
an escalation, never a guess. Instruction-like label text is data only, never an action (T1).

Vision is not in the control loop: the outcome may carry ``obstruction_class`` as data for the
planner, but it has no order, motion or execution field and nothing here creates one. Model
calls are not made here: a reader is any callable returning raw model text, and the vision call
itself lives in ``waggle.llm``. Every failure path returns a typed outcome; this module never
raises for untrusted input.
"""

import logging
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Literal

from waggle.governance.classifier import GuardClassifier, classify_input
from waggle.governance.guard import GuardOutcome
from waggle.governance.sanitizers import UntrustedSource
from waggle.multimodal.vision_schema import LabelError, VisionLabel, parse_vision_label

_LOGGER = logging.getLogger(__name__)
Status = Literal["identified", "unknown", "rejected"]
Reader = Callable[[], str]
_TOKEN = re.compile(r"[A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class VisionConfig:
    """Thresholds. The values are assumptions to calibrate in E7."""

    min_legibility: float = 0.7
    guard_timeout_s: float = 2.0


@dataclass(frozen=True)
class VisionOutcome:
    """What the pipeline decided. ``obstruction_class`` is data for the planner, never an order."""

    status: Status
    reason: str
    package_id: str | None = None
    obstruction_class: str | None = None
    label: VisionLabel | None = None
    escalate: bool = False


def resolve_label(label_text: str, known: Collection[str]) -> frozenset[str]:
    """The known package ids named exactly, as whole tokens, in the sanitized label text.

    ``resolve_items`` from the read-back module is not reused here: it resolves the spoken
    ``ITEM-n`` form (digits and number words) for voice, while package ids are arbitrary
    registry strings (``waggle.sim.packages`` allows ``[A-Za-z0-9_.-]{1,64}``). This lookup is
    exact and case-sensitive, so ``PKG-70`` does not match ``PKG-7`` and a partial or
    lower-case read matches nothing.
    """
    tokens = _TOKEN.findall(label_text)
    return frozenset(token for token in tokens if token in set(known))


async def process_image(
    reader: Reader,
    classifier: GuardClassifier,
    known_package_ids: Collection[str],
    *,
    config: VisionConfig,
) -> VisionOutcome:
    """Run one image report through the pipeline. It never raises for untrusted input."""
    try:
        raw = reader()
    except Exception:
        _LOGGER.warning("vision_reader_error")
        return VisionOutcome("unknown", "reader_error", escalate=True)
    try:
        label = parse_vision_label(raw)
    except LabelError:
        return VisionOutcome("unknown", "label_invalid", escalate=True)
    screened = await classify_input(
        label.label_text,
        UntrustedSource.PACKAGE_LABEL,
        classifier,
        timeout_s=config.guard_timeout_s,
    )
    if screened.outcome is not GuardOutcome.PASS or screened.sanitized is None:
        return VisionOutcome(
            "rejected", f"screening:{screened.reason_code}", label=label, escalate=True
        )
    if label.legibility < config.min_legibility:
        return VisionOutcome(
            "unknown",
            "low_legibility",
            obstruction_class=label.obstruction_class,
            label=label,
            escalate=True,
        )
    named = resolve_label(screened.sanitized.text, known_package_ids)
    if not named:
        return VisionOutcome(
            "unknown",
            "no_match",
            obstruction_class=label.obstruction_class,
            label=label,
            escalate=True,
        )
    if len(named) > 1:
        return VisionOutcome(
            "unknown",
            "ambiguous",
            obstruction_class=label.obstruction_class,
            label=label,
            escalate=True,
        )
    return VisionOutcome(
        "identified",
        "identified",
        package_id=next(iter(named)),
        obstruction_class=label.obstruction_class,
        label=label,
    )
