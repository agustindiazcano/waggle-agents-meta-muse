"""Simulated lidar, odometry and human beacons. Control never imports this module.

The lidar is a pure function over geometry arrays: the static map as segments, the dynamic
footprints (human discs and other robots' rectangles), the robot pose, a configuration and a
random generator. It reads ground truth and returns the ``LidarScan`` that control may see.
The random draws are fixed per scan (one noise value and one dropout value per ray), so the
stream advances the same amount whatever the geometry is. Rays that hit nothing within range
return ``max_range``. Dropped rays return NaN. Defaults are assumptions to calibrate.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from waggle.sim import world
from waggle.sim.observations import BeaconReport, LidarScan, RobotOdometry
from waggle.sim.params import LIDAR_PERIOD_TICKS

Floats = NDArray[np.float64]
_PARALLEL = 1e-12


@dataclass(frozen=True)
class LidarConfig:
    """Lidar parameters: 360 rays, 12 m range, 2 cm range noise, 1 percent dropout."""

    n_rays: int = 360
    max_range: float = 12.0
    range_sigma: float = 0.02
    dropout_probability: float = 0.01

    def __post_init__(self) -> None:
        if self.n_rays < 1 or self.max_range <= 0 or self.range_sigma < 0:
            raise ValueError("n_rays >= 1, max_range > 0 and range_sigma >= 0 are required")
        if not 0.0 <= self.dropout_probability <= 1.0:
            raise ValueError("dropout_probability must be between 0 and 1")


@dataclass(frozen=True)
class OdometryNoise:
    """Standard deviations of the own-state estimate (assumptions)."""

    position_sigma: float = 0.02
    heading_sigma: float = 0.005
    speed_sigma: float = 0.02


@dataclass(frozen=True)
class BeaconConfig:
    """Human beacons: off by default. Position noise in meters, delay in ticks, range in meters."""

    enabled: bool = False
    position_sigma: float = 0.10
    delay_ticks: int = 4
    max_range: float = 30.0


def lidar_due(tick: int) -> bool:
    """True on the ticks where the lidar scans (every ``LIDAR_PERIOD_TICKS`` ticks, 10 Hz)."""
    return tick % LIDAR_PERIOD_TICKS == 0


def _polygon_segments(points: Sequence[Sequence[float]]) -> list[list[float]]:
    closed = [*points, points[0]]
    return [[a[0], a[1], b[0], b[1]] for a, b in itertools.pairwise(closed)]


def static_segments(box: world.World) -> Floats:
    """The static map as an (S, 4) array of segments: walls, racks and the four bounds edges."""
    segments: list[list[float]] = []
    for polygon in (*box.walls, *box.racks):
        segments += _polygon_segments(polygon.points)
    x0, y0, x1, y1 = box.bounds
    segments += _polygon_segments([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    return np.array(segments, dtype=np.float64).reshape(-1, 4)


def _cross(a: Floats, b: Floats) -> Floats:
    return np.asarray(a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0], dtype=np.float64)


def _segment_hits(origin: Floats, dirs: Floats, segments: Floats) -> Floats:
    """Distance along each ray to the nearest segment, infinity when there is none."""
    if len(segments) == 0:
        return np.full(len(dirs), np.inf)
    start, edge = segments[:, :2], segments[:, 2:] - segments[:, :2]
    to_start = start - origin  # (S, 2)
    d = dirs[:, None, :]  # (R, 1, 2)
    denom = _cross(d, edge[None, :, :])  # (R, S)
    safe = np.where(np.abs(denom) < _PARALLEL, np.nan, denom)
    t = _cross(to_start[None, :, :], edge[None, :, :]) / safe
    u = _cross(to_start[None, :, :], d) / safe
    valid = (t >= 0.0) & (u >= 0.0) & (u <= 1.0)
    return np.asarray(np.min(np.where(valid, t, np.inf), axis=1), dtype=np.float64)


def _disc_hits(origin: Floats, dirs: Floats, discs: Floats) -> Floats:
    if len(discs) == 0:
        return np.full(len(dirs), np.inf)
    rel = origin - discs[:, :2]  # (M, 2)
    b = dirs @ rel.T  # (R, M)
    c = np.sum(rel * rel, axis=1) - discs[:, 2] ** 2  # (M,)
    disc = b * b - c[None, :]
    root = np.sqrt(np.where(disc >= 0.0, disc, np.nan))
    t = -b - root
    valid = (disc >= 0.0) & (t >= 0.0)
    return np.asarray(np.min(np.where(valid, t, np.inf), axis=1), dtype=np.float64)


def lidar_scan(
    static: Floats,
    discs: Floats,
    boxes: Floats,
    pose: Floats,
    config: LidarConfig,
    rng: np.random.Generator,
    tick: int = 0,
    robot_index: int = 0,
) -> LidarScan:
    """One scan from ``pose`` (x, y, theta).

    ``static`` is (S, 4) segments, ``discs`` is (M, 3) with x, y, radius, and ``boxes`` is
    (K, 4, 2) rectangle corners of the other robots. The robot's own footprint is not passed.
    """
    angle_increment = 2 * math.pi / config.n_rays
    local = -math.pi + angle_increment * np.arange(config.n_rays)
    angles = local + pose[2]
    dirs = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    origin = np.asarray(pose[:2], dtype=np.float64)
    box_segments = (
        np.array([_polygon_segments(corners.tolist()) for corners in boxes]).reshape(-1, 4)
        if len(boxes)
        else np.zeros((0, 4))
    )
    nearest = np.minimum(
        _segment_hits(origin, dirs, np.vstack([static, box_segments])),
        _disc_hits(origin, dirs, discs),
    )
    noise = rng.normal(0.0, 1.0, size=config.n_rays)
    dropped = rng.random(config.n_rays) < config.dropout_probability
    returned = nearest < config.max_range
    ranges = np.where(returned, nearest + config.range_sigma * noise, config.max_range)
    ranges = np.clip(ranges, 0.0, config.max_range)
    ranges = np.where(dropped, np.nan, ranges)
    return LidarScan(
        tick=tick,
        robot_index=robot_index,
        angle_min=-math.pi,
        angle_increment=angle_increment,
        max_range=config.max_range,
        ranges=np.asarray(ranges, dtype=np.float64),
    )


def odometry(
    tick: int,
    robot_index: int,
    pose: Floats,
    speed: float,
    angular_speed: float,
    noise: OdometryNoise,
    rng: np.random.Generator,
) -> RobotOdometry:
    """The robot's noisy own-state estimate. Five normal draws per call, always."""
    draws = rng.normal(0.0, 1.0, size=5)
    return RobotOdometry(
        tick=tick,
        robot_index=robot_index,
        x=float(pose[0] + noise.position_sigma * draws[0]),
        y=float(pose[1] + noise.position_sigma * draws[1]),
        theta=float(pose[2] + noise.heading_sigma * draws[2]),
        speed=float(speed + noise.speed_sigma * draws[3]),
        angular_speed=float(angular_speed + noise.heading_sigma * draws[4]),
    )


