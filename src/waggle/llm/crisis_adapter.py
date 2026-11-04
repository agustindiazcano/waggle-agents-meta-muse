"""The planner role as the crisis loop proposer (ADR-090).

LLM calls live only in ``waggle.llm``. This adapter renders the versioned ``planner-v1``
prompt from the trusted mission id and plan context, builds a request id that makes a
repeat come from the client cache, and returns the raw model text. It does not parse or
trust that text: ``waggle.validation.plan.parse_plan`` validates it and the crisis loop
only accepts a plan whose rollouts all pass. Feedback from the validator is passed as
data in the prompt, never as an instruction. The model id comes from the routing table
(the ``planner`` role), never from this file.
"""

import hashlib
import json
from pathlib import Path
from string import Template
from typing import Final

from waggle.llm.client import LlmClient
from waggle.llm.models import LlmRequest
from waggle.validation.plan import PlanContext

PLANNER_PROMPT_VERSION: Final = "planner-v1"
PLANNER_PROMPT_PATH: Final = Path(__file__).with_name("planner_v1.txt")
PLANNER_PROMPT_HASH: Final = hashlib.sha256(PLANNER_PROMPT_PATH.read_bytes()).hexdigest()
PLANNER_ROLE: Final = "planner"
_NO_FEEDBACK: Final = "(none)"


def _canonical(mission_id: str, context: PlanContext, feedback: str | None) -> str:
    body = {
        "mission": mission_id,
        "robots": sorted(context.robot_max_speed_mps.items()),
        "items": sorted(context.items),
        "zones": sorted(context.zones),
        "feedback": feedback,
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def render_prompt(mission_id: str, context: PlanContext, feedback: str | None) -> str:
    """Render the prompt file. Trusted ids come from the context; feedback is data."""
    robots = ", ".join(
        f"{robot} (max {speed:g} m/s)"
        for robot, speed in sorted(context.robot_max_speed_mps.items())
    )
    template = Template(PLANNER_PROMPT_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        mission=mission_id,
        robots=robots or _NO_FEEDBACK,
        items=", ".join(sorted(context.items)) or _NO_FEEDBACK,
        zones=", ".join(sorted(context.zones)) or _NO_FEEDBACK,
        feedback=feedback if feedback is not None else _NO_FEEDBACK,
    )


def planner_request_id(mission_id: str, context: PlanContext, feedback: str | None) -> str:
    """Request id of one proposal: same mission, context and feedback, same id.

    The digest covers the prompt file hash and the canonical inputs, so a repeat of the
    same round is served from the client cache and a new feedback round is a real call.
    """
    digest = hashlib.sha256(
        f"{PLANNER_PROMPT_HASH}\n{_canonical(mission_id, context, feedback)}".encode()
    ).hexdigest()
    return f"planner-{PLANNER_PROMPT_VERSION}-{digest}"


def build_llm_request(
    mission_id: str,
    context: PlanContext,
    feedback: str | None,
    *,
    task_id: str | None = None,
) -> LlmRequest:
    """Build the client request for one proposal round."""
    return LlmRequest(
        request_id=planner_request_id(mission_id, context, feedback),
        role=PLANNER_ROLE,
        prompt=render_prompt(mission_id, context, feedback),
        task_id=task_id,
    )


class LlmPlanProposer:
    """Proposes plans through the shared client, so budget, retries and the call log apply.

    Satisfies the ``PlanProposer`` protocol of ``waggle.validation.crisis_loop`` without
    that package importing this one. Errors propagate: the loop counts the round as a
    proposer error and escalates after the round bound.
    """

    prompt_version = PLANNER_PROMPT_VERSION
    prompt_hash = PLANNER_PROMPT_HASH

    def __init__(
        self,
        client: LlmClient,
        *,
        mission_id: str,
        context: PlanContext,
        task_id: str | None = None,
    ) -> None:
        if not mission_id:
            raise ValueError("mission_id must not be empty")
        self._client = client
        self._mission_id = mission_id
        self._context = context
        self._task_id = task_id

    def propose(self, feedback: str | None) -> str:
        """Return the raw model text for one round. Errors propagate to the loop."""
        completion = self._client.call(
            build_llm_request(self._mission_id, self._context, feedback, task_id=self._task_id)
        )
        return completion.text
