"""The simulator executes queued move orders and refuses what it cannot model (ADR-051)."""

import numpy as np
import pytest

from waggle.db.motion import MotionOrder, NewOrder
from waggle.experiments.sim_motion import MotionExecutor
from waggle.sim import engine, packages, params, robots, scenarios, scripted
from waggle.sim.params import RobotKind

TICKS_PER_SECOND = 40


class FakeQueue:
    def __init__(self, *orders: MotionOrder) -> None:
        self.queue = list(orders)
        self.resolved: list[tuple[int, str, int]] = []

    def pending(self, limit: int = 100) -> tuple[MotionOrder, ...]:
        return tuple(self.queue[:limit])

    def resolve(self, order_id: int, outcome: str, now_tick: int) -> bool:
        before = len(self.queue)
        self.queue = [o for o in self.queue if o.order_id != order_id]
        if len(self.queue) == before:
            return False
        self.resolved.append((order_id, outcome, now_tick))
        return True


def _move(order_id: int, robot: str, x: float, y: float) -> MotionOrder:
    return MotionOrder(order_id, robot, NewOrder("move_waypoint", "job", x=x, y=y, speed=1.0), 0)


def _rig(
    queue: FakeQueue, *, timeout_ticks: int = 40 * 60
) -> tuple[engine.Engine, scripted.WaypointDriver]:
    fleet = robots.RobotFleet([RobotKind.CARRIER, RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[], []], loop=False)
    executor = MotionExecutor(driver, queue, {"carrier-0": 0, "carrier-1": 1}, timeout_ticks)
    arrays = {
        **fleet.initial_arrays(np.array([[0.0, 0.0, 0.0], [0.0, 10.0, 0.0]])),
        **driver.initial_arrays(),
    }
    sim = engine.Engine(1, arrays, [executor.system(), driver.system(), fleet.system()], {})
    return sim, driver


def test_a_move_order_drives_the_robot_and_resolves_done_once() -> None:
    queue = FakeQueue(_move(5, "carrier-0", 8.0, 0.0))
    sim, _ = _rig(queue)
    sim.run(TICKS_PER_SECOND * 30)
    assert [(r[0], r[1]) for r in queue.resolved] == [(5, "done")]
    pose = np.asarray(sim.state.arrays["robot_pose"])
    assert abs(pose[0, 0] - 8.0) < 1.5
    assert abs(pose[1, 0]) < 1e-9  # the other robot got no order


def test_the_order_stays_pending_until_the_robot_arrives() -> None:
    queue = FakeQueue(_move(5, "carrier-0", 30.0, 0.0))
    sim, _ = _rig(queue)
    sim.run(TICKS_PER_SECOND * 3)
    assert queue.resolved == []
    assert [o.order_id for o in queue.queue] == [5]


@pytest.mark.parametrize(
    "order",
    [
        NewOrder("pick_package", "job", package_id="pk-1"),
        NewOrder("deliver_package", "job", package_id="pk-1", zone_id="dock"),
    ],
)
def test_package_orders_fail_because_the_simulator_has_no_package_model(order: NewOrder) -> None:
    queue = FakeQueue(MotionOrder(9, "carrier-0", order, 0))
    sim, _ = _rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(9, "failed")]


def test_an_unknown_robot_fails_the_order() -> None:
    queue = FakeQueue(_move(3, "ghost", 1.0, 1.0))
    sim, _ = _rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(3, "failed")]


def test_an_order_that_is_not_reached_times_out_and_the_robot_stops() -> None:
    queue = FakeQueue(_move(4, "carrier-0", 500.0, 0.0))
    sim, driver = _rig(queue, timeout_ticks=TICKS_PER_SECOND * 2)
    sim.run(TICKS_PER_SECOND * 6)
    assert [(r[0], r[1]) for r in queue.resolved] == [(4, "failed")]
    assert driver.routes[0] == []
    assert np.asarray(sim.state.arrays["robot_speed"])[0] == 0.0


def test_two_runs_with_the_same_orders_are_identical() -> None:
    outcomes = []
    for _ in range(2):
        queue = FakeQueue(_move(1, "carrier-0", 6.0, 0.0), _move(2, "carrier-1", 6.0, 10.0))
        sim, _ = _rig(queue)
        sim.run(TICKS_PER_SECOND * 20)
        outcomes.append((queue.resolved, np.asarray(sim.state.arrays["robot_pose"]).tobytes()))
    assert outcomes[0] == outcomes[1]


def test_a_loop_driver_is_refused() -> None:
    fleet = robots.RobotFleet([RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[]], loop=True)
    with pytest.raises(ValueError):
        MotionExecutor(driver, FakeQueue(), {"carrier-0": 0}, 100)


@pytest.mark.parametrize("timeout", [0, -1, True])
def test_a_bad_timeout_is_refused(timeout: int) -> None:
    fleet = robots.RobotFleet([RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[]], loop=False)
    with pytest.raises(ValueError):
        MotionExecutor(driver, FakeQueue(), {"carrier-0": 0}, timeout)


# ---------------------------------------------------------------- package orders on the model

