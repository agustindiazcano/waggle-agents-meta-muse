"""Cloud-only motion order checks against PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from typing import cast

import pytest

from waggle.coordination.corridors import CorridorRequest, Direction, ZoneObservation
from waggle.coordination.task_model import TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.motion import MotionOrderRepository, MotionRefused, NewOrder
from waggle.db.tasks import TaskRepository

pytestmark = pytest.mark.heavy

MOVE = NewOrder("move_waypoint", "job", x=1.0, y=2.0, speed=1.0)
PICK = NewOrder("pick_package", "job", package_id="pk-1")


def _task(
    database: Database, task_id: str = "job", worker: str = "robot", lease_ticks: int = 10
) -> None:
    repo = TaskRepository(database)
    repo.create(TaskDefinition(task_id))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        repo.advance(task_id, state, f"{task_id}-{state.value}", 0)
    assert repo.claim(worker, f"claim-{task_id}", 0, lease_ticks=lease_ticks).task is not None


def _refused(repo: MotionOrderRepository, robot: str, order: NewOrder, tick: int = 1) -> str:
    with pytest.raises(MotionRefused) as caught:
        repo.enqueue(robot, order, tick)
    return caught.value.reason


def test_a_live_own_task_queues_an_order(database: Database) -> None:
    _task(database)
    result = MotionOrderRepository(database).enqueue("robot", MOVE, 1)
    assert (result.queued, result.reason) == (True, "queued") and result.order_id is not None


def test_unknown_task_and_another_robots_task_are_refused(database: Database) -> None:
    _task(database)
    repo = MotionOrderRepository(database)
    assert (
        _refused(repo, "robot", NewOrder("pick_package", "missing", package_id="pk-1")) == "no_task"
    )
    assert _refused(repo, "intruder", PICK) == "not_your_task"


def test_an_expired_or_unclaimed_task_is_refused(database: Database) -> None:
    _task(database)
    repo = MotionOrderRepository(database)
    assert _refused(repo, "robot", PICK, tick=10) == "task_not_live"
    TaskRepository(database).create(TaskDefinition("idle"))
    assert (
        _refused(repo, "robot", NewOrder("pick_package", "idle", package_id="p")) == "not_your_task"
    )


def test_the_same_order_replays_and_a_different_one_is_busy(database: Database) -> None:
    _task(database)
    repo = MotionOrderRepository(database)
    first = repo.enqueue("robot", MOVE, 1)
    again = repo.enqueue("robot", MOVE, 2)
    other = repo.enqueue("robot", PICK, 2)
    assert (again.reason, again.order_id) == ("replayed", first.order_id)
    assert (other.queued, other.reason, other.order_id) == (False, "busy", None)


def test_resolving_frees_the_robot_and_is_not_repeatable(database: Database) -> None:
    _task(database)
    repo = MotionOrderRepository(database)
    first = repo.enqueue("robot", MOVE, 1)
    assert first.order_id is not None
    assert [o.order_id for o in repo.pending()] == [first.order_id]
    assert repo.resolve(first.order_id, "done", 2)
    assert not repo.resolve(first.order_id, "done", 3)
    assert repo.pending() == ()
    assert repo.enqueue("robot", PICK, 3).reason == "queued"


def test_concurrent_different_orders_leave_one_pending(database: Database) -> None:
    _task(database)
    repo = MotionOrderRepository(database)
    orders = [NewOrder("move_waypoint", "job", x=float(i), y=0.0, speed=1.0) for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda o: repo.enqueue("robot", o, 1), orders))
    assert sum(r.reason == "queued" for r in results) == 1
    assert sum(r.reason == "busy" for r in results) == 7
    assert len(repo.pending()) == 1


def _hold(database: Database, zone: str, holder: str = "robot", tick: int = 0) -> None:
    corridors = CorridorRepository(database)
    corridors.register((zone,))
    granted = corridors.reserve(
        CorridorRequest(holder, (zone,), Direction.FORWARD),
        tick,
        (ZoneObservation(zone, tick, ()),),
    )
    assert granted.granted


def test_delivery_needs_a_live_lease_on_the_zone(database: Database) -> None:
    _task(database)
    repo = MotionOrderRepository(database)
    deliver = NewOrder("deliver_package", "job", package_id="pk-1", zone_id="dock")
    assert _refused(repo, "robot", deliver) == "unknown_zone"
    _hold(database, "dock", holder="someone-else")
    assert _refused(repo, "robot", deliver) == "zone_not_held"


def test_delivery_into_a_held_zone_queues_and_an_expired_lease_does_not(database: Database) -> None:
    _task(database, lease_ticks=10_000)
    _hold(database, "dock")
    repo = MotionOrderRepository(database)
    deliver = NewOrder("deliver_package", "job", package_id="pk-1", zone_id="dock")
    assert repo.enqueue("robot", deliver, 1).reason == "queued"
    with database.transaction() as connection:
        row = connection.execute("SELECT expires_tick FROM zones WHERE zone_id='dock'").fetchone()
    assert row is not None
    expired = cast(int, row[0])
    repo.resolve(repo.pending()[0].order_id, "done", 2)
    assert _refused(repo, "robot", deliver, tick=expired) == "zone_not_held"
