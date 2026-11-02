"""Transcription through the ``voice`` role (ADR-072).

LLM calls live only in ``waggle.llm``. This adapter sends one audio clip to the voice role and
returns the text as a ``Transcription``. It never raises for a model or budget failure: a provider
error, a call that would pass the cap, an empty transcript and a bad request id each come back as
an error code, so the caller falls back to text input and the process continues. The text it
returns is untrusted and goes to the sanitizer and the guard before anything else uses it. The
provider request format is not assumed here; only the mock and scripted providers exist.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from waggle.llm.client import LlmClient
from waggle.llm.errors import BudgetExceededError, LlmError, ProviderError, TaskCapExceededError
from waggle.llm.models import Attachment, LlmRequest

VOICE_PROMPT_VERSION = "voice-v1"
_PROMPT = (
    f"Prompt version: {VOICE_PROMPT_VERSION}\nTranscribe the attached audio. Return only the text."
)
_LOGGER = logging.getLogger("waggle.llm")

TranscriptionError = Literal["empty", "provider_error", "no_budget", "bad_request", "llm_error"]


@dataclass(frozen=True)
class Transcription:
    """Exactly one of ``text`` and ``error`` is set."""

    text: str | None = None
    error: TranscriptionError | None = None


def transcribe(
    client: LlmClient, clip: Attachment, request_id: str, *, task_id: str | None = None
) -> Transcription:
    """Transcribe ``clip`` with the voice role; failures are returned, not raised."""
    if not request_id.strip() or clip.kind != "audio":
        return Transcription(error="bad_request")
    request = LlmRequest(request_id, "voice", _PROMPT, task_id, (clip,))
    try:
        completion = client.call(request)
    except (BudgetExceededError, TaskCapExceededError):
        return Transcription(error="no_budget")
    except ProviderError:
        return Transcription(error="provider_error")
    except LlmError:
        _LOGGER.warning("voice transcription failed for request %s", request_id)
        return Transcription(error="llm_error")
    text = completion.text.strip()
    return Transcription(text=text) if text else Transcription(error="empty")