def beacon_reports(
    tick: int,
    robot_index: int,
    robot_xy: Floats,
    history: Sequence[Floats],
    config: BeaconConfig,
    rng: np.random.Generator,
) -> tuple[BeaconReport, ...]:
    """Human beacon positions as the robot receives them, around corners (no occlusion).

    ``history`` holds the human positions (M, 2) of past ticks, most recent last. The report
    uses the position ``delay_ticks`` ticks ago, or the oldest one when the history is shorter.
    Beacons beyond ``max_range`` are not heard. Two normal draws per human, always.
    """
    if not config.enabled or not history:
        return ()
    index = max(0, len(history) - 1 - config.delay_ticks)
    positions = np.asarray(history[index], dtype=np.float64)
    noise = rng.normal(0.0, 1.0, size=positions.shape)
    reports: list[BeaconReport] = []
    for human, (pos, jitter) in enumerate(zip(positions, noise, strict=True)):
        if float(np.hypot(*(pos - robot_xy))) > config.max_range:
            continue
        noisy = pos + config.position_sigma * jitter
        reports.append(
            BeaconReport(
                tick=tick,
                robot_index=robot_index,
                human_index=human,
                x=float(noisy[0]),
                y=float(noisy[1]),
                delay_ticks=config.delay_ticks,
            )
        )
    return tuple(reports)
