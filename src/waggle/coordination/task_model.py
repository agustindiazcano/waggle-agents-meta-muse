"""Pure task progression and bounded attempt recovery, without clocks or I/O."""

import re
from dataclasses import dataclass, replace
from enum import StrEnum

MAX_COUNTER = 2**63 - 1


def identifier(value: str) -> None:
    """Reject empty, oversized or non-identifier task, worker and request names."""
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value) is None:
        raise ValueError("invalid task, worker or request identifier")


def counter(value: int, minimum: int = 0, maximum: int = MAX_COUNTER) -> None:
    """Reject booleans, negative counters and values outside database integer bounds."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("invalid task counter or tick")


class TaskState(StrEnum):
    """Task lifecycle; only a live attempt may start or complete execution."""

    PENDING = "PENDING"
    SCREENED = "SCREENED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    ASSIGNED = "ASSIGNED"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


ACTIVE_STATES = frozenset((TaskState.ASSIGNED, TaskState.EXECUTING))


@dataclass(frozen=True)
class TaskDefinition:
    """Immutable queue metadata; dependencies must already exist when persisted."""

    task_id: str
    dependencies: tuple[str, ...] = ()
    max_attempts: int = 3
    priority: int = 0
    handoff_zone: str | None = None

    def __post_init__(self) -> None:
        identifier(self.task_id)
        counter(self.max_attempts, 1, 10)
        counter(self.priority, 0, 9)
        if self.handoff_zone is not None:
            identifier(self.handoff_zone)
        if (
            len(self.dependencies) > 32
            or len(set(self.dependencies)) != len(self.dependencies)
            or self.task_id in self.dependencies
        ):
            raise ValueError("invalid task dependencies")
        for dependency in self.dependencies:
            identifier(dependency)
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies)))


@dataclass(frozen=True)
class TaskCredential:
    """Task-scoped attempt credential, not an authenticated worker identity."""

    task_id: str
    worker_id: str
    token: int

    def __post_init__(self) -> None:
        identifier(self.task_id)
        identifier(self.worker_id)
        counter(self.token, 1)


@dataclass(frozen=True)
class TaskRecord:
    """Current state; attempt and token counters survive recovery and completion."""

    task_id: str
    state: TaskState = TaskState.PENDING
    attempt: int = 0
    token: int = 0
    worker_id: str | None = None
    expires_tick: int | None = None
    observed_tick: int = 0
    max_attempts: int = 3
    priority: int = 0

    def __post_init__(self) -> None:
        TaskDefinition(self.task_id, max_attempts=self.max_attempts, priority=self.priority)
        if not isinstance(self.state, TaskState):
            raise ValueError("invalid task state")
        counter(self.attempt, 0, self.max_attempts)
        counter(self.token)
        counter(self.observed_tick)
        if self.state in ACTIVE_STATES:
            if self.worker_id is None or self.expires_tick is None or self.attempt == 0:
                raise ValueError("active task requires an owner and expiry")
            identifier(self.worker_id)
            counter(self.token, 1)
            counter(self.expires_tick, self.observed_tick + 1)
        elif self.worker_id is not None or self.expires_tick is not None:
            raise ValueError("inactive task cannot retain attempt ownership")

    def credential(self) -> TaskCredential:
        """Return the stored credential; a caller must still check it at the effect."""
        if self.worker_id is None:
            raise ValueError("task has no active owner")
        return TaskCredential(self.task_id, self.worker_id, self.token)


def advance_task(task: TaskRecord, target: TaskState, now_tick: int) -> TaskRecord:
    """Advance one review step or terminate before assignment; never skip review."""
    counter(now_tick, task.observed_tick)
    next_state = {
        TaskState.PENDING: TaskState.SCREENED,
        TaskState.SCREENED: TaskState.REVIEWED,
        TaskState.REVIEWED: TaskState.APPROVED,
    }
    if task.state not in (*next_state, TaskState.APPROVED) or target not in (
        next_state.get(task.state),
        TaskState.REJECTED,
        TaskState.ESCALATED,
        TaskState.ABORTED,
    ):
        raise ValueError("invalid task review transition")
    if not isinstance(target, TaskState):
        raise ValueError("invalid task state")
    return replace(task, state=target, observed_tick=now_tick)


def claim_task(task: TaskRecord, worker_id: str, now_tick: int, lease_ticks: int) -> TaskRecord:
    """Assign an approved task and increment its durable attempt and token."""
    counter(now_tick, task.observed_tick)
    counter(lease_ticks, 1)
    identifier(worker_id)
    if task.state != TaskState.APPROVED or task.attempt >= task.max_attempts:
        raise ValueError("task is not eligible for assignment")
    return replace(
        task,
        state=TaskState.ASSIGNED,
        worker_id=worker_id,
        attempt=task.attempt + 1,
        token=task.token + 1,
        expires_tick=now_tick + lease_ticks,
        observed_tick=now_tick,
    )


def worker_transition(
    task: TaskRecord, credential: TaskCredential, target: TaskState, now_tick: int
) -> TaskRecord | None:
    """Return the next state only for the exact live attempt, otherwise deny."""
    counter(now_tick)
    if (
        task.task_id != credential.task_id
        or task.worker_id != credential.worker_id
        or task.token != credential.token
        or task.state not in ACTIVE_STATES
        or task.expires_tick is None
        or not task.observed_tick <= now_tick < task.expires_tick
    ):
        return None
    allowed = {
        TaskState.EXECUTING: (TaskState.ASSIGNED,),
        TaskState.DONE: (TaskState.EXECUTING,),
        TaskState.FAILED: (TaskState.ASSIGNED, TaskState.EXECUTING),
    }
    if not isinstance(target, TaskState) or task.state not in allowed.get(target, ()):
        return None
    return replace(
        task,
        state=target,
        observed_tick=now_tick,
        worker_id=task.worker_id if target == TaskState.EXECUTING else None,
        expires_tick=task.expires_tick if target == TaskState.EXECUTING else None,
    )


def recover_task(task: TaskRecord, now_tick: int) -> TaskRecord | None:
    """Requeue expired attempts up to their cap, then fail without releasing zones."""
    counter(now_tick)
    if task.state not in ACTIVE_STATES or task.expires_tick is None or now_tick < task.expires_tick:
        return None
    return replace(
        task,
        state=TaskState.APPROVED if task.attempt < task.max_attempts else TaskState.FAILED,
        worker_id=None,
        expires_tick=None,
        observed_tick=now_tick,
    )
