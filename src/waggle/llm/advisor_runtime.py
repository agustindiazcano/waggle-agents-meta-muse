"""Advisor runtime for local robot safety advisors (ADVISORS_DESIGN 5, 8, 14).

Builds snapshot requests, calls the LLM with the advisor role, parses cautions with the strict
schema, records accepted events in the caution log, and returns active speed limits.
Deterministic, safe degraded mode on outage, and strictly non-widening.
"""

import asyncio
import contextlib
import hashlib
import logging
import math
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Final, Literal

from waggle.governance.advisor_input import (
    AdvisorInputLimits,
    AdvisorInputRejected,
    InboundMessage,
    TrustedFacts,
    build_advisor_input,
)
from waggle.governance.caution import (
    CautionAction,
    CautionConfig,
    CautionEvent,
    CautionRejected,
    build_event,
    parse_advisor_output,
)
from waggle.governance.caution_limits import SpeedLimit, speed_limits_at
from waggle.governance.caution_log import CautionLog, LogRejected
from waggle.governance.classifier import GuardClassifier
from waggle.llm.client import LlmClient
from waggle.llm.errors import (
    BudgetExceededError,
    LlmError,
    ProviderError,
    ProviderTimeoutError,
)
from waggle.llm.models import Completion, LlmRequest

logger = logging.getLogger("waggle.llm.advisor")

ADVISOR_ROLE: Final = "advisor"
ADVISOR_PROMPT_VERSION: Final = "advisor-v1"
ADVISOR_PROMPT_PATH: Final = Path(__file__).with_name("advisor_v1.txt")
ADVISOR_PROMPT_HASH: Final = hashlib.sha256(ADVISOR_PROMPT_PATH.read_bytes()).hexdigest()


