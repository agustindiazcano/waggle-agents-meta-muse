"""Robot dynamics: actuation delay, speed and turn limits, footprints. Control never imports this.

Each robot has a pose (x, y, theta), a speed along its heading and an active command
(speed, turn). A forklift is a bicycle model: the turn command is a steering angle and the
yaw rate is ``v * tan(steer) / wheelbase``, so it cannot turn tighter than its minimum radius.
The other classes are differential drives: the turn command is a yaw rate, limited by the
maximum angular speed. A command issued at tick t becomes active at tick t + delay_ticks.

Integration is explicit Euler: position and heading advance with the speed and heading at the
start of the tick, then the speed moves toward the command by at most ``decel * dt``. The
simulated stopping distance then differs from ``v*t_r + v^2/(2a)`` by at most
``v*dt/2 + a*dt^2/2`` (derivation in ADR-021).
"""

import itertools
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from waggle.sim import params, state
from waggle.sim.engine import System
from waggle.sim.params import DT, RobotKind, RobotParams

Floats = NDArray[np.float64]


def _f(sim: state.SimState, name: str) -> Floats:
    return np.asarray(sim.arrays[name], dtype=np.float64)


def _i(sim: state.SimState, name: str) -> NDArray[np.int64]:
    return np.asarray(sim.arrays[name], dtype=np.int64)


class RobotFleet:
    """Parameters of N robots and the functions that build, command and step their state."""

    def __init__(
        self,
        kinds: Sequence[RobotKind | RobotParams],
        load_raised: Sequence[bool] | None = None,
    ) -> None:
        self.params: list[RobotParams] = [
            params.ROBOT_PARAMS[k] if isinstance(k, RobotKind) else k for k in kinds
        ]
        raised = list(load_raised) if load_raised is not None else [False] * len(self.params)
        if len(raised) != len(self.params):
            raise ValueError("load_raised needs one flag per robot")
        for p, flag in zip(self.params, raised, strict=True):
            if flag and p.kind is not RobotKind.FORKLIFT:
                raise ValueError("load_raised applies to the forklift only")
        n = len(self.params)
        scale_v = np.array(
            [params.LOAD_RAISED_SPEED_FACTOR if r else 1.0 for r in raised], dtype=np.float64
        )
        scale_a = np.array(
            [params.LOAD_RAISED_DECEL_FACTOR if r else 1.0 for r in raised], dtype=np.float64
        )
        self.max_speed: Floats = np.array([p.max_speed for p in self.params]) * scale_v
        self.decel: Floats = np.array([p.decel for p in self.params]) * scale_a
        self.delay: NDArray[np.int64] = np.array([p.delay_ticks for p in self.params], np.int64)
        self.is_bicycle = np.array([p.kinematics == "bicycle" for p in self.params], dtype=bool)
        self.wheelbase: Floats = np.array([p.wheelbase or 1.0 for p in self.params])
        self.max_steer: Floats = np.array([p.max_steer or 0.0 for p in self.params])
        self.max_angular: Floats = np.array([p.max_angular_speed or 0.0 for p in self.params])
        self.ring = int(self.delay.max()) + 1 if n else 1
        self.count = n

    def initial_arrays(self, poses: Floats, speeds: Floats | None = None) -> dict[str, state.Array]:
        """State arrays for the fleet. ``poses`` is (N, 3): x, y, theta."""
        pose = np.ascontiguousarray(poses, dtype=np.float64)
        if pose.shape != (self.count, 3):
            raise ValueError(f"poses must have shape ({self.count}, 3)")
        speed = (
            np.zeros(self.count)
            if speeds is None
            else np.ascontiguousarray(speeds, dtype=np.float64)
        )
        if speed.shape != (self.count,):
            raise ValueError("speeds must have one value per robot")
        return {
            "robot_pose": pose,
            "robot_speed": speed,
            "robot_active": np.zeros((self.count, 2)),
            "robot_pending": np.zeros((self.count, self.ring, 2)),
            "robot_pending_valid": np.zeros((self.count, self.ring), dtype=np.int64),
        }

    def issue(
        self, sim: state.SimState, commands: Floats, mask: NDArray[np.bool_] | None = None
    ) -> None:
        """Queue one (speed, turn) command per robot. It becomes active after the robot's delay."""
        cmd = np.asarray(commands, dtype=np.float64)
        if cmd.shape != (self.count, 2) or not np.all(np.isfinite(cmd)):
            raise ValueError("commands must be a finite (N, 2) array")
        chosen = np.ones(self.count, dtype=bool) if mask is None else mask
        slots = (sim.tick + self.delay) % self.ring
        pending, valid = _f(sim, "robot_pending"), _i(sim, "robot_pending_valid")
        rows = np.nonzero(chosen)[0]
        pending[rows, slots[rows]] = cmd[rows]
        valid[rows, slots[rows]] = 1

    def system(self) -> System:
        """The per-tick dynamics as an engine system."""

        def step(sim: state.SimState, rngs: object) -> None:
            self._step(sim)

        return step

    def _step(self, sim: state.SimState) -> None:
        pose, speed, active = _f(sim, "robot_pose"), _f(sim, "robot_speed"), _f(sim, "robot_active")
        pending, valid = _f(sim, "robot_pending"), _i(sim, "robot_pending_valid")
        slot = sim.tick % self.ring
        due = valid[:, slot] == 1
        active[due] = pending[due, slot]
        valid[due, slot] = 0

        speed_cmd = np.clip(active[:, 0], 0.0, self.max_speed)
        turn = active[:, 1]
        steer = np.clip(turn, -self.max_steer, self.max_steer)
        omega = np.where(
            self.is_bicycle,
            speed * np.tan(steer) / self.wheelbase,
            np.clip(turn, -self.max_angular, self.max_angular),
        )
        theta = pose[:, 2]
        pose[:, 0] += speed * np.cos(theta) * DT
        pose[:, 1] += speed * np.sin(theta) * DT
        pose[:, 2] = (theta + omega * DT + np.pi) % (2 * np.pi) - np.pi
        change = np.clip(speed_cmd - speed, -self.decel * DT, self.decel * DT)
        speed[:] = np.clip(speed + change, 0.0, self.max_speed)


