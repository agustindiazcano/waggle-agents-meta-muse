"""E2 fault schedule: a pure, seeded plan of kills, clock jumps, replays and database delays."""

import json
from dataclasses import replace

import pytest

from waggle.experiments.e2_faults import (
    DbDelay,
    FaultParams,
    KillPoint,
    ReplayMode,
    ScheduleError,
    build_schedule,
    db_delay,
)

PARAMS = FaultParams()


def test_same_seed_gives_the_same_schedule() -> None:
    assert build_schedule(7, PARAMS) == build_schedule(7, PARAMS)


def test_different_seeds_give_different_schedules() -> None:
    assert build_schedule(7, PARAMS) != build_schedule(8, PARAMS)


def test_defaults_are_the_design_assumptions() -> None:
    assert (PARAMS.workers, PARAMS.tasks, PARAMS.horizon) == (8, 500, 20000)


def test_killed_task_count_is_exact() -> None:
    schedule = build_schedule(3, replace(PARAMS, kill_rate=0.2))
    killed = {kill.task_index for kill in schedule.kills}
    assert len(killed) == 100


def test_kills_use_every_kill_point_and_stay_in_range() -> None:
    schedule = build_schedule(3, PARAMS)
    assert {kill.point for kill in schedule.kills} == set(KillPoint)
    assert all(0 <= kill.task_index < PARAMS.tasks for kill in schedule.kills)


def test_kill_attempts_are_consecutive_from_one_and_capped() -> None:
    params = replace(PARAMS, max_kills_per_task=3)
    schedule = build_schedule(11, params)
    by_task: dict[int, list[int]] = {}
    for kill in schedule.kills:
        by_task.setdefault(kill.task_index, []).append(kill.attempt)
    for attempts in by_task.values():
        assert attempts == list(range(1, len(attempts) + 1))
        assert len(attempts) <= 3


def test_no_kill_rate_means_no_kills() -> None:
    assert build_schedule(1, replace(PARAMS, kill_rate=0.0)).kills == ()


def test_clock_jumps_are_bounded_and_counted_per_worker() -> None:
    params = replace(PARAMS, clock_jumps_per_worker=3, jump_ticks_min=10, jump_ticks_max=90)
    schedule = build_schedule(5, params)
    assert len(schedule.jumps) == 3 * params.workers
    for jump in schedule.jumps:
        assert 0 <= jump.worker < params.workers
        assert 1 <= jump.iteration <= params.worker_iterations
        assert 10 <= jump.ticks <= 90


def test_replays_have_the_declared_count_and_lag_rules() -> None:
    schedule = build_schedule(5, replace(PARAMS, replay_rate=0.1, replay_lag_max=40))
    assert len(schedule.replays) == 50
    assert len({replay.task_index for replay in schedule.replays}) == 50
    for replay in schedule.replays:
        if replay.mode is ReplayMode.DURING_RECOVERY:
            assert replay.lag_ticks == 0
        else:
            assert 1 <= replay.lag_ticks <= 40
    assert {replay.mode for replay in schedule.replays} == set(ReplayMode)


def test_changing_one_rate_does_not_reshuffle_the_other_faults() -> None:
    base = build_schedule(9, PARAMS)
    other = build_schedule(9, replace(PARAMS, replay_rate=0.3, delay_rate=0.5))
    assert other.kills == base.kills
    assert other.jumps == base.jumps
    assert other.replays != base.replays


def test_db_delay_is_a_pure_function_of_its_arguments() -> None:
    schedule = build_schedule(4, replace(PARAMS, delay_rate=0.5))
    forward = [db_delay(schedule, 2, call) for call in range(50)]
    backward = [db_delay(schedule, 2, call) for call in reversed(range(50))]
    assert forward == list(reversed(backward))


def test_db_delay_respects_rate_and_bound() -> None:
    schedule = build_schedule(4, replace(PARAMS, delay_rate=0.25, delay_ms_max=80))
    delays = [db_delay(schedule, w, c) for w in range(PARAMS.workers) for c in range(250)]
    delayed = [d for d in delays if d != DbDelay(0, 0)]
    assert 0.15 < len(delayed) / len(delays) < 0.35
    assert all(0 <= d.before_ms <= 80 and 0 <= d.commit_ms <= 80 for d in delays)


def test_zero_delay_rate_never_delays() -> None:
    schedule = build_schedule(4, replace(PARAMS, delay_rate=0.0))
    assert all(db_delay(schedule, 0, c) == DbDelay(0, 0) for c in range(200))


def test_lookups_return_the_scheduled_fault_or_none() -> None:
    schedule = build_schedule(2, PARAMS)
    kill = schedule.kills[0]
    assert schedule.kill_for(kill.task_index, kill.attempt) == kill.point
    assert schedule.kill_for(kill.task_index, 99) is None
    jump = schedule.jumps[0]
    assert schedule.jump_for(jump.worker, jump.iteration) == jump.ticks
    assert schedule.jump_for(jump.worker, 10**6) == 0
    replay = schedule.replays[0]
    assert schedule.replay_for(replay.task_index) == replay


def test_summary_is_json_serialisable_and_counts_faults() -> None:
    schedule = build_schedule(6, PARAMS)
    summary = schedule.summary()
    assert json.loads(json.dumps(summary)) == summary
    assert summary["seed"] == 6
    assert summary["kills"] == len(schedule.kills)
    by_point = summary["kills_by_point"]
    assert isinstance(by_point, dict)
    assert sum(by_point.values()) == len(schedule.kills)


@pytest.mark.parametrize(
    "change",
    [
        {"workers": 0},
        {"tasks": 0},
        {"horizon": 0},
        {"kill_rate": 1.5},
        {"kill_rate": -0.1},
        {"replay_rate": 2.0},
        {"delay_rate": -1.0},
        {"max_kills_per_task": 0},
        {"clock_jumps_per_worker": -1},
        {"worker_iterations": 0},
        {"jump_ticks_min": 100, "jump_ticks_max": 50},
        {"jump_ticks_min": 0},
        {"replay_lag_max": 0},
        {"delay_ms_max": -1},
    ],
)
def test_invalid_parameters_fail_closed(change: dict[str, object]) -> None:
    with pytest.raises(ScheduleError):
        build_schedule(1, replace(PARAMS, **change))  # type: ignore[arg-type]


def test_db_delay_rejects_unknown_worker_or_call() -> None:
    schedule = build_schedule(1, PARAMS)
    with pytest.raises(ScheduleError):
        db_delay(schedule, PARAMS.workers, 0)
    with pytest.raises(ScheduleError):
        db_delay(schedule, 0, -1)