PICK = NewOrder("pick_package", "job", package_id="pk-1")
DELIVER = NewOrder("deliver_package", "job", package_id="pk-1", zone_id="depot_n")
SPECS = (packages.PackageSpec("pk-1", "station_1", 3.0, 21.5),)


def _pkg_rig(
    queue: FakeQueue, *, speed: float = 0.0
) -> tuple[engine.Engine, packages.PackageModel, MotionExecutor]:
    fleet = robots.RobotFleet([RobotKind.CARRIER, RobotKind.CARRIER])
    model = packages.PackageModel(
        scenarios.load_map("A"), SPECS, [params.PACKAGE_CAPACITY[RobotKind.CARRIER]] * 2
    )
    driver = scripted.WaypointDriver(fleet, [[], []], loop=False)
    executor = MotionExecutor(
        driver, queue, {"carrier-0": 0, "carrier-1": 1}, 40 * 60, packages=model
    )
    poses = np.array([[3.0, 21.0, 0.0], [20.0, 2.0, 0.0]])
    arrays = {
        **fleet.initial_arrays(poses, np.array([speed, 0.0])),
        **driver.initial_arrays(),
        **model.initial_arrays(),
    }
    systems = [executor.system(), driver.system(), fleet.system(), model.system()]
    return engine.Engine(1, arrays, systems, {}), model, executor


def _status(sim: engine.Engine) -> int:
    return int(np.asarray(sim.state.arrays["pkg_status"])[0])


def test_a_pick_order_in_place_resolves_done_and_the_package_is_held() -> None:
    queue = FakeQueue(MotionOrder(9, "carrier-0", PICK, 0))
    sim, _, _ = _pkg_rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(9, "done")]
    assert _status(sim) == packages.Status.HELD
    assert np.asarray(sim.state.arrays["pkg_holder"])[0] == 0


def test_a_pick_from_the_wrong_place_fails_and_changes_nothing() -> None:
    queue = FakeQueue(MotionOrder(9, "carrier-1", PICK, 0))  # carrier-1 is in the corridor
    sim, _, _ = _pkg_rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(9, "failed")]
    assert _status(sim) == packages.Status.AT_STATION


def test_a_pick_at_speed_fails() -> None:
    queue = FakeQueue(MotionOrder(9, "carrier-0", PICK, 0))
    sim, _, _ = _pkg_rig(queue, speed=1.0)
    sim.step()
    assert [(r[0], r[1]) for r in queue.resolved] == [(9, "failed")]


def test_a_second_pick_of_a_held_package_fails() -> None:
    queue = FakeQueue(MotionOrder(1, "carrier-0", PICK, 0), MotionOrder(2, "carrier-1", PICK, 0))
    sim, _, _ = _pkg_rig(queue)
    sim.run(2)
    assert sorted((r[0], r[1]) for r in queue.resolved) == [(1, "done"), (2, "failed")]


def test_a_package_order_for_a_robot_with_an_active_move_fails() -> None:
    queue = FakeQueue(_move(1, "carrier-0", 30.0, 21.0), MotionOrder(2, "carrier-0", PICK, 0))
    sim, _, _ = _pkg_rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(2, "failed")]
    assert _status(sim) == packages.Status.AT_STATION


def test_deliver_by_a_robot_that_does_not_hold_the_package_fails() -> None:
    queue = FakeQueue(MotionOrder(5, "carrier-0", DELIVER, 0))
    sim, _, _ = _pkg_rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(5, "failed")]


def test_pick_move_then_deliver_runs_the_whole_lifecycle() -> None:
    queue = FakeQueue(MotionOrder(1, "carrier-0", PICK, 0))
    sim, model, _ = _pkg_rig(queue)
    sim.run(2)
    queue.queue.append(_move(2, "carrier-0", 34.0, 21.0))
    sim.run(TICKS_PER_SECOND * 40)
    queue.queue.append(MotionOrder(3, "carrier-0", DELIVER, 0))
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(1, "done"), (2, "done"), (3, "done")]
    assert _status(sim) == packages.Status.DELIVERED
    model.check_invariants(sim.state)


def test_package_runs_with_the_same_orders_have_equal_hashes() -> None:
    hashes = []
    for _ in range(2):
        queue = FakeQueue(MotionOrder(1, "carrier-0", PICK, 0), _move(2, "carrier-1", 25.0, 2.0))
        sim, _, _ = _pkg_rig(queue)
        sim.run(TICKS_PER_SECOND * 5)
        hashes.append(sim.state_hash())
    assert hashes[0] == hashes[1]


def test_an_order_run_on_a_fork_state_does_not_change_the_live_arrays() -> None:
    queue = FakeQueue()
    sim, model, _ = _pkg_rig(queue)
    live = sim.state_hash()
    fork = sim.fork()
    assert model.pick(fork.state, 77, 0, "pk-1").ok
    assert sim.state_hash() == live
    assert _status(sim) == packages.Status.AT_STATION


def test_without_a_package_model_package_orders_still_fail_at_once() -> None:
    queue = FakeQueue(MotionOrder(9, "carrier-0", PICK, 0))
    sim, _ = _rig(queue)
    sim.run(2)
    assert [(r[0], r[1]) for r in queue.resolved] == [(9, "failed")]
