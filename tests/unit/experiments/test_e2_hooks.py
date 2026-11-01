"""Unit tests for the E2 chaos harness hooks: KillSwitch and DelayedDatabase."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import cast

import psycopg
import pytest

from waggle.db.connection import Row
from waggle.experiments.e2_faults import (
    FaultParams,
    KillPoint,
    ScheduleError,
    build_schedule,
    db_delay,
)
from waggle.experiments.e2_hooks import DelayedDatabase, KillSwitch, TransactionSource

PARAMS = FaultParams()


class FakeInner:
    """Fake transaction source recording enter, commit, and rollback events."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection[Row]]:
        self.events.append("enter")
        try:
            yield cast(psycopg.Connection[Row], object())
            self.events.append("commit")
        except BaseException:
            self.events.append("rollback")
            raise


def test_kill_switch_fires_at_scheduled_point() -> None:
    schedule = build_schedule(1, PARAMS)
    assert len(schedule.kills) > 0
    kill = schedule.kills[0]

    kill_calls = 0

    def fake_kill() -> None:
        nonlocal kill_calls
        kill_calls += 1

    switch = KillSwitch(schedule, fake_kill)

    other_point = next(p for p in KillPoint if p != kill.point)
    assert not switch.reach(other_point, kill.task_index, kill.attempt)
    assert kill_calls == 0

    assert not switch.reach(kill.point, kill.task_index, 99999)
    assert kill_calls == 0

    assert switch.reach(kill.point, kill.task_index, kill.attempt)
    assert kill_calls == 1


def test_kill_switch_fired_records_hits_in_order() -> None:
    schedule = build_schedule(1, PARAMS)
    assert len(schedule.kills) >= 2
    kill1 = schedule.kills[0]
    kill2 = schedule.kills[1]

    switch = KillSwitch(schedule, lambda: None)
    switch.reach(kill1.point, kill1.task_index, kill1.attempt)
    switch.reach(kill2.point, kill2.task_index, kill2.attempt)

    assert switch.fired == (
        (kill1.task_index, kill1.attempt, kill1.point),
        (kill2.task_index, kill2.attempt, kill2.point),
    )


def test_kill_switch_rejects_invalid_task_or_attempt() -> None:
    schedule = build_schedule(1, PARAMS)
    switch = KillSwitch(schedule, lambda: None)

    with pytest.raises(ScheduleError):
        switch.reach(KillPoint.AFTER_CLAIM, -1, 1)

    with pytest.raises(ScheduleError):
        switch.reach(KillPoint.AFTER_CLAIM, 0, 0)


def test_delayed_database_event_order_and_sleep_times() -> None:
    params = replace(PARAMS, delay_rate=1.0, delay_ms_max=100)
    seed = 1
    while True:
        schedule = build_schedule(seed, params)
        d0 = db_delay(schedule, 0, 0)
        d1 = db_delay(schedule, 0, 1)
        if d0.before_ms > 0 and d0.commit_ms > 0 and d1.before_ms > 0 and d1.commit_ms > 0:
            break
        seed += 1

    events: list[str] = []
    slept: list[float] = []

    def recording_sleep(seconds: float) -> None:
        slept.append(seconds)
        if events and events[-1] == "body":
            events.append("sleep(commit)")
        else:
            events.append("sleep(before)")

    inner = FakeInner(events)
    delayed_db = DelayedDatabase(inner, schedule, 0, recording_sleep)

    with delayed_db.transaction():
        events.append("body")

    assert events == ["sleep(before)", "enter", "body", "sleep(commit)", "commit"]
    assert slept == [d0.before_ms / 1000.0, d0.commit_ms / 1000.0]

    events.clear()
    slept.clear()
    with delayed_db.transaction():
        events.append("body")

    assert events == ["sleep(before)", "enter", "body", "sleep(commit)", "commit"]
    assert slept == [d1.before_ms / 1000.0, d1.commit_ms / 1000.0]


def test_delayed_database_zero_delay_rate_never_sleeps() -> None:
    schedule = build_schedule(1, replace(PARAMS, delay_rate=0.0))
    events: list[str] = []
    slept: list[float] = []

    inner = FakeInner(events)
    delayed_db = DelayedDatabase(inner, schedule, 0, slept.append)

    with delayed_db.transaction():
        events.append("body")

    assert slept == []
    assert events == ["enter", "body", "commit"]


def test_delayed_database_rollback_on_exception() -> None:
    schedule = build_schedule(1, replace(PARAMS, delay_rate=1.0, delay_ms_max=100))
    events: list[str] = []
    slept: list[float] = []

    def recording_sleep(seconds: float) -> None:
        slept.append(seconds)
        if events and events[-1] == "body":
            events.append("sleep(commit)")
        else:
            events.append("sleep(before)")

    inner = FakeInner(events)
    delayed_db = DelayedDatabase(inner, schedule, 0, recording_sleep)

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError), delayed_db.transaction():
        events.append("body")
        raise CustomError("boom")

    assert "commit" not in events
    assert "sleep(commit)" not in events
    assert events[-1] == "rollback"


def test_delayed_database_calls_property_counts_started_transactions() -> None:
    schedule = build_schedule(1, PARAMS)
    events: list[str] = []
    inner = FakeInner(events)
    delayed_db = DelayedDatabase(inner, schedule, 0, lambda _: None)

    assert delayed_db.calls == 0
    with delayed_db.transaction():
        assert delayed_db.calls == 1

    with delayed_db.transaction():
        assert delayed_db.calls == 2

    assert delayed_db.calls == 2


@pytest.mark.parametrize("bad_worker", [-1, PARAMS.workers, PARAMS.workers + 5])
def test_delayed_database_rejects_worker_out_of_range(bad_worker: int) -> None:
    schedule = build_schedule(1, PARAMS)
    inner = FakeInner([])
    with pytest.raises(ScheduleError):
        DelayedDatabase(inner, schedule, bad_worker, lambda _: None)


def test_delayed_database_satisfies_transaction_source_protocol() -> None:
    schedule = build_schedule(1, PARAMS)
    inner = FakeInner([])
    delayed_db = DelayedDatabase(inner, schedule, 0, lambda _: None)
    assert isinstance(delayed_db, TransactionSource)
