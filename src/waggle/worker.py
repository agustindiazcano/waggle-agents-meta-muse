"""One bounded worker iteration with no transaction held across a handler call."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from waggle.coordination.task_model import TaskRecord
from waggle.db.tasks import TaskRepository

logger = logging.getLogger(__name__)


class WorkerStatus(StrEnum):
    """Outcome of one iteration; replay never runs the handler again."""

    IDLE = "idle"
    REPLAYED = "replayed"
    STALE = "stale"
    DONE = "done"
    FAILED = "failed"


class HandlerOutcome(StrEnum):
    """Explicit trusted-handler outcome; raw text and objects are never success."""

    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class WorkerResult:
    """One iteration's status and optional task id, without handler output or text."""

    status: WorkerStatus
    task_id: str | None = None


def _request_id(stage: str, request_id: str) -> str:
    return hashlib.sha256(f"{stage}:{request_id}".encode()).hexdigest()


def run_once(
    repository: TaskRepository,
    worker_id: str,
    request_id: str,
    now_tick: Callable[[], int],
    handler: Callable[[TaskRecord], HandlerOutcome],
    *,
    lease_ticks: int = 400,
) -> WorkerResult:
    """Claim, start and handle one task; errors fail closed and stale attempts cannot finish.

    The caller supplies trusted current ticks. A duplicate successful claim is
    returned as replayed without invoking the handler, including after a crash.
    Expired abandoned attempts are left for the separate bounded recovery sweep.
    """
    claimed = repository.claim(worker_id, request_id, now_tick(), lease_ticks=lease_ticks)
    if not claimed.accepted or claimed.task is None:
        return WorkerResult(WorkerStatus.IDLE)
    task = claimed.task
    if claimed.replayed:
        return WorkerResult(WorkerStatus.REPLAYED, task.task_id)
    credential = task.credential()
    started = repository.start(credential, _request_id("start", request_id), now_tick())
    if not started.accepted or started.task is None:
        return WorkerResult(WorkerStatus.STALE, task.task_id)
    if started.replayed:
        return WorkerResult(WorkerStatus.REPLAYED, task.task_id)
    try:
        outcome = handler(started.task)
    except Exception:
        # Never log untrusted handler output or exception text.
        logger.error("task_handler_failed", extra={"task_id": task.task_id})
        outcome = HandlerOutcome.FAILED
    if outcome is not HandlerOutcome.DONE:
        if outcome is not HandlerOutcome.FAILED:
            logger.error("task_handler_invalid_result", extra={"task_id": task.task_id})
        failed = repository.fail(credential, _request_id("fail", request_id), now_tick())
        status = WorkerStatus.FAILED if failed.accepted else WorkerStatus.STALE
        return WorkerResult(status, task.task_id)
    completed = repository.complete(credential, _request_id("complete", request_id), now_tick())
    status = WorkerStatus.DONE if completed.accepted else WorkerStatus.STALE
    return WorkerResult(status, task.task_id)
