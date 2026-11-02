"""E2 worker loop: claim, start, handler, complete, driven by the fault schedule.

The loop takes everything with an effect as an argument: the repository (anything with ``claim``,
``start`` and ``complete``), the clock, ``sleep`` and the kill switch. A test passes fakes; the
chaos runner passes the real repository, a shared monotonic clock and a kill that ends the process.
The module reads no environment, opens no connection and starts no process.

Faults are keyed as in ``waggle.experiments.e2_faults``: a kill by task and attempt, a clock jump
by worker and loop iteration, a replay by task. Request ids carry the worker, its incarnation and
the iteration, so a worker restarted after a kill never repeats an id of its earlier life. Clock
jumps apply to the first incarnation only, so a restart does not replay them.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from waggle.coordination.task_model import TaskCredential
from waggle.db.tasks import TaskResult
from waggle.experiments.e2_faults import FaultSchedule, KillPoint, ScheduleError
from waggle.experiments.e2_hooks import KillSwitch

EXIT_KILLED = 99
_TASK_ID = re.compile(r"t(\d{6})")


def task_id(index: int) -> str:
    """The identifier of the ``index``-th task of a run."""
    if type(index) is not int or not 0 <= index < 10**6:
        raise ScheduleError("task index out of range")
    return f"t{index:06d}"


def task_index(name: str) -> int:
    """The index of a task identifier made by ``task_id``; anything else is rejected."""
    match = _TASK_ID.fullmatch(name)
    if match is None:
        raise ScheduleError("not a task identifier of this harness")
    return int(match.group(1))


class TaskPort(Protocol):
    """The part of ``TaskRepository`` a worker uses."""

    def claim(
        self, worker_id: str, request_id: str, now_tick: int, lease_ticks: int = 400
    ) -> TaskResult:
        """Claim one eligible task."""
        ...

    def start(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        """Start the exact live attempt."""
        ...

    def complete(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        """Complete the exact live attempt."""
        ...


@dataclass(frozen=True)
class WorkerConfig:
    """One worker incarnation. ``handler_s`` and ``idle_s`` are seconds of real time."""

    worker: int
    incarnation: int
    horizon: int
    lease_ticks: int = 400
    handler_s: float = 0.02
    idle_s: float = 0.05

    def __post_init__(self) -> None:
        if self.worker < 0 or self.incarnation < 0:
            raise ScheduleError("worker and incarnation must not be negative")
        if self.horizon < 1 or self.lease_ticks < 1:
            raise ScheduleError("horizon and lease_ticks must be at least 1")
        if self.handler_s < 0 or self.idle_s < 0:
            raise ScheduleError("handler_s and idle_s must not be negative")


@dataclass
class WorkerStats:
    """Counts kept by one worker incarnation; the oracle, not these, judges the run."""

    iterations: int = 0
    claimed: int = 0
    started: int = 0
    completed: int = 0
    denied_start: int = 0
    denied_complete: int = 0
    replays_sent: int = 0
    replays_replayed: int = 0
    replays_applied: int = 0


@dataclass(frozen=True)
class _Pending:
    credential: TaskCredential
    request_id: str
    due: int


def _rid(config: WorkerConfig, iteration: int, step: str) -> str:
    return f"w{config.worker}-g{config.incarnation}-i{iteration}-{step}"


def _send_due_replays(
    pending: list[_Pending], repo: TaskPort, now: int, stats: WorkerStats
) -> None:
    for item in [p for p in pending if p.due <= now]:
        pending.remove(item)
        result = repo.complete(item.credential, item.request_id, now)
        stats.replays_sent += 1
        if result.replayed:
            stats.replays_replayed += 1
        elif result.accepted:
            stats.replays_applied += 1


def run_worker(
    config: WorkerConfig,
    repo: TaskPort,
    schedule: FaultSchedule,
    switch: KillSwitch,
    clock: Callable[[], int],
    sleep: Callable[[float], None],
    should_stop: Callable[[], bool],
) -> WorkerStats:
    """Run until ``should_stop`` or the horizon; a planned kill ends inside ``switch``."""
    stats = WorkerStats()
    worker_id = f"w{config.worker}"
    offset = 0
    pending: list[_Pending] = []
    iteration = 0
    while not should_stop():
        iteration += 1
        stats.iterations = iteration
        if config.incarnation == 0:
            offset += schedule.jump_for(config.worker, iteration)
        now = clock() + offset
        if now >= config.horizon:
            break
        _send_due_replays(pending, repo, now, stats)
        claimed = repo.claim(worker_id, _rid(config, iteration, "claim"), now, config.lease_ticks)
        if not claimed.accepted or claimed.task is None:
            sleep(config.idle_s)
            continue
        stats.claimed += 1
        credential = claimed.task.credential()
        index, attempt = task_index(credential.task_id), claimed.task.attempt
        switch.reach(KillPoint.AFTER_CLAIM, index, attempt)
        started = repo.start(credential, _rid(config, iteration, "start"), clock() + offset)
        if not started.accepted:
            stats.denied_start += 1
            continue
        stats.started += 1
        switch.reach(KillPoint.AFTER_START, index, attempt)
        if config.handler_s > 0:
            sleep(config.handler_s / 2)
        switch.reach(KillPoint.IN_HANDLER, index, attempt)
        if config.handler_s > 0:
            sleep(config.handler_s / 2)
        switch.reach(KillPoint.BEFORE_COMPLETE, index, attempt)
        complete_id = _rid(config, iteration, "complete")
        done_tick = clock() + offset
        done = repo.complete(credential, complete_id, done_tick)
        if not done.accepted:
            stats.denied_complete += 1
            continue
        stats.completed += 1
        replay = schedule.replay_for(index)
        if replay is not None:
            pending.append(_Pending(credential, complete_id, done_tick + replay.lag_ticks))
        switch.reach(KillPoint.AFTER_COMPLETE, index, attempt)
    return stats
