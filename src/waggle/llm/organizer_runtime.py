"""Organizer runtime for per-robot task organization (ADVISORS_DESIGN 6, 8, 9, 14).

Builds screened organizer context, calls the LLM with the ``organizer`` role, validates output
against the strict organizer schema, enforces per-task turn/message/loop limits, records yield
holds in the caution log, and forwards tool calls through an injected MCP dispatch port under the
robot's own authenticated identity. Degrades safely on timeout, budget denial or provider error.
"""

import asyncio
import hashlib
import logging
import math
from collections.abc import Coroutine, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, replace
from pathlib import Path
from string import Template
from typing import Final, Literal, Protocol

from waggle.governance.advisor_input import InboundMessage, TrustedFacts
from waggle.governance.caution import (
    CautionAction,
    CautionConfig,
    CautionEvent,
    CautionRejected,
    ParsedCaution,
    build_event,
)
from waggle.governance.caution_limits import SpeedLimit, speed_limits_at
from waggle.governance.caution_log import CautionLog, LogRejected
from waggle.governance.classifier import GuardClassifier
from waggle.governance.organizer import (
    ArgScalar,
    OrganizerAction,
    OrganizerLimits,
    OrganizerRejected,
    OrganizerTaskState,
    ParsedOrganizerDecision,
    build_organizer_input,
    check_turn_allowed,
    outbound_message_json,
    parse_organizer_output,
    record_decision,
)
from waggle.llm.client import LlmClient
from waggle.llm.errors import (
    BudgetExceededError,
    LlmError,
    ProviderError,
    ProviderTimeoutError,
)
from waggle.llm.models import Completion, LlmRequest

logger = logging.getLogger("waggle.llm.organizer")

ORGANIZER_ROLE: Final = "organizer"
ORGANIZER_PROMPT_VERSION: Final = "organizer-v1"
ORGANIZER_PROMPT_PATH: Final = Path(__file__).with_name("organizer_v1.txt")
ORGANIZER_PROMPT_HASH: Final = hashlib.sha256(ORGANIZER_PROMPT_PATH.read_bytes()).hexdigest()


