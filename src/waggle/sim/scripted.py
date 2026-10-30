"""Waypoint driver for the no-control baseline and for scripted entities.

It has no safety logic and is not the control layer: it steers toward the next waypoint at the
class speed cap and never looks at humans, other robots or zones. It only issues commands, so
the actuation delay, the speed limits and the turning limits of the robot dynamics still apply.
Control never imports this module.
"""

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from waggle.sim import state
from waggle.sim.engine import System
from waggle.sim.robots import RobotFleet

Floats = NDArray[np.float64]
Point = tuple[float, float]
_SLOW_FACTOR = 0.3
_TURN_GAIN = 2.0
_MIN_LOOKAHEAD = 1.0


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class WaypointDriver:
    """Drives each robot through its list of waypoints.

    With ``loop`` true the route repeats and every waypoint reached counts as a task. With
    ``loop`` false the robot stops at the last waypoint, which also counts as one task.
    """

    def __init__(
        self,
        fleet: RobotFleet,
        routes: Sequence[Sequence[Point]],
        loop: bool = True,
        tolerance: float = 0.6,
    ) -> None:
        if len(routes) != fleet.count:
            raise ValueError("one route per robot is required (use an empty route to idle)")
        self.fleet = fleet
        self.routes = [list(route) for route in routes]
        self.loop = loop
        self.tolerance = tolerance

    def initial_arrays(self) -> dict[str, state.Array]:
        """Waypoint index and completed task count per robot."""
        n = self.fleet.count
        return {
            "script_wp": np.zeros(n, dtype=np.int64),
            "script_tasks": np.zeros(n, dtype=np.int64),
        }

    def system(self) -> System:
        """Issue one command per robot every tick."""

        def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
            self._drive(sim)

        return step

    def _drive(self, sim: state.SimState) -> None:
        pose = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        wp = np.asarray(sim.arrays["script_wp"], dtype=np.int64)
        tasks = np.asarray(sim.arrays["script_tasks"], dtype=np.int64)
        commands = np.zeros((self.fleet.count, 2))
        for i, route in enumerate(self.routes):
            if not route:
                continue
            index = int(wp[i])
            if index >= len(route):  # one-shot route finished: stand still
                continue
            tx, ty = route[index]
            dx, dy = tx - pose[i, 0], ty - pose[i, 1]
            distance = math.hypot(dx, dy)
            if distance <= self.tolerance:
                tasks[i] += 1
                wp[i] = (index + 1) % len(route) if self.loop else len(route)
                continue
            error = _wrap(math.atan2(dy, dx) - float(pose[i, 2]))
            speed = float(self.fleet.max_speed[i]) * (1.0 if abs(error) < 0.5 else _SLOW_FACTOR)
            commands[i] = (speed, self._turn(i, error, distance))
        self.fleet.issue(sim, commands)

    def _turn(self, i: int, error: float, distance: float) -> float:
        if self.fleet.is_bicycle[i]:
            lookahead = max(distance, _MIN_LOOKAHEAD)
            return math.atan2(2.0 * float(self.fleet.wheelbase[i]) * math.sin(error), lookahead)
        return _TURN_GAIN * error
