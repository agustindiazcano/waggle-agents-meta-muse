"""Cloud-only: a queued order is executed by the simulator and resolved in PostgreSQL."""

import numpy as np
import pytest

from waggle.coordination.task_model import TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.motion import MotionOrderRepository, NewOrder
from waggle.db.tasks import TaskRepository
from waggle.experiments.sim_motion import MotionExecutor
from waggle.sim import engine, robots, scripted
from waggle.sim.params import RobotKind

pytestmark = pytest.mark.heavy

TICKS_PER_SECOND = 40


def _live_task(database: Database) -> None:
    repo = TaskRepository(database)
    repo.create(TaskDefinition("job"))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        repo.advance("job", state, f"job-{state.value}", 0)
    assert repo.claim("carrier-0", "claim", 0, lease_ticks=100_000).task is not None


def _sim(queue: MotionOrderRepository) -> engine.Engine:
    fleet = robots.RobotFleet([RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[]], loop=False)
    executor = MotionExecutor(driver, queue, {"carrier-0": 0}, TICKS_PER_SECOND * 60)
    arrays = {**fleet.initial_arrays(np.zeros((1, 3))), **driver.initial_arrays()}
    return engine.Engine(1, arrays, [executor.system(), driver.system(), fleet.system()], {})


def test_a_queued_move_is_executed_and_frees_the_robot(database: Database) -> None:
    _live_task(database)
    queue = MotionOrderRepository(database)
    first = queue.enqueue("carrier-0", NewOrder("move_waypoint", "job", x=8.0, y=0.0, speed=1.0), 0)
    assert first.queued and first.order_id is not None
    sim = _sim(queue)
    sim.run(TICKS_PER_SECOND * 30)
    assert queue.pending() == ()
    assert abs(float(np.asarray(sim.state.arrays["robot_pose"])[0, 0]) - 8.0) < 1.5
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT status, resolved_tick FROM motion_orders WHERE order_id=%s", (first.order_id,)
        ).fetchone()
    assert row is not None and row[0] == "done" and row[1] is not None
    assert queue.enqueue("carrier-0", NewOrder("pick_package", "job", package_id="pk-1"), 1).queued


def test_a_queued_pick_fails_in_the_simulator(database: Database) -> None:
    _live_task(database)
    queue = MotionOrderRepository(database)
    queued = queue.enqueue("carrier-0", NewOrder("pick_package", "job", package_id="pk-1"), 0)
    _sim(queue).run(3)
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT status FROM motion_orders WHERE order_id=%s", (queued.order_id,)
        ).fetchone()
    assert row is not None and row[0] == "failed"