def footprint_corners(p: RobotParams, x: float, y: float, theta: float) -> Floats:
    """The four corners of the oriented rectangle, counter-clockwise, in meters."""
    half_l, half_w = p.length / 2, p.width / 2
    local = np.array([[half_l, -half_w], [half_l, half_w], [-half_l, half_w], [-half_l, -half_w]])
    c, s = np.cos(theta), np.sin(theta)
    rotation = np.array([[c, -s], [s, c]])
    return np.asarray(local @ rotation.T + np.array([x, y]), dtype=np.float64)


def _hull(points: Floats) -> Floats:
    """Convex hull, counter-clockwise (Andrew's monotone chain)."""
    pts = sorted({(float(a), float(b)) for a, b in points})
    if len(pts) <= 2:
        return np.array(pts, dtype=np.float64)

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.array(lower[:-1] + upper[:-1], dtype=np.float64)


def swept_footprint(p: RobotParams, poses: Floats) -> list[Floats]:
    """The area swept along a path, as one convex polygon per consecutive pair of poses.

    Each piece is the convex hull of the footprint at pose i and at pose i + 1. Over a short
    step this is the swept area up to the chord error of the rotation. The detector (B6) takes
    these polygons.
    """
    path = np.asarray(poses, dtype=np.float64)
    if path.ndim != 2 or path.shape[1] != 3 or len(path) < 2:
        raise ValueError("a swept footprint needs at least two poses of shape (k, 3)")
    pieces: list[Floats] = []
    for a, b in itertools.pairwise(path):
        both = np.vstack([footprint_corners(p, *a), footprint_corners(p, *b)])
        pieces.append(_hull(both))
    return pieces
