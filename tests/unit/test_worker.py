"""One worker step never invokes a handler after a replay or a rejected start."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from waggle.coordination.task_model import TaskRecord, TaskState
from waggle.db.tasks import TaskRepository, TaskResult
from waggle.worker import HandlerOutcome, WorkerStatus, run_once


def _assigned() -> TaskRecord:
    return TaskRecord(
        "task-1", TaskState.ASSIGNED, attempt=1, token=1, worker_id="worker-0", expires_tick=10
    )


def test_replayed_claim_does_not_repeat_a_handler() -> None:
    repository = MagicMock(spec=TaskRepository)
    repository.claim.return_value = TaskResult(True, _assigned(), replayed=True)
    handler = MagicMock()
    result = run_once(repository, "worker-0", "request-1", lambda: 0, handler)
    assert result.status == WorkerStatus.REPLAYED
    handler.assert_not_called()
    repository.start.assert_not_called()


def test_rejected_start_stops_before_handler() -> None:
    repository = MagicMock(spec=TaskRepository)
    repository.claim.return_value = TaskResult(True, _assigned())
    repository.start.return_value = TaskResult(False, _assigned())
    handler = MagicMock()
    result = run_once(repository, "worker-0", "request-1", lambda: 0, handler)
    assert result.status == WorkerStatus.STALE
    handler.assert_not_called()
    repository.complete.assert_not_called()


def test_handler_failure_is_logged_without_its_text_and_marks_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = MagicMock(spec=TaskRepository)
    repository.claim.return_value = TaskResult(True, _assigned())
    executing = replace(_assigned(), state=TaskState.EXECUTING)
    repository.start.return_value = TaskResult(True, executing)
    failed = replace(executing, state=TaskState.FAILED, worker_id=None, expires_tick=None)
    repository.fail.return_value = TaskResult(True, failed)
    handler = MagicMock(side_effect=RuntimeError("private-input-must-not-be-logged"))
    result = run_once(repository, "worker-0", "request-1", lambda: 0, handler)
    assert result.status == WorkerStatus.FAILED
    assert "task_handler_failed" in caplog.text
    assert "private-input-must-not-be-logged" not in caplog.text
    repository.complete.assert_not_called()


def test_no_available_task_is_idle() -> None:
    repository = MagicMock(spec=TaskRepository)
    repository.claim.return_value = TaskResult(False)
    handler = MagicMock()
    result = run_once(repository, "worker-0", "request-1", lambda: 0, handler)
    assert result.status == WorkerStatus.IDLE and result.task_id is None
    handler.assert_not_called()


def test_untyped_handler_result_cannot_complete_a_task() -> None:
    repository = MagicMock(spec=TaskRepository)
    assigned = _assigned()
    repository.claim.return_value = TaskResult(True, assigned)
    repository.start.return_value = TaskResult(True, replace(assigned, state=TaskState.EXECUTING))
    failed = replace(assigned, state=TaskState.FAILED, worker_id=None, expires_tick=None)
    repository.fail.return_value = TaskResult(True, failed)
    handler = MagicMock(return_value={"status": "done"})
    result = run_once(repository, "worker-0", "request-1", lambda: 0, handler)
    assert result.status == WorkerStatus.FAILED
    repository.complete.assert_not_called()


def test_a_custom_completion_replaces_ordinary_completion() -> None:
    repository = MagicMock(spec=TaskRepository)
    repository.claim.return_value = TaskResult(True, _assigned())
    started = replace(_assigned(), state=TaskState.EXECUTING)
    repository.start.return_value = TaskResult(True, started)
    finish = MagicMock(return_value=TaskResult(True, started))
    result = run_once(
        repository,
        "worker-0",
        "request-1",
        lambda: 3,
        lambda task: HandlerOutcome.DONE,
        complete=finish,
    )
    assert result.status == WorkerStatus.DONE
    finish.assert_called_once()
    repository.complete.assert_not_called()


def test_a_refused_custom_completion_is_stale_not_done() -> None:
    repository = MagicMock(spec=TaskRepository)
    repository.claim.return_value = TaskResult(True, _assigned())
    repository.start.return_value = TaskResult(
        True, replace(_assigned(), state=TaskState.EXECUTING)
    )
    result = run_once(
        repository,
        "worker-0",
        "request-1",
        lambda: 3,
        lambda task: HandlerOutcome.DONE,
        complete=lambda credential, request, tick: TaskResult(False, None),
    )
    assert result.status == WorkerStatus.STALE
