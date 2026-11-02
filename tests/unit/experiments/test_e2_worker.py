"""E2 worker loop: claim, start, handler, complete with kill points, clock jumps and replays."""

from collections.abc import Callable
from dataclasses import replace

import pytest

from waggle.coordination.task_model import (
    TaskCredential,
    TaskRecord,
    TaskState,
    claim_task,
    worker_transition,
)
from waggle.db.tasks import TaskResult
from waggle.experiments.e2_faults import (
    ClockJump,
    FaultParams,
    FaultSchedule,
    Kill,
    KillPoint,
    Replay,
    ReplayMode,
    ScheduleError,
    build_schedule,
)
from waggle.experiments.e2_hooks import KillSwitch
from waggle.experiments.e2_worker import (
    WorkerConfig,
    WorkerStats,
    run_worker,
    task_id,
    task_index,
)

PARAMS = FaultParams(
    workers=2,
    tasks=4,
    horizon=1000,
    kill_rate=0.0,
    clock_jumps_per_worker=0,
    replay_rate=0.0,
    delay_rate=0.0,
)
CONFIG = WorkerConfig(worker=0, incarnation=0, horizon=1000, lease_ticks=400, handler_s=0.0)


class Killed(Exception):
    """Raised by the fake kill so a test can stop the loop where the process would end."""


