"""Closest point of approach: a constant velocity prediction that can only restrict (ADR-018).

Each track with a velocity estimate is walked forward at constant velocity while the robot follows
the arc of its requested command at the requested speed. The first time the person is inside the
footprint widened by the body radius and the lateral margin is the predicted meeting. The speed cap
leaves room to stop before it. A track without a velocity, or not seen recently, adds nothing: the
envelope (ADR-027) stays the floor. World frame, meters and seconds.
"""

import math

import numpy as np
from numpy.typing import NDArray

from waggle.control import envelope, tracking
from waggle.control.params import ControlParams, CpaParams, PerceptionParams
from waggle.control.tracking import Track
from waggle.control.types import ControlRequest, Limit, Reason
from waggle.sim.observations import RobotOdometry
from waggle.sim.params import DT, RobotParams

_EPS = 1e-9
_STRAIGHT_RADIUS = 1e6

Floats = NDArray[np.float64]


def _robot_poses(
    odom: RobotOdometry, radius: float, direction: float, travelled: Floats
) -> tuple[Floats, Floats, Floats]:
    """Position and heading of the robot after each travelled distance along its arc."""
    if not math.isfinite(radius) or abs(radius) > _STRAIGHT_RADIUS:
        s = direction * travelled
        return (
            odom.x + math.cos(odom.theta) * s,
            odom.y + math.sin(odom.theta) * s,
            np.full_like(s, odom.theta),
        )
    centre_x = odom.x - radius * math.sin(odom.theta)
    centre_y = odom.y + radius * math.cos(odom.theta)
    heading = odom.theta + direction * travelled / radius
    return centre_x + radius * np.sin(heading), centre_y - radius * np.cos(heading), heading


def _meeting_time(
    track: Track,
    velocity: tuple[float, float],
    request: ControlRequest,
    p: RobotParams,
    odom: RobotOdometry,
    tick: int,
    cp: ControlParams,
    cpap: CpaParams,
) -> float | None:
    """First time in seconds the person is inside the widened footprint, or None."""
    age = max(tick - track.seen_tick, 0) * DT
    steps = math.ceil(cpap.horizon / cpap.step)
    times = np.arange(steps + 1, dtype=np.float64) * cpap.step
    px = track.x + velocity[0] * (age + times)
    py = track.y + velocity[1] * (age + times)
    radius = envelope.path_radius(p, request.speed, request.turn)
    direction = math.copysign(1.0, request.speed)
    rx, ry, heading = _robot_poses(odom, radius, direction, abs(request.speed) * times)
    dx, dy = px - rx, py - ry
    local_x = np.cos(heading) * dx + np.sin(heading) * dy
    local_y = -np.sin(heading) * dx + np.cos(heading) * dy
    widen = max(track.body_radius, 0.0) + cp.lateral_margin
    inside = (np.abs(local_x) <= p.length / 2 + widen) & (np.abs(local_y) <= p.width / 2 + widen)
    if not inside.any():
        return None
    return float(times[int(np.argmax(inside))])


def cpa_limit(
    request: ControlRequest,
    p: RobotParams,
    odom: RobotOdometry,
    tracks: tuple[Track, ...],
    tick: int,
    cp: ControlParams,
    pp: PerceptionParams,
    cpap: CpaParams,
) -> Limit:
    """Speed cap that leaves ``S_stop`` plus the structure margin before the nearest predicted
    meeting. A request that does not move is not limited. A track that is not finite gives zero."""
    if not math.isfinite(request.speed) or abs(request.speed) <= _EPS:
        return Limit(p.max_speed, Reason.CPA)
    cap = p.max_speed
    for track in tracks:
        if not all(math.isfinite(v) for v in (track.x, track.y, track.body_radius)):
            return Limit(0.0, Reason.CPA)
        if tick - track.seen_tick > pp.max_scan_age_ticks:
            continue
        velocity = tracking.smoothed_velocity(track, pp)
        if velocity is None:
            continue
        meeting = _meeting_time(track, velocity, request, p, odom, tick, cp, cpap)
        if meeting is not None:
            room = abs(request.speed) * meeting
            cap = min(cap, envelope.structure_cap(p, room, cp))
    return Limit(cap, Reason.CPA)
