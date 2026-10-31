"""Task progression, attempt fencing and bounded crash recovery are deterministic."""

from dataclasses import replace

import pytest

from waggle.coordination.task_model import (
    TaskCredential,
    TaskDefinition,
    TaskRecord,
    TaskState,
    advance_task,
    claim_task,
    recover_task,
    worker_transition,
)


def _approved(max_attempts: int = 3) -> TaskRecord:
    task = TaskRecord("task-1", max_attempts=max_attempts)
    for tick, target in enumerate((TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED)):
        task = advance_task(task, target, tick)
    return task


def test_task_needs_each_review_step_before_assignment() -> None:
    with pytest.raises(ValueError):
        advance_task(TaskRecord("task-1"), TaskState.APPROVED, 0)
    with pytest.raises(ValueError):
        claim_task(TaskRecord("task-1"), "worker-0", 0, 10)
    approved = _approved()
    claimed = claim_task(approved, "worker-0", 3, 10)
    assert claimed.state == TaskState.ASSIGNED
    assert claimed.attempt == 1 and claimed.token == 1 and claimed.expires_tick == 13
    assert approved.state == TaskState.APPROVED


def test_old_worker_cannot_finish_after_recovery_and_reassignment() -> None:
    old = claim_task(_approved(), "worker-0", 3, 2)
    recovered = recover_task(old, 5)
    assert recovered is not None and recovered.state == TaskState.APPROVED
    assert recovered.token == old.token
    new = claim_task(recovered, "worker-0", 6, 10)
    assert new.token == 2 and new.attempt == 2
    assert worker_transition(new, old.credential(), TaskState.EXECUTING, 6) is None
    started = worker_transition(new, new.credential(), TaskState.EXECUTING, 6)
    assert started is not None
    assert worker_transition(started, old.credential(), TaskState.DONE, 7) is None
    done = worker_transition(started, new.credential(), TaskState.DONE, 7)
    assert done is not None and done.state == TaskState.DONE
    with pytest.raises(ValueError):
        advance_task(done, TaskState.APPROVED, 8)


def test_expiry_is_exclusive_and_attempt_cap_stops_requeueing() -> None:
    task = claim_task(_approved(max_attempts=1), "worker-0", 3, 2)
    assert recover_task(task, 4) is None
    assert worker_transition(task, task.credential(), TaskState.EXECUTING, 5) is None
    failed = recover_task(task, 5)
    assert failed is not None and failed.state == TaskState.FAILED
    assert failed.worker_id is None and failed.expires_tick is None
    with pytest.raises(ValueError):
        claim_task(failed, "worker-1", 6, 2)


def test_completion_requires_start_and_exact_worker_and_token() -> None:
    task = claim_task(_approved(), "worker-0", 3, 10)
    assert worker_transition(task, task.credential(), TaskState.DONE, 4) is None
    wrong = TaskCredential(task.task_id, "worker-1", task.token)
    assert worker_transition(task, wrong, TaskState.EXECUTING, 4) is None
    future = TaskCredential(task.task_id, "worker-0", task.token + 1)
    assert worker_transition(task, future, TaskState.EXECUTING, 4) is None
    assert worker_transition(task, task.credential(), TaskState.EXECUTING, 2) is None


def test_task_definitions_reject_self_dependencies_duplicates_and_invalid_caps() -> None:
    for dependencies in (("task-1",), ("parent", "parent")):
        with pytest.raises(ValueError):
            TaskDefinition("task-1", dependencies=dependencies)
    for attempts in (0, 11, True):
        with pytest.raises(ValueError):
            TaskDefinition("task-1", max_attempts=attempts)
    assert TaskDefinition("task-1", dependencies=("z", "a")).dependencies == ("a", "z")


def test_task_record_rejects_inconsistent_ownership_and_backwards_time() -> None:
    with pytest.raises(ValueError):
        replace(_approved(), worker_id="worker-0")
    with pytest.raises(ValueError):
        advance_task(_approved(), TaskState.ABORTED, 1)
    with pytest.raises(ValueError):
        TaskRecord("bad id")
