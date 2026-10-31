"""The handoff finisher completes ordinary tasks normally and handoff tasks only when fenced."""

from unittest.mock import MagicMock

from waggle.coordination.corridors import (
    CorridorState,
    CorridorZone,
    Direction,
    ZoneObservation,
    ZoneToken,
)
from waggle.coordination.leases import LeaseState
from waggle.coordination.task_model import TaskCredential, TaskRecord, TaskState
from waggle.db.tasks import TaskRepository, TaskResult
from waggle.handoff_finisher import HandoffFinisher

CREDENTIAL = TaskCredential("t1", "robot-0", 1)
RECORD = TaskRecord("t1", TaskState.EXECUTING, 1, 1, "robot-0", 90)


class FakeCorridors:
    def __init__(self, holder: str | None = "robot-0", token: int = 4) -> None:
        lease = LeaseState(
            resource_id="dock",
            holder=holder,
            token=token if holder else 0,
            expires_tick=90 if holder else None,
            observed_tick=5,
        )
        self.state = CorridorState(
            (CorridorZone(lease, Direction.FORWARD if holder else None, False),)
        )

    def snapshot(self) -> CorridorState:
        return self.state


class FakeOccupancy:
    def __init__(self, occupants: tuple[str, ...] | None = ("robot-0",)) -> None:
        self.occupants = occupants
        self.asked: list[tuple[tuple[str, ...], int]] = []

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        self.asked.append((zone_ids, now_tick))
        return (ZoneObservation(zone_ids[0], now_tick, self.occupants),)


def _tasks(zone: str | None) -> MagicMock:
    tasks = MagicMock(spec=TaskRepository)
    tasks.handoff_zone.return_value = zone
    tasks.complete.return_value = TaskResult(True, RECORD)
    tasks.complete_handoff.return_value = TaskResult(True, RECORD)
    tasks.get.return_value = RECORD
    return tasks


def test_an_ordinary_task_uses_ordinary_completion() -> None:
    tasks = _tasks(None)
    result = HandoffFinisher(tasks, FakeCorridors(), FakeOccupancy()).complete(
        CREDENTIAL, "req-1", 7
    )
    assert result.accepted
    tasks.complete.assert_called_once_with(CREDENTIAL, "req-1", 7)
    tasks.complete_handoff.assert_not_called()


def test_a_handoff_task_passes_the_held_zone_token_and_trusted_occupancy() -> None:
    tasks, occupancy = _tasks("dock"), FakeOccupancy()
    result = HandoffFinisher(tasks, FakeCorridors(token=4), occupancy).complete(
        CREDENTIAL, "req-1", 7
    )
    assert result.accepted
    tasks.complete.assert_not_called()
    tasks.complete_handoff.assert_called_once_with(
        CREDENTIAL, ZoneToken("dock", 4), ZoneObservation("dock", 7, ("robot-0",)), "req-1", 7
    )
    assert occupancy.asked == [(("dock",), 7)]


def test_a_worker_that_does_not_hold_the_zone_is_refused_without_a_call() -> None:
    for holder in (None, "robot-9"):
        tasks = _tasks("dock")
        result = HandoffFinisher(tasks, FakeCorridors(holder=holder), FakeOccupancy()).complete(
            CREDENTIAL, "req-1", 7
        )
        assert not result.accepted
        tasks.complete.assert_not_called()
        tasks.complete_handoff.assert_not_called()


def test_a_missing_zone_row_is_refused() -> None:
    tasks = _tasks("elsewhere")
    result = HandoffFinisher(tasks, FakeCorridors(), FakeOccupancy()).complete(
        CREDENTIAL, "req-1", 7
    )
    assert not result.accepted
    tasks.complete_handoff.assert_not_called()


def test_the_trusted_store_decides_occupancy_not_the_worker() -> None:
    tasks = _tasks("dock")
    tasks.complete_handoff.return_value = TaskResult(False, RECORD)
    result = HandoffFinisher(
        tasks, FakeCorridors(), FakeOccupancy(("robot-0", "robot-1"))
    ).complete(CREDENTIAL, "req-1", 7)
    assert not result.accepted
    observation = tasks.complete_handoff.call_args.args[2]
    assert observation.occupants == ("robot-0", "robot-1")
