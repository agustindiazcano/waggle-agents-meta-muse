"""Worker polling loop with bounded recovery and cooperative shutdown."""

from collections.abc import Callable
from threading import Event
from uuid import uuid4

from waggle.coordination.task_model import TaskCredential, TaskRecord
from waggle.db.tasks import TaskRepository, TaskResult
from waggle.worker import HandlerOutcome, WorkerResult, run_once


def run_worker(
    repository: TaskRepository,
    worker_id: str,
    now_tick: Callable[[], int],
    request_id: Callable[[], str],
    stop: Event,
    pause: Callable[[float], object],
    run_iteration: Callable[[TaskRepository, str, str], WorkerResult],
    *,
    poll_seconds: float = 1.0,
    recovery_limit: int = 100,
    max_iterations: int | None = None,
) -> int:
    """Run recovery and one trusted iteration per poll until stopped.

    The caller supplies trusted ticks, unique request IDs and a stop-aware pause.
    Errors propagate to the supervisor; a failed sweep never falls through to claim.
    """
    if type(max_iterations) is not int and max_iterations is not None:
        raise ValueError("invalid iteration limit")
    if max_iterations is not None and max_iterations < 0:
        raise ValueError("invalid iteration limit")
    if type(poll_seconds) not in (int, float) or not 0 < poll_seconds <= 60:
        raise ValueError("invalid poll interval")
    if type(recovery_limit) is not int or not 1 <= recovery_limit <= 1000:
        raise ValueError("invalid recovery limit")
    count = 0
    while not stop.is_set() and (max_iterations is None or count < max_iterations):
        repository.recover(now_tick(), limit=recovery_limit)
        if stop.is_set():
            break
        run_iteration(repository, worker_id, request_id())
        count += 1
        if not stop.is_set() and (max_iterations is None or count < max_iterations):
            pause(poll_seconds)
    return count


def serve_worker(
    repository: TaskRepository,
    worker_id: str,
    now_tick: Callable[[], int],
    handler: Callable[[TaskRecord], HandlerOutcome],
    stop: Event,
    *,
    poll_seconds: float = 1.0,
    recovery_limit: int = 100,
    max_iterations: int | None = None,
    complete: Callable[[TaskCredential, str, int], TaskResult] | None = None,
) -> int:
    """Drive worker iterations with fresh request ids and interruptible waiting.

    The application must provide a shared trusted clock and a trusted handler.
    Process configuration, authentication and physical handoff remain separate.
    """

    def iteration(repo: TaskRepository, name: str, request: str) -> WorkerResult:
        return run_once(repo, name, request, now_tick, handler, complete=complete)

    return run_worker(
        repository,
        worker_id,
        now_tick,
        lambda: uuid4().hex,
        stop,
        stop.wait,
        iteration,
        poll_seconds=poll_seconds,
        recovery_limit=recovery_limit,
        max_iterations=max_iterations,
    )
