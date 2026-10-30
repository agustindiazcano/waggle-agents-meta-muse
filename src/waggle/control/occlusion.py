"""Occlusion boundaries and the phantom human speed cap (ADR-024).

A lidar cannot see behind a rack. Where the range jumps between two neighbouring rays by at least a
pocket deep enough for a person, the nearer return is a boundary: a person could stand just behind
it. The cap assumes such a phantom at the boundary, walking toward the path at the human speed
bound.
Points are in the robot frame: x forward, y left, meters.
"""

import math
from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from waggle.control import envelope, perception
from waggle.control.params import ControlParams, OcclusionParams, PerceptionParams
from waggle.control.types import ControlRequest, Limit, Reason
from waggle.sim.observations import LidarScan
from waggle.sim.params import RobotParams

Points = NDArray[np.float64]

_EPS = 1e-9
_BISECTIONS = 40


def boundary_points(scan: LidarScan, pp: PerceptionParams, op: OcclusionParams) -> Points:
    """The nearer return of every pair of neighbouring rays whose ranges differ by ``jump_min``.

    A ray with no return reads ``max_range``, so the edge of a rack next to open floor is a
    boundary. Dropped rays are filled as in perception, so they do not make a boundary.
    """
    ranges = perception.fill_dropped(np.asarray(scan.ranges, dtype=np.float64), pp.nan_window)
    n = len(ranges)
    angles = scan.angle_min + scan.angle_increment * np.arange(n)
    nxt = np.roll(np.arange(n), -1)
    first = np.arange(n)
    jump = np.abs(ranges[nxt] - ranges)
    pair = jump >= op.jump_min
    if not perception.scan_wraps(scan):
        pair[-1] = False
    near = np.where(ranges[first] <= ranges[nxt], first, nxt)[pair]
    near = np.unique(near)
    return np.column_stack(
        [ranges[near] * np.cos(angles[near]), ranges[near] * np.sin(angles[near])]
    )


def _turning_radius(request: ControlRequest, p: RobotParams, op: OcclusionParams) -> float:
    speed = math.copysign(max(abs(request.speed), op.speed_floor), request.speed)
    return envelope.path_radius(p, speed, request.turn)


def _horizon(p: RobotParams, cp: ControlParams) -> float:
    """Distance beyond which a boundary cannot bind, even at the class maximum speed."""
    reach = cp.human_speed_bound * (p.actuation_delay + p.max_speed / p.decel)
    sep = cp.interp_k * envelope.separation_distance(p, p.max_speed, cp)
    return sep + reach + p.length + p.width + cp.lateral_margin


def _feasible(
    points: Points, p: RobotParams, radius: float, reverse: bool, v: float, cp: ControlParams
) -> bool:
    """True when ``interp_k * S_sep(v)`` fits in the gap to a phantom that can step sideways by the
    distance a person covers while the robot reacts and brakes from ``v``."""
    reach = cp.human_speed_bound * (p.actuation_delay + v / p.decel)
    wide = replace(cp, lateral_margin=cp.lateral_margin + reach)
    gap = envelope.path_gap(points, p, radius, wide, reverse)
    return cp.interp_k * envelope.separation_distance(p, v, cp) <= gap


def occlusion_cap(
    request: ControlRequest,
    p: RobotParams,
    points: Points,
    cp: ControlParams,
    op: OcclusionParams,
) -> float:
    """Largest speed with ``interp_k * S_sep(v)`` at most the gap to the nearest phantom.

    The gap is measured along the swept path of the requested command, widened by how far a person
    walks toward the path at ``v_h`` while the robot reacts and brakes. No feasible speed gives
    zero. A boundary that is not finite fails closed.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] == 0:
        return p.max_speed
    if not np.isfinite(pts).all():
        return 0.0
    pts = pts[np.hypot(pts[:, 0], pts[:, 1]) <= _horizon(p, cp)]
    if pts.shape[0] == 0:
        return p.max_speed
    radius = _turning_radius(request, p, op)
    reverse = request.speed < 0.0
    if not _feasible(pts, p, radius, reverse, 0.0, cp):
        return 0.0
    if _feasible(pts, p, radius, reverse, p.max_speed, cp):
        return p.max_speed
    low, high = 0.0, p.max_speed
    for _ in range(_BISECTIONS):
        mid = (low + high) / 2.0
        if _feasible(pts, p, radius, reverse, mid, cp):
            low = mid
        else:
            high = mid
    return low


def occlusion_limit(
    request: ControlRequest,
    p: RobotParams,
    points: Points,
    cp: ControlParams,
    op: OcclusionParams,
) -> Limit:
    """The occlusion cap as an arbiter limit. A request that does not move is not limited."""
    if not math.isfinite(request.speed) or abs(request.speed) <= _EPS:
        return Limit(p.max_speed, Reason.OCCLUSION)
    return Limit(occlusion_cap(request, p, points, cp, op), Reason.OCCLUSION)
