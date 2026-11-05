"""The simulator side of the motion order queue (ADR-051).

The MCP server only queues orders; the simulator owns ground truth, so it executes them. A
``move_waypoint`` order replaces the robot's route with one waypoint and resolves ``done`` when
the waypoint driver reports arrival, or ``failed`` when the deadline passes. ``pick_package`` and
``deliver_package`` go to the package model, which checks ground truth and resolves ``done`` or
``failed`` in the same tick. With no package model they resolve ``failed`` at once: nothing is
reported as done that did not happen. An order for a robot the simulation does not have, or for a
robot with an active order, also fails. Only the live simulation runs this system, never a
rollout fork.
"""

from collections.abc import Mapping
from typing import Literal, Protocol

import numpy as np

from waggle.db.motion import MotionOrder
from waggle.sim import state
from waggle.sim.engine import System
from waggle.sim.packages import PackageModel
from waggle.sim.scripted import WaypointDriver


class PackageRegistryPort(Protocol):
    """The id listing of ``PackageRegistry``."""

    def ids(self) -> tuple[str, ...]:
        """Every registered package id."""
        ...


def packages_match(registry: PackageRegistryPort, packages: PackageModel) -> bool:
    """True only when the registry and the simulator hold exactly the same package ids.

    Order does not matter; a missing, extra or duplicated id on either side is a mismatch.
    """
    registry_ids = registry.ids()
    simulator_ids = packages.package_ids
    return sorted(registry_ids) == sorted(simulator_ids)


class OrderQueue(Protocol):
    """The read and resolve side of ``MotionOrderRepository``."""

    def pending(self, limit: int = 100) -> tuple[MotionOrder, ...]:
        """Pending orders, oldest first."""
        ...

    def resolve(self, order_id: int, outcome: Literal["done", "failed"], now_tick: int) -> bool:
        """Record the outcome; False when it was already resolved."""
        ...


class MotionExecutor:
    """Runs queued orders on a one-shot waypoint driver. Place it before the driver."""

    def __init__(
        self,
        driver: WaypointDriver,
        queue: OrderQueue,
        robot_index: Mapping[str, int],
        timeout_ticks: int,
        packages: PackageModel | None = None,
    ) -> None:
        if driver.loop:
            raise ValueError("the driver must be one-shot so arrival is observable")
        if type(timeout_ticks) is not int or timeout_ticks < 1:
            raise ValueError("timeout must be a positive number of ticks")
        self._driver = driver
        self._queue = queue
        self._index = dict(robot_index)
        self._timeout = timeout_ticks
        self._packages = packages
        self._active: dict[int, tuple[int, int]] = {}

    def system(self) -> System:
        """One poll per tick: close finished orders, then start new ones."""

        def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
            self._close(sim)
            self._start(sim)

        return step

    def _close(self, sim: state.SimState) -> None:
        wp = np.asarray(sim.arrays["script_wp"], dtype=np.int64)
        for order_id, (i, deadline) in sorted(self._active.items()):
            route = self._driver.routes[i]
            if route and int(wp[i]) >= len(route):
                self._queue.resolve(order_id, "done", sim.tick)
            elif sim.tick >= deadline:
                self._driver.routes[i] = []
                self._queue.resolve(order_id, "failed", sim.tick)
            else:
                continue
            del self._active[order_id]

    def _start(self, sim: state.SimState) -> None:
        busy = {i for i, _ in self._active.values()}
        for item in self._queue.pending():
            if item.order_id in self._active:
                continue
            i = self._index.get(item.robot_id)
            order = item.order
            if i is None or i in busy:
                self._queue.resolve(item.order_id, "failed", sim.tick)
                continue
            if order.tool != "move_waypoint":
                self._package_order(sim, item, i)
                continue
            self._driver.routes[i] = [(float(order.x or 0.0), float(order.y or 0.0))]
            wp = sim.arrays["script_wp"]
            wp[i] = 0
            self._active[item.order_id] = (i, sim.tick + self._timeout)
            busy.add(i)

    def _package_order(self, sim: state.SimState, item: MotionOrder, robot: int) -> None:
        """Run a package order on the model and resolve it in the same tick."""
        outcome = False
        order = item.order
        if self._packages is not None and order.package_id is not None:
            if order.tool == "pick_package":
                outcome = self._packages.pick(sim, item.order_id, robot, order.package_id).ok
            elif order.zone_id is not None:
                result = self._packages.deliver(
                    sim, item.order_id, robot, order.package_id, order.zone_id
                )
                outcome = result.ok
        self._queue.resolve(item.order_id, "done" if outcome else "failed", sim.tick)
