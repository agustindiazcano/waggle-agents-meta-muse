"""One court round: pre-checks, concurrent reviewers, post-checks and the round record.

The round only proposes. ``decide`` (unchanged, unanimity) turns the votes into a decision, and
every failure on the way fails closed: a timeout, an outage, an invalid answer, a budget denial,
a malformed composition or a failed record write all end in escalation, never in execution.
Pre-check failures spend nothing. Nothing here widens what code already allowed.
"""

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from waggle.governance.court import Decision, Verdict, decide
from waggle.governance.court_contract import ReviewRequest, Vote, vote_or_none
from waggle.llm.call_log import CallLog
from waggle.llm.errors import (
    BudgetExceededError,
    InvalidCapError,
    LlmError,
    ProviderError,
    ProviderTimeoutError,
    TaskCapExceededError,
)

_LOGGER = logging.getLogger(__name__)

Action = Literal["execute", "escalate", "deny"]


class Reviewer(Protocol):
    """What a round needs from the LLM side (implemented by ``waggle.llm.court_adapter``)."""

    prompt_version: str
    prompt_hash: str

    def request_id(self, role: str, review: ReviewRequest, repeat: int | None = None) -> str:
        """Request id for a role and a request."""
        ...

    def preflight(
        self,
        roles: Sequence[str],
        review: ReviewRequest,
        *,
        task_id: str | None = None,
        repeat: int | None = None,
    ) -> None:
        """Raise a typed error if the whole round cannot be afforded. Makes no call."""
        ...

    def ask(
        self,
        role: str,
        review: ReviewRequest,
        *,
        task_id: str | None = None,
        repeat: int | None = None,
    ) -> str:
        """Return the raw model text, or raise a typed LlmError."""
        ...


@dataclass(frozen=True)
class PreCheckFailure:
    """A deterministic check failed before any reviewer call."""

    action: Literal["deny", "escalate"]
    code: str


PreCheck = Callable[[], PreCheckFailure | None]
DecideFn = Callable[[Sequence[Verdict | None]], Decision]


@dataclass(frozen=True)
class MemberResult:
    """What one reviewer produced: a valid vote, or ``None`` with the cause."""

    role: str
    request_id: str
    vote: Vote | None
    cause: str | None
    model_id: str
    fallback_label: str | None


@dataclass(frozen=True)
class RoundRecord:
    """Everything needed to audit a round. ``decision`` is None when no round was held."""

    task_id: str | None
    action: Action
    decision: Decision | None
    reason: str
    members: tuple[MemberResult, ...]
    prompt_version: str
    prompt_hash: str
    review_digest: str
    held_out: bool


@dataclass(frozen=True)
class RoundResult:
    """The outcome of a round and its record."""

    action: Action
    record: RoundRecord


class RoundStore(Protocol):
    """Where round records go. A failed write must raise."""

    def write(self, record: RoundRecord) -> None:
        """Persist one record."""
        ...


class InMemoryRoundStore:
    """Round records kept in a list, for tests and local runs."""

    def __init__(self) -> None:
        self.records: list[RoundRecord] = []

    def write(self, record: RoundRecord) -> None:
        """Append one record."""
        self.records.append(record)


def check_composition(members: Sequence[MemberResult], roles: Sequence[str]) -> str | None:
    """Return ``"composition"`` unless members match the configured roles one to one.

    A forged or duplicated vote cannot count: roles and request ids must be distinct and the
    member roles must be exactly the configured ones.
    """
    ids = [m.request_id for m in members]
    well_formed = (
        len(roles) > 0
        and len(set(roles)) == len(roles)
        and [m.role for m in members] == list(roles)
        and all(ids)
        and len(set(ids)) == len(ids)
    )
    return None if well_formed else "composition"


def _cause(error: LlmError) -> str:
    if isinstance(error, ProviderTimeoutError):
        return "timeout"
    if isinstance(error, ProviderError):
        return "provider_error"
    if isinstance(error, BudgetExceededError | InvalidCapError):
        return "budget"
    if isinstance(error, TaskCapExceededError):
        return "task_cap"
    return "error"


def _collect(future: Future[str], done: bool) -> tuple[Vote | None, str | None]:
    if not done:
        return None, "timeout"
    error = future.exception()
    if error is None:
        vote = vote_or_none(future.result())
        return vote, None if vote else "parse_error"
    if isinstance(error, LlmError):
        return None, _cause(error)
    raise error


