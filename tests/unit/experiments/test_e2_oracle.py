"""E2 oracle: counts violations from a task event log and zone samples, with hand-built logs."""

import pytest

from waggle.experiments.e2_oracle import (
    OracleError,
    TaskEvent,
    ZoneSample,
    judge_tasks,
    judge_zones,
)


def _event(no: int, kind: str, state: str, token: int, tick: int, **extra: object) -> TaskEvent:
    values: dict[str, object] = {
        "event_no": no,
        "task_id": "T1",
        "kind": kind,
        "state": state,
        "token": token,
        "worker_id": None,
        "expires_tick": None,
        "observed_tick": tick,
    }
    values.update(extra)
    return TaskEvent(**values)  # type: ignore[arg-type]


def _claim(no: int, token: int, tick: int, worker: str = "w1", expires: int = 100) -> TaskEvent:
    return _event(
        no, "claimed", "ASSIGNED", token, tick, worker_id=worker, expires_tick=tick + expires
    )


CLEAN = (
    _event(1, "created", "PENDING", 0, 0),
    _claim(2, 1, 10),
    _event(3, "executing", "EXECUTING", 1, 12, worker_id="w1", expires_tick=110),
    _event(4, "done", "DONE", 1, 20),
)


def test_a_clean_log_has_no_violations() -> None:
    report = judge_tasks(CLEAN, {"T1": "DONE"})
    assert report.double_assignments == 0
    assert report.stale_writes_accepted == 0
    assert report.expired_writes_accepted == 0
    assert report.tasks_stuck == ()
    assert report.tasks_done == 1


def test_a_second_claim_inside_a_live_lease_is_a_double_assignment() -> None:
    log = (_claim(1, 1, 10, "w1", 100), _claim(2, 2, 50, "w2", 100))
    report = judge_tasks(log, {"T1": "ASSIGNED"})
    assert report.double_assignments == 1


def test_a_claim_after_recovery_is_not_a_double_assignment() -> None:
    log = (
        _claim(1, 1, 10, "w1", 100),
        _event(2, "recovered", "APPROVED", 1, 110),
        _claim(3, 2, 120, "w2", 100),
        _event(4, "done", "DONE", 2, 130),
    )
    report = judge_tasks(log, {"T1": "DONE"})
    assert report.double_assignments == 0
    assert report.tasks_recovered == 1
    assert report.recovery_ticks == (10,)


def test_a_write_with_an_old_token_after_a_newer_claim_is_a_stale_write() -> None:
    log = (
        _claim(1, 1, 10, "w1", 100),
        _event(2, "recovered", "APPROVED", 1, 110),
        _claim(3, 2, 120, "w2", 100),
        _event(4, "done", "DONE", 1, 125),
    )
    report = judge_tasks(log, {"T1": "DONE"})
    assert report.stale_writes_accepted == 1


def test_a_write_at_or_after_the_expiry_of_its_own_lease_is_an_expired_write() -> None:
    log = (_claim(1, 1, 10, "w1", 100), _event(2, "done", "DONE", 1, 110))
    report = judge_tasks(log, {"T1": "DONE"})
    assert report.expired_writes_accepted == 1
    assert report.stale_writes_accepted == 0


def test_a_task_that_is_not_terminal_at_the_end_is_stuck() -> None:
    report = judge_tasks(CLEAN[:2], {"T1": "ASSIGNED"})
    assert report.tasks_stuck == ("T1",)


def test_an_exhausted_task_is_terminal_and_not_stuck() -> None:
    report = judge_tasks((_claim(1, 1, 10),), {"T1": "FAILED"})
    assert report.tasks_stuck == ()


def test_events_out_of_order_or_of_an_unknown_kind_raise() -> None:
    with pytest.raises(OracleError):
        judge_tasks((CLEAN[1], CLEAN[0]), {"T1": "DONE"})
    with pytest.raises(OracleError):
        judge_tasks((_event(1, "teleported", "DONE", 1, 5),), {"T1": "DONE"})


def test_a_task_with_events_but_no_final_state_raises() -> None:
    with pytest.raises(OracleError):
        judge_tasks(CLEAN, {})


def test_two_robots_in_a_capacity_one_zone_are_a_violation() -> None:
    samples = (
        ZoneSample(1, "Z1", frozenset({"R1"}), 1),
        ZoneSample(2, "Z1", frozenset({"R1", "R2"}), 1),
        ZoneSample(3, "Z2", frozenset({"R1", "R2"}), 2),
    )
    report = judge_zones(samples)
    assert report.violation_samples == 1
    assert report.violating_ticks == (2,)
    assert report.undecided_samples == 0


def test_an_unknown_occupant_is_undecided_not_a_pass() -> None:
    report = judge_zones((ZoneSample(1, "Z1", None, 1),))
    assert report.violation_samples == 0
    assert report.undecided_samples == 1
