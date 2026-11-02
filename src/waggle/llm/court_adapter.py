"""The court roles as plain model calls (ADR-005, ADR-017).

LLM calls live only in ``waggle.llm``. This adapter renders the versioned ``court-v1`` prompt
from a ``ReviewRequest``, builds a request id that makes a repeat come from the client cache,
and returns the raw model text. It does not parse or trust that text: the strict parser in
``waggle.governance.court_contract`` validates it and fails closed. Model ids come from the
routing table, never from this file.
"""

import asyncio
import hashlib
from collections.abc import Sequence
from pathlib import Path
from string import Template

from waggle.governance.court_contract import ReviewRequest
from waggle.governance.sanitizers import fence
from waggle.llm.client import LlmClient
from waggle.llm.models import LlmRequest

COURT_PROMPT_VERSION = "court-v1"
COURT_PROMPT_PATH = Path(__file__).with_name("court_v1.txt")
COURT_PROMPT_HASH = hashlib.sha256(COURT_PROMPT_PATH.read_bytes()).hexdigest()
COURT_ROLES = ("court_1", "court_2", "court_3")
_NO_EXCERPTS = "(none)"


def _check_role(role: str) -> None:
    if role not in COURT_ROLES:
        raise ValueError(f"{role!r} is not a court role")


def render_prompt(review: ReviewRequest) -> str:
    """Render the prompt file. Excerpts are fenced as data, trusted fields come from code."""
    excerpts = "\n".join(fence(e) for e in review.excerpts) or _NO_EXCERPTS
    template = Template(COURT_PROMPT_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        task=review.task,
        item_resolution=review.item_resolution,
        world_summary=review.world_summary,
        excerpts=excerpts,
    )


def court_request_id(role: str, review: ReviewRequest, repeat: int | None = None) -> str:
    """Request id of one reviewer for one request: same input, same id, so a repeat is cached.

    The digest covers the prompt file hash and the canonical request. An evaluation repeat
    appends ``-r<n>`` so that it is a real call.
    """
    _check_role(role)
    if repeat is not None and repeat < 0:
        raise ValueError("repeat must be >= 0")
    digest = hashlib.sha256(f"{COURT_PROMPT_HASH}\n{review.digest()}".encode()).hexdigest()
    base = f"court-{role}-{COURT_PROMPT_VERSION}-{digest}"
    return base if repeat is None else f"{base}-r{repeat}"


def build_llm_request(
    role: str, review: ReviewRequest, *, task_id: str | None = None, repeat: int | None = None
) -> LlmRequest:
    """Build the client request for one reviewer."""
    return LlmRequest(
        request_id=court_request_id(role, review, repeat),
        role=role,
        prompt=render_prompt(review),
        task_id=task_id,
    )


class CourtReviewer:
    """Calls the court roles through the shared client, so budget, retries and the call log
    apply."""

    prompt_version = COURT_PROMPT_VERSION
    prompt_hash = COURT_PROMPT_HASH

    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def request_id(self, role: str, review: ReviewRequest, repeat: int | None = None) -> str:
        """Request id this reviewer uses for a role and a request."""
        return court_request_id(role, review, repeat)

    def preflight(
        self,
        roles: Sequence[str],
        review: ReviewRequest,
        *,
        task_id: str | None = None,
        repeat: int | None = None,
    ) -> None:
        """Refuse the whole round, before any call, if the caps cannot cover every role."""
        self._client.preflight(
            [build_llm_request(r, review, task_id=task_id, repeat=repeat) for r in roles]
        )

    def ask(
        self,
        role: str,
        review: ReviewRequest,
        *,
        task_id: str | None = None,
        repeat: int | None = None,
    ) -> str:
        """Return the raw model text. Errors propagate and the caller counts no vote."""
        completion = self._client.call(
            build_llm_request(role, review, task_id=task_id, repeat=repeat)
        )
        return completion.text

    async def ask_async(
        self,
        role: str,
        review: ReviewRequest,
        *,
        task_id: str | None = None,
        repeat: int | None = None,
    ) -> str:
        """Same as ``ask`` without blocking the event loop."""
        return await asyncio.to_thread(self.ask, role, review, task_id=task_id, repeat=repeat)
