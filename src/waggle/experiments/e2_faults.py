"""E2 fault schedule: a pure, seeded plan of the faults the chaos harness injects.

Nothing here touches a database, a process, a clock or the global random stream. The schedule is a
function of the seed and the parameters, so the same inputs give the same plan (AGENTS.md 5.5).
Each fault family draws from its own stream, derived from the seed and a family name, so changing
one rate does not reshuffle the others. Faults are keyed by task index and attempt number, by
worker and loop iteration, or by worker and database call number, never by which worker happens to
claim a task, so the plan does not depend on operating system scheduling. Whether the run that
follows is deterministic is a separate matter (``docs/E2_CHAOS_DESIGN.md``).

The parameter defaults are assumptions to calibrate on development seeds. A kill planned for an
attempt that never happens (the task finished earlier) is simply not applied by the runner.
"""

import random
from dataclasses import dataclass
from enum import Enum


class ScheduleError(ValueError):
    """The parameters or a lookup are invalid; no schedule is built."""


class KillPoint(Enum):
    """Where a worker process is killed, in the order of the task lifecycle."""

    AFTER_CLAIM = "after_claim"
    AFTER_START = "after_start"
    IN_HANDLER = "in_handler"
    BEFORE_COMPLETE = "before_complete"
    AFTER_COMPLETE = "after_complete"


class ReplayMode(Enum):
    """When a duplicate delivery of an old request arrives."""

    DURING_RECOVERY = "during_recovery"
    AFTER_RECOVERY = "after_recovery"


@dataclass(frozen=True)
class FaultParams:
    """Sizes and rates of one run. Rates are fractions of tasks, except ``delay_rate``."""

    workers: int = 8
    tasks: int = 500
    horizon: int = 20000
    kill_rate: float = 0.2
    max_kills_per_task: int = 2
    clock_jumps_per_worker: int = 2
    worker_iterations: int = 200
    jump_ticks_min: int = 50
    jump_ticks_max: int = 2000
    replay_rate: float = 0.1
    replay_lag_max: int = 500
    delay_rate: float = 0.05
    delay_ms_max: int = 200


@dataclass(frozen=True)
class Kill:
    """Kill the process that runs attempt ``attempt`` (from 1) of a task at ``point``."""

    task_index: int
    attempt: int
    point: KillPoint


@dataclass(frozen=True)
class ClockJump:
    """Move the clock of a worker forward by ``ticks`` at its ``iteration``-th loop pass."""

    worker: int
    iteration: int
    ticks: int


@dataclass(frozen=True)
class Replay:
    """Send an old request again, with its old request id and credential."""

    task_index: int
    mode: ReplayMode
    lag_ticks: int


@dataclass(frozen=True)
class DbDelay:
    """Sleep times around one database transaction, in milliseconds."""

    before_ms: int
    commit_ms: int


@dataclass(frozen=True)
class FaultSchedule:
    """The plan for one run: tables for kills, jumps and replays; delays derive from the seed."""

    seed: int
    params: FaultParams
    kills: tuple[Kill, ...]
    jumps: tuple[ClockJump, ...]
    replays: tuple[Replay, ...]

    def kill_for(self, task_index: int, attempt: int) -> KillPoint | None:
        """Kill point planned for this attempt of this task, or None."""
        for kill in self.kills:
            if kill.task_index == task_index and kill.attempt == attempt:
                return kill.point
        return None

    def jump_for(self, worker: int, iteration: int) -> int:
        """Ticks the clock of this worker jumps at this iteration; zero when none."""
        return sum(j.ticks for j in self.jumps if j.worker == worker and j.iteration == iteration)

    def replay_for(self, task_index: int) -> Replay | None:
        """Replay planned for this task, or None."""
        for replay in self.replays:
            if replay.task_index == task_index:
                return replay
        return None

    def summary(self) -> dict[str, object]:
        """Counts of planned faults, for the result file."""
        by_point = {point.value: 0 for point in KillPoint}
        for kill in self.kills:
            by_point[kill.point.value] += 1
        by_mode = {mode.value: 0 for mode in ReplayMode}
        for replay in self.replays:
            by_mode[replay.mode.value] += 1
        return {
            "seed": self.seed,
            "kills": len(self.kills),
            "kills_by_point": by_point,
            "killed_tasks": len({kill.task_index for kill in self.kills}),
            "clock_jumps": len(self.jumps),
            "replays": len(self.replays),
            "replays_by_mode": by_mode,
        }