def _run_async[T](coro: Coroutine[object, object, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def organizer_request_id(robot_id: str, tick: int) -> str:
    """Build a deterministic request id derived from robot id and simulation tick."""
    return f"organizer-{robot_id}-{tick}"


def render_organizer_prompt(context_text: str) -> str:
    """Render the versioned organizer prompt template with the context body."""
    template = Template(ORGANIZER_PROMPT_PATH.read_text(encoding="utf-8"))
    return template.substitute(context=context_text)


class McpToolDispatch(Protocol):
    """Port for forwarding an organizer tool call under the robot's authenticated identity."""

    def call_tool(
        self,
        *,
        robot_id: str,
        tool: str,
        arguments: Mapping[str, ArgScalar],
        request_id: str,
    ) -> Mapping[str, object]:
        """Dispatch ``tool`` for ``robot_id``; raise on boundary or backend failure."""
        ...


OrganizerStatus = Literal[
    "accepted",
    "cached",
    "rejected",
    "rate_limited",
    "timeout",
    "budget_denied",
    "error",
    "oversize",
    "tool_error",
]


@dataclass(frozen=True)
class OrganizerResult:
    """Outcome of one organizer evaluation step."""

    status: OrganizerStatus
    limits: tuple[SpeedLimit, ...]
    decision: ParsedOrganizerDecision | None = None
    hold_event: CautionEvent | None = None
    outbound_message: str | None = None
    tool_outcome: Mapping[str, object] | None = None
    reason: str | None = None
    request_id: str = ""
    cached: bool = False


class OrganizerRuntime:
    """Coordinates organizer context screening, LLM call, loop/turn checks and tool/hold actions."""

    def __init__(
        self,
        client: LlmClient,
        caution_log: CautionLog,
        caution_config: CautionConfig,
        limits: OrganizerLimits,
        timeout_s: float,
        max_response_chars: int,
        max_messages: int,
        classifier: GuardClassifier,
        tool_dispatch: McpToolDispatch | None = None,
    ) -> None:
        """Initialize with all bounds and the classifier required."""
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        if max_response_chars < 1:
            raise ValueError("max_response_chars must be positive")
        if max_messages < 1:
            raise ValueError("max_messages must be positive")
        self._client = client
        self._caution_log = caution_log
        self._caution_config = caution_config
        self._limits = limits
        self._timeout_s = timeout_s
        self._max_response_chars = max_response_chars
        self._max_messages = max_messages
        self._classifier = classifier
        self._tool_dispatch = tool_dispatch
        self._states: dict[tuple[str, str], OrganizerTaskState] = {}
        self._cached_results: dict[str, OrganizerResult] = {}
        self._outbound_messages: list[tuple[str, str, str]] = []
        self.last_rendered_prompt: str = ""

    @property
    def outbound_messages(self) -> tuple[tuple[str, str, str], ...]:
        """Recorded outbound messages as (sender, recipient, raw_json)."""
        return tuple(self._outbound_messages)

    def _call_client(
        self, request: LlmRequest
    ) -> tuple[Completion | None, OrganizerStatus | None, str | None]:
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            completion = pool.submit(self._client.call, request).result(timeout=self._timeout_s)
            return completion, None, None
        except (FutureTimeout, ProviderTimeoutError):
            return None, "timeout", "timeout"
        except BudgetExceededError as err:
            return None, "budget_denied", str(err)
        except ProviderError as err:
            return None, "error", str(err)
        except LlmError as err:
            return None, "error", str(err)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def organize(
        self,
        facts: TrustedFacts,
        *,
        tick: int,
        class_max: float,
        run_id: str,
        task_id: str,
        ask_signals: tuple[str, ...] = (),
        messages: list[InboundMessage] | None = None,
        latency_ticks: int = 0,
    ) -> OrganizerResult:
        """Run one organizer evaluation step with strict schema, loop and boundary checks."""
        request_id = organizer_request_id(facts.robot_id, tick)
        active_limits = speed_limits_at(
            self._caution_log, facts.robot_id, tick, class_max=class_max
        )

        if request_id in self._cached_results:
            prev = self._cached_results[request_id]
            return replace(prev, status="cached", limits=active_limits, cached=True)

        state = self._states.setdefault((facts.robot_id, task_id), OrganizerTaskState())
        try:
            check_turn_allowed(self._limits, state, now_tick=tick)
        except OrganizerRejected as exc:
            status: OrganizerStatus = "rate_limited" if exc.code == "too_soon" else "rejected"
            return OrganizerResult(
                status=status,
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        try:
            org_input = _run_async(
                build_organizer_input(
                    facts,
                    messages or [],
                    ask_signals,
                    self._classifier,
                    self._limits,
                    max_messages=self._max_messages,
                )
            )
        except OrganizerRejected as exc:
            return OrganizerResult(
                status="rejected",
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        prompt_text = render_organizer_prompt(org_input.prompt)
        self.last_rendered_prompt = prompt_text
        llm_request = LlmRequest(
            request_id=request_id,
            role=ORGANIZER_ROLE,
            prompt=prompt_text,
            task_id=task_id,
        )

        completion, failure_status, failure_reason = self._call_client(llm_request)
        if completion is None:
            state.turns += 1
            state.last_tick = tick
            return OrganizerResult(
                status=failure_status or "error",
                limits=active_limits,
                reason=failure_reason,
                request_id=request_id,
            )

        if len(completion.text) > self._max_response_chars:
            state.turns += 1
            state.last_tick = tick
            return OrganizerResult(
                status="oversize",
                limits=active_limits,
                reason="too_long",
                request_id=request_id,
            )

        try:
            decision = parse_organizer_output(
                completion.text, self._limits, owner_robot=facts.robot_id
            )
            record_decision(self._limits, state, decision, now_tick=tick)
        except OrganizerRejected as exc:
            state.turns += 1
            state.last_tick = tick
            return OrganizerResult(
                status="rejected",
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        if decision.action is OrganizerAction.NONE:
            res = OrganizerResult(
                status="accepted",
                limits=active_limits,
                decision=decision,
                request_id=request_id,
            )
            self._cached_results[request_id] = res
            return res

        if decision.action is OrganizerAction.YIELD_HOLD:
            try:
                event = build_event(
                    ParsedCaution(CautionAction.HOLD, 0.0, decision.duration_ticks, None),
                    run_id=run_id,
                    robot_id=facts.robot_id,
                    issue_tick=tick,
                    latency_ticks=latency_ticks,
                    request_id=request_id,
                )
                self._caution_log.submit(event, owner_robot=facts.robot_id, task_id=task_id)
            except (CautionRejected, LogRejected) as exc:
                return OrganizerResult(
                    status="rejected",
                    limits=active_limits,
                    reason=exc.code,
                    request_id=request_id,
                )
            updated_limits = speed_limits_at(
                self._caution_log, facts.robot_id, tick, class_max=class_max
            )
            res = OrganizerResult(
                status="accepted",
                limits=updated_limits,
                decision=decision,
                hold_event=event,
                request_id=request_id,
            )
            self._cached_results[request_id] = res
            return res

        if decision.action is OrganizerAction.SEND_MESSAGE:
            msg_json = outbound_message_json(decision, owner_robot=facts.robot_id)
            assert decision.recipient is not None
            self._outbound_messages.append((facts.robot_id, decision.recipient, msg_json))
            res = OrganizerResult(
                status="accepted",
                limits=active_limits,
                decision=decision,
                outbound_message=msg_json,
                request_id=request_id,
            )
            self._cached_results[request_id] = res
            return res

        # CALL_TOOL
        assert decision.tool is not None
        if self._tool_dispatch is None:
            return OrganizerResult(
                status="tool_error",
                limits=active_limits,
                decision=decision,
                reason="tool_unavailable",
                request_id=request_id,
            )
        try:
            outcome = self._tool_dispatch.call_tool(
                robot_id=facts.robot_id,
                tool=decision.tool,
                arguments=decision.arguments_dict(),
                request_id=request_id,
            )
        except Exception as exc:
            logger.warning("organizer tool dispatch failed: %s", type(exc).__name__)
            return OrganizerResult(
                status="tool_error",
                limits=active_limits,
                decision=decision,
                reason="tool_dispatch_failed",
                request_id=request_id,
            )
        res = OrganizerResult(
            status="accepted",
            limits=active_limits,
            decision=decision,
            tool_outcome=outcome,
            request_id=request_id,
        )
        self._cached_results[request_id] = res
        return res
