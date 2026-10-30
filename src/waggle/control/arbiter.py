"""Limit arbitration: the output is the minimum over all limits and never above the request.

ADR-027. A minimum does not depend on the order of the limits, and a new limit cannot raise the
result. A malformed request or limit fails closed to zero with the reason ``INPUT_MISSING``.
"""

import math
from collections.abc import Sequence

from waggle.control.types import ControlOutput, ControlRequest, Limit, Reason
from waggle.sim.params import RobotParams

_EPS = 1e-9

_PRIORITY = (
    Reason.ESTOP,
    Reason.INPUT_MISSING,
    Reason.SCAN_INVALID,
    Reason.WATCHDOG,
    Reason.GEOFENCE,
    Reason.ENVELOPE,
    Reason.OCCLUSION,
    Reason.CPA,
    Reason.CLASS_MAX,
    Reason.REQUEST,
)
_RANK = {reason: index for index, reason in enumerate(_PRIORITY)}


def _checked(limit: Limit) -> tuple[float, Reason]:
    cap = limit.speed_cap
    if not math.isfinite(cap) or cap < 0.0:
        return 0.0, Reason.INPUT_MISSING
    return cap, limit.reason


def _class_hits(request: ControlRequest, p: RobotParams) -> tuple[float, float, list[float]]:
    """Speed cap of the class, angular factor of a differential drive, and the caps that bind."""
    mag = abs(request.speed)
    hits: list[float] = []
    if mag > p.max_speed:
        hits.append(p.max_speed)
    omega_factor = 1.0
    if p.kinematics == "differential":
        assert p.max_angular_speed is not None
        if abs(request.turn) > p.max_angular_speed:
            omega_factor = p.max_angular_speed / abs(request.turn)
            hits.append(mag * omega_factor)
    elif p.max_steer is not None and abs(request.turn) > p.max_steer:
        hits.append(mag)
    return p.max_speed, omega_factor, hits


def _scale(mag: float, allowed: float, turn: float) -> float:
    """Fraction of the request that survives the tightest cap."""
    if mag > _EPS:
        return min(1.0, allowed / mag)
    return 0.0 if allowed <= 0.0 and turn != 0.0 else 1.0


def arbitrate(request: ControlRequest, p: RobotParams, limits: Sequence[Limit]) -> ControlOutput:
    """Apply every limit to a request and report the binding reason."""
    if not (math.isfinite(request.speed) and math.isfinite(request.turn)):
        return ControlOutput(0.0, 0.0, Reason.INPUT_MISSING, (Reason.INPUT_MISSING,))
    mag = abs(request.speed)
    class_cap, omega_factor, class_hits = _class_hits(request, p)
    checked = [_checked(limit) for limit in limits]
    allowed = min([class_cap, *(cap for cap, _ in checked)])
    scale = _scale(mag, allowed, request.turn)
    hits = [(cap, reason) for cap, reason in checked if _binds(cap, mag, request.turn)]
    hits += [(cap, Reason.CLASS_MAX) for cap in class_hits]
    if p.kinematics == "differential":
        factor = min(scale, omega_factor)
        speed, turn = request.speed * factor, request.turn * factor
    else:
        assert p.max_steer is not None
        speed = request.speed * scale
        turn = max(-p.max_steer, min(p.max_steer, request.turn))
    if not hits:
        return ControlOutput(speed, turn, Reason.REQUEST, ())
    binding = min(hits, key=lambda hit: (hit[0], _RANK[hit[1]]))[1]
    ordered = sorted({reason for _, reason in hits}, key=_RANK.__getitem__)
    return ControlOutput(speed, turn, binding, tuple(ordered))


def _binds(cap: float, mag: float, turn: float) -> bool:
    """A limit binds when it is below the request, or blocks a pure rotation with a zero cap."""
    return cap < mag or (mag <= _EPS and cap <= 0.0 and turn != 0.0)
