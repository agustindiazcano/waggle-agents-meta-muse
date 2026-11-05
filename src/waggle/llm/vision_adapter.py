"""Label reading through the ``vision`` role (ADR-099).

LLM calls live only in ``waggle.llm``. This adapter sends one image to the vision role and
returns the raw model text as a ``LabelRead``. It never raises for a model or budget failure: a
provider error, a call that would pass the cap, an empty reply and a bad request each come back
as an error code, so the caller treats the label as unknown and the process continues. The text
it returns is untrusted: it is parsed against ``vision-v1``, sanitized and screened by the guard,
and resolved against the package registry in code before anything uses it. The provider request
format is not assumed here; only the mock and scripted providers exist.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from waggle.llm.client import LlmClient
from waggle.llm.errors import BudgetExceededError, LlmError, ProviderError, TaskCapExceededError
from waggle.llm.models import Attachment, LlmRequest

VISION_PROMPT_VERSION = "vision-v1"
_PROMPT = (
    f"Prompt version: {VISION_PROMPT_VERSION}\n"
    "Read the attached package label image. Return only JSON with label_text, "
    "obstruction_class and legibility."
)
_LOGGER = logging.getLogger("waggle.llm")

LabelReadError = Literal["empty", "provider_error", "no_budget", "bad_request", "llm_error"]


@dataclass(frozen=True)
class LabelRead:
    """Exactly one of ``text`` and ``error`` is set. ``text`` is raw, untrusted model output."""

    text: str | None = None
    error: LabelReadError | None = None


def read_label(
    client: LlmClient, image: Attachment, request_id: str, *, task_id: str | None = None
) -> LabelRead:
    """Read ``image`` with the vision role; failures are returned, not raised."""
    if not request_id.strip() or image.kind != "image":
        return LabelRead(error="bad_request")
    request = LlmRequest(request_id, "vision", _PROMPT, task_id, (image,))
    try:
        completion = client.call(request)
    except (BudgetExceededError, TaskCapExceededError):
        return LabelRead(error="no_budget")
    except ProviderError:
        return LabelRead(error="provider_error")
    except LlmError:
        _LOGGER.warning("vision label read failed for request %s", request_id)
        return LabelRead(error="llm_error")
    text = completion.text.strip()
    return LabelRead(text=text) if text else LabelRead(error="empty")
