"""Reflex limits: heartbeat watchdog, e-stop, hazard geofences and telemetry thresholds (ADR-027).

Each function returns a limit for the arbiter. None of them reads a model or a map: a geofence is a
polygon in the world frame given by the caller, and a telemetry reading is a number against two
thresholds. A missing or malformed input stops the robot.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from waggle.control import envelope, frames
from waggle.control.params import ControlParams, ReflexParams
from waggle.control.types import ControlRequest, Limit, Reason
from waggle.sim.observations import RobotOdometry
from waggle.sim.params import RobotParams

Points = NDArray[np.float64]

_EPS = 1e-9


@dataclass(frozen=True)
class Geofence:
    """A hazard polygon in the world frame that motion commands may not enter."""

    fence_id: str
    vertices: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class TelemetryReading:
    """A machine or robot reading at a world position, against its warning and critical limits."""

    source_id: str
    x: float
    y: float
    value: float
    warn: float
    critical: float


def watchdog_limit(heartbeat_tick: int | None, tick: int, rp: ReflexParams) -> Limit | None:
    """Zero speed when the heartbeat is missing, older than the timeout or from the future."""
    if heartbeat_tick is None or not 0 <= tick - heartbeat_tick <= rp.heartbeat_timeout_ticks:
        return Limit(0.0, Reason.WATCHDOG)
    return None


def estop_limit(estop: bool) -> Limit | None:
    """Zero speed while the emergency stop is active."""
    return Limit(0.0, Reason.ESTOP) if estop else None


def _circle(reading: TelemetryReading, radius: float, rp: ReflexParams) -> Geofence:
    """A polygon that contains the disc of ``radius`` around the reading."""
    outer = radius / math.cos(math.pi / rp.polygon_sides)
    angles = 2.0 * math.pi * np.arange(rp.polygon_sides) / rp.polygon_sides
    vertices = tuple(
        (reading.x + outer * math.cos(a), reading.y + outer * math.sin(a)) for a in angles
    )
    return Geofence(f"telemetry:{reading.source_id}", vertices)


def telemetry_geofences(
    readings: Sequence[TelemetryReading], rp: ReflexParams
) -> tuple[Geofence, ...]:
    """A hazard geofence around every reading over its warning limit.

    A reading over the critical limit, or one that is not a number, gets the larger radius.
    """
    fences = []
    for reading in readings:
        if math.isnan(reading.value) or reading.value >= reading.critical:
            fences.append(_circle(reading, rp.critical_radius, rp))
        elif reading.value >= reading.warn:
            fences.append(_circle(reading, rp.warn_radius, rp))
    return tuple(fences)


def _well_formed(fence: Geofence) -> bool:
    return len(fence.vertices) >= 3 and all(
        math.isfinite(x) and math.isfinite(y) for x, y in fence.vertices
    )


def boundary_samples(fence: Geofence, rp: ReflexParams) -> Points:
    """Points along the polygon edges at most ``edge_spacing`` apart, in the world frame."""
    corners = np.asarray(fence.vertices, dtype=np.float64)
    pieces = []
    for start, end in zip(corners, np.roll(corners, -1, axis=0), strict=True):
        count = max(math.ceil(float(np.hypot(*(end - start))) / rp.edge_spacing), 1)
        fractions = np.arange(count) / count
        pieces.append(start + fractions[:, None] * (end - start))
    return np.vstack(pieces)


def _contains(fence: Geofence, x: float, y: float) -> bool:
    """Even-odd test of a point against the polygon."""
    inside = False
    corners = fence.vertices
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def geofence_limit(
    request: ControlRequest,
    p: RobotParams,
    odom: RobotOdometry,
    fences: Sequence[Geofence],
    cp: ControlParams,
    rp: ReflexParams,
) -> Limit:
    """Speed cap that stops the robot before a geofence along its swept path.

    A robot whose footprint already touches a fence may only creep at ``escape_speed``, so it can
    leave. A malformed fence stops the robot. A request that does not move is not limited.
    """
    if not math.isfinite(request.speed) or abs(request.speed) <= _EPS:
        return Limit(p.max_speed, Reason.GEOFENCE)
    radius = envelope.path_radius(p, request.speed, request.turn)
    reverse = request.speed < 0.0
    cap = p.max_speed
    for fence in fences:
        if not _well_formed(fence):
            return Limit(0.0, Reason.GEOFENCE)
        local = frames.to_robot(boundary_samples(fence, rp), odom)
        gap = envelope.path_gap(local, p, radius, cp, reverse)
        if gap <= 0.0 or _contains(fence, odom.x, odom.y):
            cap = min(cap, rp.escape_speed)
        else:
            cap = min(cap, envelope.structure_cap(p, gap, cp))
    return Limit(cap, Reason.GEOFENCE)
