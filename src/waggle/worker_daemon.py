"""Worker polling loop with bounded recovery and cooperative shutdown."""

from collections.abc import Callable
from threading import Event

from waggle.db.tasks import TaskRepository
from waggle.worker import WorkerResult


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