def _run_async[T](coro: Coroutine[object, object, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def advisor_request_id(robot_id: str, tick: int) -> str:
    """Build a deterministic request id derived from robot id and simulation tick."""
    return f"advisor-{robot_id}-{tick}"


def render_advisor_prompt(snapshot_text: str) -> str:
    """Render the versioned prompt template with the snapshot body."""
    template = Template(ADVISOR_PROMPT_PATH.read_text(encoding="utf-8"))
    return template.substitute(snapshot=snapshot_text)


AdvisorStatus = Literal[
    "accepted",
    "cached",
    "rejected",
    "rate_limited",
    "timeout",
    "budget_denied",
    "error",
    "oversize",
]


@dataclass(frozen=True)
class AdvisorResult:
    """Outcome of an advisor evaluation step. Any status but accepted or cached adds no caution."""

    status: AdvisorStatus
    limits: tuple[SpeedLimit, ...]
    event: CautionEvent | None = None
    reason: str | None = None
    request_id: str = ""
    cached: bool = False


class AdvisorRuntime:
    """Coordinates snapshot building, LLM execution, caution validation and event logging."""

    def __init__(
        self,
        client: LlmClient,
        caution_log: CautionLog,
        config: CautionConfig,
        timeout_s: float,
        max_response_chars: int,
        rate_limit_ticks: int,
        classifier: GuardClassifier,
        input_limits: AdvisorInputLimits,
    ) -> None:
        """Initialize with every limit and the classifier required. Nothing is defaulted, so
        untrusted text is never screened by an implicit always-benign classifier."""
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be finite and positive")
        if max_response_chars < 1:
            raise ValueError("max_response_chars must be positive")
        if rate_limit_ticks < 0:
            raise ValueError("rate_limit_ticks must be non-negative")
        self._client = client
        self._caution_log = caution_log
        self._config = config
        self._timeout_s = timeout_s
        self._max_response_chars = max_response_chars
        self._rate_limit_ticks = rate_limit_ticks
        self._classifier = classifier
        self._input_limits = input_limits
        self._served: set[str] = set()
        self._last_call_tick: dict[str, int] = {}
        self.last_rendered_prompt: str = ""

    def _call_client(
        self, request: LlmRequest
    ) -> tuple[Completion | None, AdvisorStatus | None, str | None]:
        # No ``with`` block: leaving it would wait for the worker thread and the timeout would
        # not bound the wait. The abandoned call finishes on its own and its result is dropped.
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

    def _record_unscored_signal(
        self, facts: TrustedFacts, tick: int, request_id: str, run_id: str, task_id: str
    ) -> None:
        unscored_event = CautionEvent(
            run_id=run_id,
            robot_id=facts.robot_id,
            issue_tick=tick,
            effective_tick=tick,
            expiry_tick=tick,
            action=CautionAction.ASK_ORGANIZER,
            speed_cap=None,
            code="unscored_input",
            call_request_id=f"{request_id}-unscored",
            validator_verdict="accepted",
        )
        with contextlib.suppress(LogRejected):
            self._caution_log.submit(unscored_event, owner_robot=facts.robot_id, task_id=task_id)

    def advise(
        self,
        facts: TrustedFacts,
        *,
        tick: int,
        current_cap: float,
        class_max: float,
        run_id: str,
        task_id: str,
        messages: list[InboundMessage] | None = None,
        latency_ticks: int = 0,
    ) -> AdvisorResult:
        """Run one advisor evaluation step, validating outputs and recording accepted cautions."""
        request_id = advisor_request_id(facts.robot_id, tick)
        active_limits = speed_limits_at(
            self._caution_log, facts.robot_id, tick, class_max=class_max
        )

        is_cached = request_id in self._served
        last_tick = self._last_call_tick.get(facts.robot_id)
        if not is_cached and last_tick is not None and (tick - last_tick) < self._rate_limit_ticks:
            return AdvisorResult(
                status="rate_limited",
                limits=active_limits,
                reason="too_soon",
                request_id=request_id,
            )

        try:
            advisor_input = _run_async(
                build_advisor_input(facts, messages or [], self._classifier, self._input_limits)
            )
        except AdvisorInputRejected as exc:
            return AdvisorResult(
                status="rejected",
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        if advisor_input.ask_code == "unscored_input":
            self._record_unscored_signal(facts, tick, request_id, run_id, task_id)

        prompt_text = render_advisor_prompt(advisor_input.prompt)
        self.last_rendered_prompt = prompt_text
        request = LlmRequest(
            request_id=request_id,
            role=ADVISOR_ROLE,
            prompt=prompt_text,
            task_id=task_id,
        )

        if not is_cached:
            self._last_call_tick[facts.robot_id] = tick

        completion, failure_status, failure_reason = self._call_client(request)
        if completion is not None:
            self._served.add(request_id)
        if completion is None:
            return AdvisorResult(
                status=failure_status or "error",
                limits=active_limits,
                reason=failure_reason,
                request_id=request_id,
            )

        if len(completion.text) > self._max_response_chars:
            return AdvisorResult(
                status="oversize",
                limits=active_limits,
                reason="too_long",
                request_id=request_id,
            )

        try:
            parsed = parse_advisor_output(
                completion.text,
                self._config,
                current_cap=current_cap,
                class_max=class_max,
            )
        except CautionRejected as exc:
            return AdvisorResult(
                status="rejected",
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        if parsed.action is CautionAction.NONE:
            return AdvisorResult(
                status="accepted",
                limits=active_limits,
                event=None,
                request_id=request_id,
                cached=is_cached,
            )

        try:
            event = build_event(
                parsed,
                run_id=run_id,
                robot_id=facts.robot_id,
                issue_tick=tick,
                latency_ticks=latency_ticks,
                request_id=request_id,
            )
        except CautionRejected as exc:
            return AdvisorResult(
                status="rejected",
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        if is_cached:
            updated_limits = speed_limits_at(
                self._caution_log, facts.robot_id, tick, class_max=class_max
            )
            return AdvisorResult(
                status="cached",
                limits=updated_limits,
                event=event,
                request_id=request_id,
                cached=True,
            )

        try:
            self._caution_log.submit(event, owner_robot=facts.robot_id, task_id=task_id)
        except LogRejected as exc:
            return AdvisorResult(
                status="rejected",
                limits=active_limits,
                reason=exc.code,
                request_id=request_id,
            )

        updated_limits = speed_limits_at(
            self._caution_log, facts.robot_id, tick, class_max=class_max
        )
        return AdvisorResult(
            status="accepted",
            limits=updated_limits,
            event=event,
            request_id=request_id,
        )
