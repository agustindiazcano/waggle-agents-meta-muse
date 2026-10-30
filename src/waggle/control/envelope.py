"""Stopping and separation envelope along the swept path (ADR-027).

Pure functions. Points are an ``(N, 2)`` array in the robot frame: x forward, y left, meters. A
non-finite point fails closed to a gap of zero. A gap of ``math.inf`` means nothing is in the way.
"""

import math

import numpy as np
from numpy.typing import NDArray

from waggle.control.params import ControlParams
from waggle.sim.params import RobotParams

Points = NDArray[np.float64]

_STRAIGHT_RADIUS = 1e6
_EPS = 1e-9


def stop_distance(p: RobotParams, speed: float) -> float:
    """``S_stop = v*t_r + v^2/(2a)`` in meters."""
    return speed * p.actuation_delay + speed * speed / (2.0 * p.decel)


def separation_distance(p: RobotParams, speed: float, cp: ControlParams) -> float:
    """``S_sep = v_h*(t_r + v/a) + S_stop + C`` in meters."""
    reaction = p.actuation_delay + speed / p.decel
    return cp.human_speed_bound * reaction + stop_distance(p, speed) + cp.human_margin


def _largest_speed(p: RobotParams, room: float, reaction_extra: float) -> float:
    """Largest ``v`` with ``v*t_r + v^2/(2a) + v*extra <= room``, clamped to the class maximum."""
    if room <= 0.0:
        return 0.0
    b = p.actuation_delay + reaction_extra
    speed = p.decel * (-b + math.sqrt(b * b + 2.0 * room / p.decel))
    return min(max(speed, 0.0), p.max_speed)


def human_cap(p: RobotParams, gap: float, cp: ControlParams) -> float:
    """Largest speed with ``interp_k * S_sep(v) <= gap``. A NaN gap gives zero."""
    if math.isnan(gap):
        return 0.0
    if math.isinf(gap):
        return p.max_speed if gap > 0 else 0.0
    constant = cp.human_speed_bound * p.actuation_delay + cp.human_margin
    return _largest_speed(p, gap / cp.interp_k - constant, cp.human_speed_bound / p.decel)


def structure_cap(p: RobotParams, gap: float, cp: ControlParams) -> float:
    """Largest speed with ``S_stop(v) + structure_margin <= gap``. A NaN gap gives zero."""
    if math.isnan(gap):
        return 0.0
    if math.isinf(gap):
        return p.max_speed if gap > 0 else 0.0
    return _largest_speed(p, gap - cp.structure_margin, 0.0)


def path_radius(p: RobotParams, speed: float, turn: float) -> float:
    """Signed radius of the current arc in meters, positive to the left. ``inf`` is straight."""
    if p.kinematics == "bicycle":
        assert p.wheelbase is not None
        tangent = math.tan(turn)
        return math.inf if abs(tangent) < _EPS else p.wheelbase / tangent
    if abs(speed) < _EPS or abs(turn) < _EPS:
        return math.inf
    return speed / turn


def _straight_gap(x: Points, y: Points, half_length: float, half_width: float) -> float:
    ahead = (np.abs(y) <= half_width) & (x >= -half_length)
    if not ahead.any():
        return math.inf
    return float(max(np.min(x[ahead]) - half_length, 0.0))


def _first_forward(alpha: Points, d_low: Points, d_high: Points) -> Points:
    """Smallest non-negative travel angle at which a point is reached, ``inf`` where never."""
    lo_a, hi_a = alpha - d_high, alpha - d_low
    lo_b, hi_b = alpha + d_low, alpha + d_high
    best_a = np.where(hi_a >= 0.0, np.maximum(lo_a, 0.0), np.inf)
    best_b = np.where(hi_b >= 0.0, np.maximum(lo_b, 0.0), np.inf)
    return np.minimum(best_a, best_b)


def _curved_gap(
    x: Points, y: Points, radius: float, half_length: float, half_width: float
) -> float:
    r = abs(radius)
    if radius < 0.0:
        y = -y
    rp = np.maximum(np.hypot(x, y - r), 1e-12)
    far_enough = rp >= r - half_width
    near_enough = np.sqrt(np.maximum(rp * rp - half_length**2, 0.0)) <= r + half_width
    reach = far_enough & near_enough
    if not reach.any():
        return math.inf
    x, y, rp = x[reach], y[reach], rp[reach]
    alpha = np.arctan2(x, r - y)
    d_low = np.arccos(np.minimum(1.0, (r + half_width) / rp))
    d_max = np.where(rp > half_length, np.arcsin(np.minimum(1.0, half_length / rp)), np.pi)
    d_high = np.minimum(d_max, np.arccos(np.clip((r - half_width) / rp, -1.0, 1.0)))
    travel = _first_forward(alpha, d_low, d_high)
    if not np.isfinite(travel).any():
        return math.inf
    return float(np.min(travel) * r)


def path_gap(
    points: Points, p: RobotParams, radius: float, cp: ControlParams, reverse: bool = False
) -> float:
    """Distance in meters the robot can travel along its arc before the footprint, widened by the
    lateral margin, reaches a point. Zero if a point is already inside or not finite."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] == 0:
        return math.inf
    if not np.isfinite(pts).all():
        return 0.0
    x = -pts[:, 0] if reverse else pts[:, 0]
    y = pts[:, 1]
    half_length, half_width = p.length / 2.0, p.width / 2.0 + cp.lateral_margin
    if not math.isfinite(radius) or abs(radius) > _STRAIGHT_RADIUS:
        return _straight_gap(x, y, half_length, half_width)
    return _curved_gap(x, y, radius, half_length, half_width)


def _circumradius(p: RobotParams) -> float:
    return math.hypot(p.length, p.width) / 2.0


def radial_gap(points: Points, p: RobotParams) -> float:
    """Nearest distance to a point minus the circumradius: the 1D radial baseline of E1."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] == 0:
        return math.inf
    if not np.isfinite(pts).all():
        return 0.0
    return float(max(np.min(np.hypot(pts[:, 0], pts[:, 1])) - _circumradius(p), 0.0))


def rotation_blocked(points: Points, p: RobotParams, cp: ControlParams) -> bool:
    """True if a point is inside the circle swept by turning in place, or is not finite."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] == 0:
        return False
    if not np.isfinite(pts).all():
        return True
    reach = _circumradius(p) + cp.lateral_margin
    return bool(np.min(np.hypot(pts[:, 0], pts[:, 1])) <= reach)
