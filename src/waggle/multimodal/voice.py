"""Voice pipeline: transcript, sanitizer, guard, intent schema, item resolution, read-back.

Authority comes from the authenticated operator session, never from the audio or the transcript.
The transcript is untrusted: it is sanitized and screened by the guard before any proposer sees
it, a proposal is validated against ``voice-intent-v1``, and items are resolved against the trusted
order in code. A consequential command (pick, deliver) ends in a read-back that names the trusted
item. Only a typed ``Confirmation`` from the operator channel authorizes (ADR-057); the words
"yes" or "confirmed" in a transcript are never parsed. Every failure rejects or asks to repeat and
none creates an order. Model calls are not made here: a proposer is any callable, and the
transcription call lives in ``waggle.llm``.
"""

import json
import logging
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Final, Literal

from waggle.governance.classifier import GuardClassifier, classify_input
from waggle.governance.guard import GuardOutcome
from waggle.governance.readback import (
    Confirmation,
    Decision,
    ReadBackPrompt,
    authorize,
    resolve_items,
    start_readback,
)
from waggle.governance.sanitizers import UntrustedSource
from waggle.multimodal.voice_intent import (
    CONSEQUENTIAL,
    IntentError,
    VoiceIntent,
    parse_voice_intent,
)

_LOGGER = logging.getLogger(__name__)
Status = Literal["rejected", "repeat", "awaiting_confirmation", "accepted"]
Proposer = Callable[[str], str]
_KEYWORDS: Final[dict[str, str]] = {
    "pick": "pick_item",
    "deliver": "deliver_item",
    "drop": "deliver_item",
    "blocked": "report_obstruction",
    "obstruction": "report_obstruction",
    "obstructed": "report_obstruction",
    "status": "status_query",
    "where": "status_query",
    "cancel": "cancel_last",
    "undo": "cancel_last",
}
_WORD = re.compile(r"[a-z]+")
_KEYWORD_CONFIDENCE: Final = 0.9


@dataclass(frozen=True)
class OperatorSession:
    """The authenticated operator of the request. It comes from the session, not from the audio."""

    operator_id: str
    authenticated: bool


@dataclass(frozen=True)
class TrustedOrder:
    """The item the operator is working on and the catalog of known items, both trusted."""

    ordered_item: str
    known_items: frozenset[str]


@dataclass(frozen=True)
class VoiceConfig:
    """Thresholds. The values are assumptions to calibrate in E7."""

    min_confidence: float = 0.6
    guard_timeout_s: float = 2.0


@dataclass(frozen=True)
class VoiceOutcome:
    """What the pipeline decided. Nothing here is an order; execution needs a confirmation."""

    status: Status
    reason: str
    operator_id: str | None = None
    intent: VoiceIntent | None = None
    prompt: ReadBackPrompt | None = None
    item_id: str | None = None
    escalate: bool = False


def keyword_proposer(known: Collection[str]) -> Proposer:
    """A deterministic proposer. It maps keywords to the closed enum and never guesses.

    No keyword, or keywords for two different intents, give confidence 0, so the pipeline asks
    the operator to repeat. Item ids are those that ``resolve_items`` finds in the text.
    """
    catalog = frozenset(known)

    def propose(text: str) -> str:
        found = {_KEYWORDS[w] for w in _WORD.findall(text.lower()) if w in _KEYWORDS}
        intent = next(iter(found)) if len(found) == 1 else "status_query"
        confidence = _KEYWORD_CONFIDENCE if len(found) == 1 else 0.0
        items = sorted(resolve_items(text, catalog))[:5]
        payload = {"intent": intent, "item_ids": items, "zone_ids": [], "confidence": confidence}
        return json.dumps(payload)

    return propose


def _rejected(reason: str, session: OperatorSession, *, escalate: bool = False) -> VoiceOutcome:
    return VoiceOutcome("rejected", reason, session.operator_id, escalate=escalate)


def _consequential(
    intent: VoiceIntent, text: str, session: OperatorSession, order: TrustedOrder, prompt_id: str
) -> VoiceOutcome:
    named = resolve_items(text, order.known_items)
    if not named:
        return VoiceOutcome("repeat", "no_item", session.operator_id, intent)
    if len(named) > 1:
        return VoiceOutcome("repeat", "ambiguous_item", session.operator_id, intent)
    if not set(intent.item_ids) <= named:
        return VoiceOutcome("repeat", "item_mismatch", session.operator_id, intent)
    if named != {order.ordered_item}:
        return VoiceOutcome("rejected", "transcript_mismatch", session.operator_id, intent)
    prompt = start_readback(prompt_id, order.ordered_item, order.known_items)
    return VoiceOutcome(
        "awaiting_confirmation",
        intent.intent,
        session.operator_id,
        intent,
        prompt,
        order.ordered_item,
    )


async def process_transcript(
    transcript: str,
    session: OperatorSession,
    order: TrustedOrder,
    classifier: GuardClassifier,
    *,
    proposer: Proposer,
    config: VoiceConfig,
    prompt_id: str,
) -> VoiceOutcome:
    """Run one transcript through the pipeline. It never raises for untrusted input."""
    if not session.authenticated or not session.operator_id.strip():
        return VoiceOutcome("rejected", "unauthenticated")
    screened = await classify_input(
        transcript,
        UntrustedSource.VOICE_TRANSCRIPT,
        classifier,
        timeout_s=config.guard_timeout_s,
    )
    if screened.outcome is not GuardOutcome.PASS or screened.sanitized is None:
        return _rejected(f"screening:{screened.reason_code}", session, escalate=True)
    text = screened.sanitized.text
    try:
        intent = parse_voice_intent(proposer(text))
    except IntentError:
        return _rejected("intent_invalid", session)
    except Exception:
        _LOGGER.warning("voice_proposer_error")
        return _rejected("proposer_error", session)
    if intent.confidence < config.min_confidence:
        return VoiceOutcome("repeat", "low_confidence", session.operator_id, intent)
    if intent.intent in CONSEQUENTIAL:
        return _consequential(intent, text, session, order, prompt_id)
    return VoiceOutcome("accepted", intent.intent, session.operator_id, intent)


def authorize_execution(
    outcome: VoiceOutcome,
    confirmation: Confirmation | None,
    transcript: str,
    known: Collection[str],
) -> Decision:
    """Allow execution only for a waiting outcome and a matching typed confirmation."""
    if outcome.status != "awaiting_confirmation" or outcome.prompt is None:
        return Decision(False, "no_confirmation")
    return authorize(outcome.prompt, transcript, confirmation, known)