def _labels(call_log: CallLog, request_id: str) -> tuple[str, str | None]:
    for record in call_log.records():
        if record.request_id == request_id and record.status == "ok":
            return record.model_id, record.fallback_label
    return "", None


@dataclass(frozen=True)
class _Context:
    review: ReviewRequest
    reviewer: Reviewer
    task_id: str | None
    held_out: bool

    def ending(
        self,
        action: Action,
        reason: str,
        members: tuple[MemberResult, ...] = (),
        decision: Decision | None = None,
    ) -> RoundResult:
        record = RoundRecord(
            self.task_id,
            action,
            decision,
            reason,
            members,
            self.reviewer.prompt_version,
            self.reviewer.prompt_hash,
            self.review.digest(),
            self.held_out,
        )
        return RoundResult(action, record)


def _persist(store: RoundStore, result: RoundResult) -> RoundResult:
    """Write the record. A failed write turns execute into escalate (fail closed)."""
    try:
        store.write(result.record)
    except Exception:
        # Any store failure must block execution; the cause is logged, never the record text.
        _LOGGER.warning("round_record_write_failed", exc_info=True)
        if result.action == "execute":
            failed = replace(result.record, action="escalate", reason="record_write_failed")
            return RoundResult("escalate", failed)
    return result


def run_round(
    review: ReviewRequest,
    reviewer: Reviewer,
    roles: Sequence[str],
    *,
    store: RoundStore,
    call_log: CallLog,
    task_id: str | None,
    held_out: bool,
    deadline_s: float,
    pre_checks: Sequence[PreCheck] = (),
    repeat: int | None = None,
    decide_fn: DecideFn = decide,
) -> RoundResult:
    """Run one round for the configured ``roles`` and return the action and its record.

    Order: composition, pre-checks, all-or-nothing budget check, concurrent reviewers until
    ``deadline_s`` (a late answer is discarded), post-checks, ``decide``, record write.
    """
    if not deadline_s > 0:
        raise ValueError("deadline_s must be > 0")
    ctx = _Context(review, reviewer, task_id, held_out)
    if not roles or len(set(roles)) != len(roles):
        return _persist(store, ctx.ending("escalate", "composition"))
    for check in pre_checks:
        failure = check()
        if failure is not None:
            return _persist(store, ctx.ending(failure.action, failure.code))
    try:
        reviewer.preflight(roles, review, task_id=task_id, repeat=repeat)
    except LlmError as error:
        reason = "budget" if _cause(error) == "budget" else "config"
        return _persist(store, ctx.ending("escalate", reason))
    members = _run_members(ctx, roles, call_log, deadline_s, repeat)
    return _persist(store, _decide(ctx, members, roles, decide_fn))


def _run_members(
    ctx: _Context,
    roles: Sequence[str],
    call_log: CallLog,
    deadline_s: float,
    repeat: int | None,
) -> tuple[MemberResult, ...]:
    review, reviewer, task_id = ctx.review, ctx.reviewer, ctx.task_id
    pool = ThreadPoolExecutor(max_workers=len(roles))
    try:
        futures = [
            pool.submit(reviewer.ask, role, review, task_id=task_id, repeat=repeat)
            for role in roles
        ]
        done, _ = wait(futures, timeout=deadline_s)
        members = []
        for role, future in zip(roles, futures, strict=True):
            vote, cause = _collect(future, future in done)
            request_id = reviewer.request_id(role, review, repeat)
            model_id, label = _labels(call_log, request_id)
            if ctx.held_out and label is not None:
                vote, cause = None, "fallback_in_held_out"
            members.append(MemberResult(role, request_id, vote, cause, model_id, label))
        return tuple(members)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _decide(
    ctx: _Context, members: tuple[MemberResult, ...], roles: Sequence[str], decide_fn: DecideFn
) -> RoundResult:
    broken = check_composition(members, roles)
    votes: list[Verdict | None] = [m.vote.verdict if m.vote else None for m in members]
    decision = Decision.ESCALATE if broken else decide_fn(votes)
    if broken:
        reason = broken
    elif decision is Decision.EXECUTE:
        reason = "unanimous"
    elif any(v is None for v in votes):
        reason = "missing_vote"
    else:
        reason = "reject"
    action: Action = "execute" if decision is Decision.EXECUTE else "escalate"
    return ctx.ending(action, reason, members, decision)
