"""Hand-built lidar scans for control tests. Independent of the simulator internals.

Objects are discs ``(cx, cy, r)`` and axis-aligned boxes ``(x0, y0, x1, y1)`` in the robot frame.
"""

import math
from collections.abc import Sequence

import numpy as np

from waggle.sim.observations import LidarScan, RobotOdometry

N_RAYS = 360
MAX_RANGE = 12.0


def _disc_range(dx: np.ndarray, dy: np.ndarray, disc: tuple[float, float, float]) -> np.ndarray:
    cx, cy, r = disc
    b = dx * cx + dy * cy
    c = cx * cx + cy * cy - r * r
    disc_det = b * b - c
    root = np.sqrt(np.maximum(disc_det, 0.0))
    t = b - root
    return np.where((disc_det >= 0.0) & (t > 0.0), t, np.inf)


def _box_range(
    dx: np.ndarray, dy: np.ndarray, box: tuple[float, float, float, float]
) -> np.ndarray:
    x0, y0, x1, y1 = box
    with np.errstate(divide="ignore", invalid="ignore"):
        tx0, tx1 = x0 / dx, x1 / dx
        ty0, ty1 = y0 / dy, y1 / dy
    t_near = np.maximum(np.fmin(tx0, tx1), np.fmin(ty0, ty1))
    t_far = np.minimum(np.fmax(tx0, tx1), np.fmax(ty0, ty1))
    parallel_x = (dx == 0.0) & ((x0 > 0.0) | (x1 < 0.0))
    parallel_y = (dy == 0.0) & ((y0 > 0.0) | (y1 < 0.0))
    hit = (t_near <= t_far) & (t_far > 0.0) & ~parallel_x & ~parallel_y
    return np.where(hit, np.maximum(t_near, 0.0), np.inf)


def make_scan(
    tick: int = 0,
    discs: Sequence[tuple[float, float, float]] = (),
    boxes: Sequence[tuple[float, float, float, float]] = (),
    robot_index: int = 0,
    n_rays: int = N_RAYS,
    max_range: float = MAX_RANGE,
    nan_rays: Sequence[int] = (),
) -> LidarScan:
    """A noiseless scan. A ray with no return reads ``max_range``. ``nan_rays`` are dropped."""
    increment = 2.0 * math.pi / n_rays
    angles = -math.pi + increment * np.arange(n_rays)
    dx, dy = np.cos(angles), np.sin(angles)
    nearest = np.full(n_rays, np.inf)
    for disc in discs:
        nearest = np.minimum(nearest, _disc_range(dx, dy, disc))
    for box in boxes:
        nearest = np.minimum(nearest, _box_range(dx, dy, box))
    ranges = np.where(nearest < max_range, nearest, max_range).astype(np.float64)
    for index in nan_rays:
        ranges[index] = math.nan
    return LidarScan(tick, robot_index, -math.pi, increment, max_range, ranges)


def make_odometry(
    tick: int = 0,
    x: float = 0.0,
    y: float = 0.0,
    theta: float = 0.0,
    speed: float = 0.0,
    angular_speed: float = 0.0,
    robot_index: int = 0,
) -> RobotOdometry:
    """An own-state estimate with no noise."""
    return RobotOdometry(tick, robot_index, x, y, theta, speed, angular_speed)
