"""Scan checks, dropped rays and clusters (ADR-026).

Everything is in the robot frame: x forward, y to the left, meters. A scan that cannot be trusted
is reported with a reason, never repaired silently.
"""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from waggle.control.params import PerceptionParams
from waggle.control.types import Reason
from waggle.sim.observations import LidarScan, RobotOdometry

_NO_RETURN_MARGIN = 1e-6
_FULL_CIRCLE_TOLERANCE = 1e-6
_EXACT_EXTENT_LIMIT = 400


@dataclass(frozen=True)
class Cluster:
    """A group of neighbouring returns: points in the robot frame and the largest distance
    between two of them."""

    points: NDArray[np.float64]
    extent: float


def _scan_is_well_formed(scan: LidarScan) -> bool:
    ranges = np.asarray(scan.ranges)
    return bool(
        ranges.ndim == 1
        and ranges.size > 0
        and math.isfinite(scan.angle_min)
        and math.isfinite(scan.angle_increment)
        and scan.angle_increment > 0.0
        and math.isfinite(scan.max_range)
        and scan.max_range > 0.0
    )


def _dropped(ranges: NDArray[np.float64]) -> NDArray[np.bool_]:
    return ~np.isfinite(ranges) | (ranges < 0.0)


def check_inputs(
    scan: LidarScan | None, odometry: RobotOdometry | None, tick: int, pp: PerceptionParams
) -> Reason | None:
    """The reason the inputs cannot be used this tick, or None when they are valid.

    Missing or stale odometry is ``INPUT_MISSING``. A missing, malformed, stale, future or mostly
    dropped scan is ``SCAN_INVALID``.
    """
    if odometry is None or not 0 <= tick - odometry.tick <= pp.max_scan_age_ticks:
        return Reason.INPUT_MISSING
    if scan is None or not _scan_is_well_formed(scan):
        return Reason.SCAN_INVALID
    if not 0 <= tick - scan.tick <= pp.max_scan_age_ticks:
        return Reason.SCAN_INVALID
    if float(np.mean(_dropped(np.asarray(scan.ranges, dtype=np.float64)))) > pp.max_nan_fraction:
        return Reason.SCAN_INVALID
    return None


def _nearest_valid(
    ranges: NDArray[np.float64], bad: NDArray[np.bool_], i: int, step: int, window: int
) -> float | None:
    for offset in range(1, window + 1):
        j = i + step * offset
        if 0 <= j < len(ranges) and not bad[j]:
            return float(ranges[j])
    return None


def fill_dropped(ranges: NDArray[np.float64], window: int) -> NDArray[np.float64]:
    """Replace each dropped ray by the smaller of its nearest valid neighbours within ``window``.

    With a valid neighbour on one side only it takes that one. With none it takes zero, which puts
    a point at the robot. A dropped ray can only make an obstacle look closer.
    """
    values = np.asarray(ranges, dtype=np.float64)
    bad = _dropped(values)
    filled = np.where(bad, 0.0, values)
    for i in np.flatnonzero(bad):
        sides = [
            r
            for r in (
                _nearest_valid(values, bad, int(i), -1, window),
                _nearest_valid(values, bad, int(i), 1, window),
            )
            if r is not None
        ]
        filled[i] = min(sides) if sides else 0.0
    return filled


def _extent(points: NDArray[np.float64]) -> float:
    if len(points) < 2:
        return 0.0
    if len(points) <= _EXACT_EXTENT_LIMIT:
        diff = points[:, None, :] - points[None, :, :]
        return float(np.sqrt(np.max(np.sum(diff * diff, axis=2))))
    low, high = points.min(axis=0), points.max(axis=0)
    return float(np.hypot(*(high - low)))


def _runs(linked: NDArray[np.bool_], returns: NDArray[np.bool_], wraps: bool) -> list[list[int]]:
    """Groups of consecutive linked returns, the last joined to the first on a full circle."""
    groups: list[list[int]] = []
    current: list[int] = []
    for i in range(len(returns)):
        if not returns[i]:
            if current:
                groups.append(current)
                current = []
            continue
        if current and not linked[i - 1]:
            groups.append(current)
            current = []
        current.append(i)
    if current:
        groups.append(current)
    joins = wraps and len(groups) > 1 and groups[0][0] == 0 and groups[-1][-1] == len(returns) - 1
    if joins and linked[-1]:
        groups[0] = groups.pop() + groups[0]
    return groups


def scan_wraps(scan: LidarScan) -> bool:
    """True when the last ray is the neighbour of the first, a scan over the full circle."""
    n = len(scan.ranges)
    return abs(scan.angle_increment * n - 2.0 * math.pi) < (
        _FULL_CIRCLE_TOLERANCE + scan.angle_increment * 0.5
    )


def clusters_from_scan(scan: LidarScan, pp: PerceptionParams) -> list[Cluster]:
    """Group the returns of a valid scan into clusters in the robot frame."""
    ranges = fill_dropped(np.asarray(scan.ranges, dtype=np.float64), pp.nan_window)
    n = len(ranges)
    angles = scan.angle_min + scan.angle_increment * np.arange(n)
    points = np.column_stack([ranges * np.cos(angles), ranges * np.sin(angles)])
    returns = ranges < scan.max_range - _NO_RETURN_MARGIN
    nxt = np.roll(np.arange(n), -1)
    dist = np.hypot(*(points[nxt] - points).T)
    near = np.minimum(ranges, ranges[nxt])
    linked = returns & returns[nxt] & (dist <= pp.gap_base + pp.gap_per_meter * near)
    groups = _runs(linked, returns, scan_wraps(scan))
    return [Cluster(points[g], _extent(points[g])) for g in groups]


def is_human_candidate(cluster: Cluster, pp: PerceptionParams) -> bool:
    """True when the cluster is small enough to be a person. Larger ones are structures."""
    return cluster.extent <= pp.human_max_extent
