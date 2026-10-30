"""Control in the loop for E1: sensors, ``control_step`` and the command override.

The rig is an engine system that runs right after the waypoint driver. The driver writes the
requested command of every robot into the actuation ring. The rig reads it back, builds the
sensor inputs from ground truth (this is the only place ground truth meets the control code, and
only through a ``LidarScan``, a ``RobotOdometry`` and ``BeaconReport`` items), calls
``control_step`` and writes the limited command over the requested one. The code latency of
``control_step`` is measured here with a monotonic timer, outside the call (ADR-028).
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field, replace

import numpy as np
from numpy.typing import NDArray

from waggle.control.step import ControlInputs, ControlState, control_step
from waggle.control.types import ControlRequest
from waggle.experiments.e1_config import FALSE_STOP_GAP_M, E1Config, Sensing
from waggle.sim import sensors, state, world
from waggle.sim.engine import System
from waggle.sim.observations import LidarScan
from waggle.sim.params import HUMAN_RADIUS
from waggle.sim.robots import RobotFleet, footprint_corners
from waggle.sim.sensors import BeaconConfig, LidarConfig, OdometryNoise

Floats = NDArray[np.float64]
_MOVING = 1e-9


@dataclass
class Tally:
    """What the rig counts during one run."""

    control_calls: int = 0
    stop_episodes: dict[str, int] = field(default_factory=dict)
    false_stops: int = 0
    latency_us: list[float] = field(default_factory=list)


def streams_for(config: E1Config, robots: int) -> dict[str, int]:
    """The extra random streams a configuration needs: one per robot and sensor."""
    if not config.controlled:
        return {}
    extra = {"robots": robots}
    if config.sensing is Sensing.LIDAR:
        extra["lidar"] = robots
    if config.beacons:
        extra["beacons"] = robots
    return extra


class ControlRig:
    """Runs ``control_step`` for every robot every tick and applies the limited commands."""

    def __init__(self, config: E1Config, fleet: RobotFleet, box: world.World) -> None:
        self.config = config
        self.fleet = fleet
        self.static = sensors.static_segments(box)
        self.lidar = LidarConfig()
        self.noise = OdometryNoise()
        self.beacon_config = BeaconConfig(enabled=True)
        # The fleet scales speed and braking for a raised load. The control code is given the
        # same figures, otherwise it would assume a braking the robot does not have.
        self.params = [
            replace(p, max_speed=float(fleet.max_speed[i]), decel=float(fleet.decel[i]))
            for i, p in enumerate(fleet.params)
        ]
        self.states = [ControlState() for _ in fleet.params]
        self.scans: list[LidarScan | None] = [None] * fleet.count
        self.history: deque[Floats] = deque(maxlen=self.beacon_config.delay_ticks + 1)
        self.stopped = [False] * fleet.count
        self.tally = Tally()

    def system(self) -> System:
        """The rig as an engine system. Insert it right after the driver."""

        def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
            self._step(sim, rngs)

        return step

    def _scan(
        self,
        i: int,
        tick: int,
        poses: Floats,
        discs: Floats,
        rngs: dict[str, np.random.Generator],
    ) -> LidarScan:
        others = [footprint_corners(self.params[j], *poses[j]) for j in range(len(poses)) if j != i]
        boxes = np.array(others, dtype=np.float64).reshape(-1, 4, 2)
        if self.config.sensing is Sensing.ORACLE:
            return sensors.oracle_scan(self.static, discs, boxes, poses[i], self.lidar, tick, i)
        return sensors.lidar_scan(
            self.static, discs, boxes, poses[i], self.lidar, rngs[f"lidar/{i}"], tick, i
        )

    def _yaw_rate(self, i: int, speed: float, turn: float) -> float:
        if self.fleet.is_bicycle[i]:
            steer = float(np.clip(turn, -self.fleet.max_steer[i], self.fleet.max_steer[i]))
            return speed * math.tan(steer) / float(self.fleet.wheelbase[i])
        return float(np.clip(turn, -self.fleet.max_angular[i], self.fleet.max_angular[i]))

    def _count_stop(
        self, i: int, requested: float, limited: float, reason: str, humans: Floats, xy: Floats
    ) -> None:
        """Count a stop episode when a moving request first meets a zero limit.

        The true gap to the nearest human is read from ground truth for the count only. It never
        reaches the control code. Centre distance minus the human radius is larger than the gap
        to the robot footprint, so the false stop count errs on the high side.
        """
        stopped = abs(requested) > _MOVING and limited <= _MOVING
        if stopped and not self.stopped[i]:
            counts = self.tally.stop_episodes
            counts[reason] = counts.get(reason, 0) + 1
            gap = (
                float(np.min(np.hypot(*(humans - xy).T))) - HUMAN_RADIUS
                if len(humans)
                else math.inf
            )
            if gap > FALSE_STOP_GAP_M:
                self.tally.false_stops += 1
        self.stopped[i] = stopped

    def _step(self, sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        tick = sim.tick
        poses = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        speeds = np.asarray(sim.arrays["robot_speed"], dtype=np.float64)
        active = np.asarray(sim.arrays["robot_active"], dtype=np.float64)
        pending = np.asarray(sim.arrays["robot_pending"], dtype=np.float64)
        humans = np.asarray(sim.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
        self.history.append(humans.copy())
        discs = np.column_stack([humans, np.full(len(humans), HUMAN_RADIUS)])
        refresh = sensors.lidar_due(tick)
        commands = np.zeros((self.fleet.count, 2))
        for i in range(self.fleet.count):
            if refresh:
                self.scans[i] = self._scan(i, tick, poses, discs, rngs)
            slot = (tick + int(self.fleet.delay[i])) % self.fleet.ring
            requested = pending[i, slot]
            odometry = sensors.odometry(
                tick,
                i,
                poses[i],
                float(speeds[i]),
                self._yaw_rate(i, float(speeds[i]), float(active[i, 1])),
                self.noise,
                rngs[f"robots/{i}"],
            )
            beacons = (
                sensors.beacon_reports(
                    tick,
                    i,
                    poses[i, :2],
                    list(self.history),
                    self.beacon_config,
                    rngs[f"beacons/{i}"],
                )
                if self.config.beacons
                else ()
            )
            inputs = ControlInputs(
                request=ControlRequest(float(requested[0]), float(requested[1])),
                params=self.params[i],
                tick=tick,
                odometry=odometry,
                scan=self.scans[i],
                beacons=beacons,
                mode=self.config.mode,
                use_occlusion=self.config.occlusion,
                use_cpa=self.config.cpa,
            )
            started = time.perf_counter_ns()
            self.states[i], out = control_step(self.states[i], inputs)
            self.tally.latency_us.append((time.perf_counter_ns() - started) / 1000.0)
            self.tally.control_calls += 1
            commands[i] = (out.speed, out.turn)
            self._count_stop(
                i, float(requested[0]), out.speed, out.reason.value, humans, poses[i, :2]
            )
        self.fleet.issue(sim, commands)
