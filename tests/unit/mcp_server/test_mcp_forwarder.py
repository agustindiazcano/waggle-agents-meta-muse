"""The forwarder maps allowed tools onto fenced repositories with trusted tick and occupancy."""

import pytest

from waggle.coordination.corridors import (
    CorridorReason,
    CorridorResult,
    CorridorState,
    ZoneObservation,
    ZoneToken,
)
from waggle.coordination.task_model import TaskRecord, TaskState
from waggle.mcp_server.forwarder import FencedForwarder, ToolDenied, ToolUnavailable
from waggle.mcp_server.identity import Identity

ROBOT = Identity("carrier", "robot-0")


class FakeCorridors:
    def __init__(self, reason: CorridorReason = CorridorReason.RELEASED) -> None:
        self.reason = reason
        self.calls: list[tuple[str, tuple[ZoneToken, ...], int, tuple[ZoneObservation, ...]]] = []

    def release(
        self,
        holder: str,
        tokens: tuple[ZoneToken, ...],
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
    ) -> CorridorResult:
        self.calls.append((holder, tokens, now_tick, observations))
        return CorridorResult(
            CorridorState(()), self.reason == CorridorReason.RELEASED, self.reason
        )


class FakeTasks:
    def __init__(self, *records: TaskRecord) -> None:
        self.records = {r.task_id: r for r in records}

    def get(self, task_id: str) -> TaskRecord | None:
        return self.records.get(task_id)


class FakeTicks:
    def __init__(self, tick: int = 42, *, fail: bool = False) -> None:
        self.tick = tick
        self.fail = fail

    def now_tick(self) -> int:
        if self.fail:
            raise RuntimeError("clock down")
        return self.tick


class FakeOccupancy:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.asked: list[tuple[tuple[str, ...], int]] = []

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        if self.fail:
            raise RuntimeError("sensor down")
        self.asked.append((zone_ids, now_tick))
        return tuple(ZoneObservation(z, now_tick, ()) for z in zone_ids)


def _forwarder(
    corridors: FakeCorridors | None = None,
    tasks: FakeTasks | None = None,
    ticks: FakeTicks | None = None,
    occupancy: FakeOccupancy | None = None,
) -> FencedForwarder:
    return FencedForwarder(
        corridors or FakeCorridors(),
        tasks or FakeTasks(),
        ticks or FakeTicks(),
        occupancy or FakeOccupancy(),
    )


def test_release_zone_uses_the_derived_holder_trusted_tick_and_occupancy() -> None:
    corridors, occupancy = FakeCorridors(), FakeOccupancy()
    result = _forwarder(corridors, occupancy=occupancy).forward(
        ROBOT, "release_zone", {"zone_id": "dock", "token": 7}, 1.0
    )
    assert result == {"released": True, "reason": "released"}
    holder, tokens, tick, observations = corridors.calls[0]
    assert holder == "robot-0" and tokens == (ZoneToken("dock", 7),) and tick == 42
    assert observations == (ZoneObservation("dock", 42, ()),)
    assert occupancy.asked == [(("dock",), 42)]


def test_release_zone_reports_a_denied_release_without_raising() -> None:
    corridors = FakeCorridors(CorridorReason.OCCUPIED)
    result = _forwarder(corridors).forward(
        ROBOT, "release_zone", {"zone_id": "dock", "token": 7}, 1.0
    )
    assert result == {"released": False, "reason": "occupied"}


@pytest.mark.parametrize("broken", ["ticks", "occupancy"])
def test_release_zone_fails_when_a_trusted_source_fails(broken: str) -> None:
    corridors = FakeCorridors()
    forwarder = _forwarder(
        corridors,
        ticks=FakeTicks(fail=broken == "ticks"),
        occupancy=FakeOccupancy(fail=broken == "occupancy"),
    )
    with pytest.raises(RuntimeError):
        forwarder.forward(ROBOT, "release_zone", {"zone_id": "dock", "token": 7}, 1.0)
    assert corridors.calls == []


def test_get_task_returns_the_assigned_workers_own_task() -> None:
    record = TaskRecord(
        "t1", TaskState.EXECUTING, attempt=1, token=3, worker_id="robot-0", expires_tick=90
    )
    result = _forwarder(tasks=FakeTasks(record)).forward(ROBOT, "get_task", {"task_id": "t1"}, 1.0)
    assert result == {
        "task_id": "t1",
        "state": "EXECUTING",
        "attempt": 1,
        "token": 3,
        "expires_tick": 90,
    }


def test_get_task_denies_another_workers_or_a_missing_task_alike() -> None:
    other = TaskRecord("t1", TaskState.EXECUTING, 1, 3, "robot-9", 90)
    forwarder = _forwarder(tasks=FakeTasks(other))
    with pytest.raises(ToolDenied) as foreign:
        forwarder.forward(ROBOT, "get_task", {"task_id": "t1"}, 1.0)
    with pytest.raises(ToolDenied) as missing:
        forwarder.forward(ROBOT, "get_task", {"task_id": "nope"}, 1.0)
    assert str(foreign.value) == str(missing.value)


@pytest.mark.parametrize(
    "tool", ["move_waypoint", "pick_package", "deliver_package", "get_inventory", "unknown"]
)
def test_tools_without_a_trusted_backend_are_unavailable(tool: str) -> None:
    with pytest.raises(ToolUnavailable):
        _forwarder().forward(ROBOT, tool, {}, 1.0)