def _validate(p: FaultParams) -> None:
    positive = {"workers": p.workers, "tasks": p.tasks, "horizon": p.horizon}
    positive |= {"max_kills_per_task": p.max_kills_per_task}
    positive |= {"worker_iterations": p.worker_iterations, "jump_ticks_min": p.jump_ticks_min}
    positive |= {"replay_lag_max": p.replay_lag_max}
    for name, value in positive.items():
        if value < 1:
            raise ScheduleError(f"{name} must be at least 1")
    if p.clock_jumps_per_worker < 0 or p.delay_ms_max < 0:
        raise ScheduleError("clock_jumps_per_worker and delay_ms_max must not be negative")
    if p.jump_ticks_max < p.jump_ticks_min:
        raise ScheduleError("jump_ticks_max must not be below jump_ticks_min")
    for name, rate in (("kill_rate", p.kill_rate), ("replay_rate", p.replay_rate)):
        if not 0.0 <= rate <= 1.0:
            raise ScheduleError(f"{name} must be between 0 and 1")
    if not 0.0 <= p.delay_rate <= 1.0:
        raise ScheduleError("delay_rate must be between 0 and 1")


def _stream(seed: int, family: str) -> random.Random:
    return random.Random(f"e2-faults:{seed}:{family}")


def _kills(seed: int, p: FaultParams) -> tuple[Kill, ...]:
    rng = _stream(seed, "kills")
    chosen = sorted(rng.sample(range(p.tasks), round(p.kill_rate * p.tasks)))
    kills: list[Kill] = []
    for task_index in chosen:
        for attempt in range(1, rng.randint(1, p.max_kills_per_task) + 1):
            kills.append(Kill(task_index, attempt, rng.choice(list(KillPoint))))
    return tuple(kills)


def _jumps(seed: int, p: FaultParams) -> tuple[ClockJump, ...]:
    rng = _stream(seed, "jumps")
    return tuple(
        ClockJump(
            worker,
            rng.randint(1, p.worker_iterations),
            rng.randint(p.jump_ticks_min, p.jump_ticks_max),
        )
        for worker in range(p.workers)
        for _ in range(p.clock_jumps_per_worker)
    )


def _replays(seed: int, p: FaultParams) -> tuple[Replay, ...]:
    rng = _stream(seed, "replays")
    chosen = sorted(rng.sample(range(p.tasks), round(p.replay_rate * p.tasks)))
    replays: list[Replay] = []
    for task_index in chosen:
        mode = rng.choice(list(ReplayMode))
        lag = 0 if mode is ReplayMode.DURING_RECOVERY else rng.randint(1, p.replay_lag_max)
        replays.append(Replay(task_index, mode, lag))
    return tuple(replays)


def build_schedule(seed: int, params: FaultParams) -> FaultSchedule:
    """Build the fault plan for one run; invalid parameters raise ``ScheduleError``."""
    _validate(params)
    return FaultSchedule(
        seed, params, _kills(seed, params), _jumps(seed, params), _replays(seed, params)
    )


def db_delay(schedule: FaultSchedule, worker: int, call_index: int) -> DbDelay:
    """Delay for the ``call_index``-th database transaction of a worker, pure in its arguments."""
    p = schedule.params
    if not 0 <= worker < p.workers or call_index < 0:
        raise ScheduleError("worker or call index out of range")
    rng = _stream(schedule.seed, f"delay:{worker}:{call_index}")
    if rng.random() >= p.delay_rate:
        return DbDelay(0, 0)
    return DbDelay(rng.randint(0, p.delay_ms_max), rng.randint(0, p.delay_ms_max))