class FakeRepo:
    """In-memory task queue on the pure task model, with a request id cache like production."""

    def __init__(self, count: int) -> None:
        self.tasks = {
            task_id(i): TaskRecord(task_id(i), state=TaskState.APPROVED) for i in range(count)
        }
        self.calls: list[tuple[str, str, int]] = []
        self._cache: dict[str, TaskResult] = {}

    def claim(
        self, worker_id: str, request_id: str, now_tick: int, lease_ticks: int = 400
    ) -> TaskResult:
        self.calls.append(("claim", request_id, now_tick))
        if request_id in self._cache:
            return self._cache[request_id]
        for name in sorted(self.tasks):
            task = self.tasks[name]
            if task.state is TaskState.APPROVED and task.attempt < task.max_attempts:
                claimed = claim_task(task, worker_id, now_tick, lease_ticks)
                self.tasks[name] = claimed
                return self._cache.setdefault(request_id, TaskResult(True, claimed))
        return TaskResult(False)

    def _work(
        self, credential: TaskCredential, target: TaskState, request_id: str, now_tick: int
    ) -> TaskResult:
        self.calls.append((target.value.lower(), request_id, now_tick))
        if request_id in self._cache:
            cached = self._cache[request_id]
            return TaskResult(cached.accepted, cached.task, replayed=True)
        current = self.tasks[credential.task_id]
        moved = worker_transition(current, credential, target, now_tick)
        if moved is None:
            return TaskResult(False, current)
        self.tasks[credential.task_id] = moved
        return self._cache.setdefault(request_id, TaskResult(True, moved))

    def start(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        return self._work(credential, TaskState.EXECUTING, request_id, now_tick)

    def complete(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        return self._work(credential, TaskState.DONE, request_id, now_tick)


def _counter() -> Callable[[], int]:
    state = {"tick": 0}

    def clock() -> int:
        state["tick"] += 1
        return state["tick"]

    return clock


def _stop_after(iterations: int) -> Callable[[], bool]:
    state = {"seen": 0}

    def stop() -> bool:
        state["seen"] += 1
        return state["seen"] > iterations

    return stop


def _run(
    repo: FakeRepo,
    schedule: FaultSchedule,
    config: WorkerConfig = CONFIG,
    *,
    iterations: int = 10,
    kill: Callable[[], None] | None = None,
) -> WorkerStats:
    def raise_killed() -> None:
        raise Killed

    switch = KillSwitch(schedule, kill or raise_killed)
    return run_worker(
        config, repo, schedule, switch, _counter(), lambda _: None, _stop_after(iterations)
    )


def test_task_ids_round_trip_and_are_valid_identifiers() -> None:
    assert task_id(7) == "t000007"
    assert task_index("t000007") == 7
    with pytest.raises(ScheduleError):
        task_index("job-7")
    with pytest.raises(ScheduleError):
        task_id(-1)


def test_without_faults_the_worker_completes_every_task() -> None:
    repo = FakeRepo(4)
    stats = _run(repo, build_schedule(1, PARAMS), iterations=10)
    assert all(task.state is TaskState.DONE for task in repo.tasks.values())
    assert stats.claimed == 4
    assert stats.completed == 4


@pytest.mark.parametrize(
    ("point", "expected_calls"),
    [
        (KillPoint.AFTER_CLAIM, ["claim"]),
        (KillPoint.AFTER_START, ["claim", "executing"]),
        (KillPoint.IN_HANDLER, ["claim", "executing"]),
        (KillPoint.BEFORE_COMPLETE, ["claim", "executing"]),
        (KillPoint.AFTER_COMPLETE, ["claim", "executing", "done"]),
    ],
)
def test_a_kill_stops_the_worker_at_exactly_its_point(
    point: KillPoint, expected_calls: list[str]
) -> None:
    repo = FakeRepo(4)
    schedule = replace(build_schedule(1, PARAMS), kills=(Kill(0, 1, point),))
    with pytest.raises(Killed):
        _run(repo, schedule)
    assert [call[0] for call in repo.calls] == expected_calls


def test_a_kill_is_planned_for_an_attempt_not_for_a_worker() -> None:
    repo = FakeRepo(4)
    schedule = replace(build_schedule(1, PARAMS), kills=(Kill(0, 2, KillPoint.AFTER_CLAIM),))
    stats = _run(repo, schedule, iterations=10)
    assert stats.completed == 4


def test_request_ids_differ_across_incarnations_and_iterations() -> None:
    first, second = FakeRepo(4), FakeRepo(4)
    schedule = build_schedule(1, PARAMS)
    _run(first, schedule, iterations=3)
    _run(second, schedule, replace(CONFIG, incarnation=1), iterations=3)
    first_ids = {call[1] for call in first.calls}
    second_ids = {call[1] for call in second.calls}
    assert len(first_ids) == len(first.calls)
    assert first_ids.isdisjoint(second_ids)


def test_a_clock_jump_moves_every_later_tick_of_that_worker_once() -> None:
    repo = FakeRepo(4)
    schedule = replace(build_schedule(1, PARAMS), jumps=(ClockJump(0, 2, 500),))
    _run(repo, schedule, iterations=3)
    claims = [call[2] for call in repo.calls if call[0] == "claim"]
    assert claims[0] < 100
    assert claims[1] >= 500
    assert claims[2] >= 500
    assert claims[2] < 700


def test_a_jump_for_another_worker_does_not_move_this_clock() -> None:
    repo = FakeRepo(4)
    schedule = replace(build_schedule(1, PARAMS), jumps=(ClockJump(1, 1, 900),))
    _run(repo, schedule, iterations=3)
    assert all(call[2] < 100 for call in repo.calls)


def test_a_restarted_worker_does_not_repeat_the_clock_jumps() -> None:
    repo = FakeRepo(4)
    schedule = replace(build_schedule(1, PARAMS), jumps=(ClockJump(0, 1, 500),))
    _run(repo, schedule, replace(CONFIG, incarnation=1), iterations=2)
    assert all(call[2] < 100 for call in repo.calls)


def test_a_replay_sends_the_old_request_again_and_production_serves_the_cache() -> None:
    repo = FakeRepo(4)
    replay = Replay(0, ReplayMode.DURING_RECOVERY, 0)
    schedule = replace(build_schedule(1, PARAMS), replays=(replay,))
    stats = _run(repo, schedule, iterations=10)
    assert stats.replays_sent == 1
    assert stats.replays_replayed == 1
    done_calls = [call for call in repo.calls if call[0] == "done"]
    assert len(done_calls) == 5
    assert len({call[1] for call in done_calls if call[1].endswith("-complete")}) == 4


def test_a_replay_with_lag_waits_for_its_tick() -> None:
    repo = FakeRepo(4)
    replay = Replay(0, ReplayMode.AFTER_RECOVERY, 400)
    schedule = replace(build_schedule(1, PARAMS), replays=(replay,))
    early = _run(FakeRepo(4), schedule, iterations=4)
    assert early.replays_sent == 0
    late = _run(repo, schedule, iterations=450)
    assert late.replays_sent == 1


def test_the_worker_stops_at_the_horizon() -> None:
    repo = FakeRepo(4)
    short = replace(CONFIG, horizon=5)
    stats = _run(repo, build_schedule(1, PARAMS), short, iterations=1000)
    assert stats.iterations < 1000


def test_a_denied_claim_sleeps_and_does_not_count_as_a_task() -> None:
    sleeps: list[float] = []
    repo = FakeRepo(0)
    schedule = build_schedule(1, PARAMS)
    switch = KillSwitch(schedule, lambda: None)
    stats = run_worker(CONFIG, repo, schedule, switch, _counter(), sleeps.append, _stop_after(3))
    assert stats.claimed == 0
    assert len(sleeps) == 3


def test_invalid_config_fails_closed() -> None:
    with pytest.raises(ScheduleError):
        WorkerConfig(worker=-1, incarnation=0, horizon=10, lease_ticks=5, handler_s=0.0)
    with pytest.raises(ScheduleError):
        WorkerConfig(worker=0, incarnation=0, horizon=10, lease_ticks=0, handler_s=0.0)
    with pytest.raises(ScheduleError):
        WorkerConfig(worker=0, incarnation=0, horizon=10, lease_ticks=5, handler_s=-1.0)
