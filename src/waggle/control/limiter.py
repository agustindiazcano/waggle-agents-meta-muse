"""Envelope limits for one motion command, composed through the arbiter (ADR-027).

The points are detections in the robot frame. Perception (ADR-026) produces them from a scan; this
module does not read a scan.
"""

import math
from enum import StrEnum

import numpy as np

from waggle.control import envelope
from waggle.control.arbiter import arbitrate
from waggle.control.params import ControlParams
from waggle.control.types import ControlOutput, ControlRequest, Limit, Reason
from waggle.sim.params import RobotParams

_EPS = 1e-9


class EnvelopeMode(StrEnum):
    """How the gap to a detection is measured."""

    SWEPT = "swept"
    RADIAL = "radial"


def _gaps(
    human: envelope.Points,
    structure: envelope.Points,
    request: ControlRequest,
    p: RobotParams,
    cp: ControlParams,
    mode: EnvelopeMode,
) -> tuple[float, float]:
    if mode is EnvelopeMode.RADIAL:
        return envelope.radial_gap(human, p), envelope.radial_gap(structure, p)
    radius = envelope.path_radius(p, request.speed, request.turn)
    reverse = request.speed < 0.0
    return (
        envelope.path_gap(human, p, radius, cp, reverse),
        envelope.path_gap(structure, p, radius, cp, reverse),
    )


def _rotation_limits(
    human: envelope.Points, structure: envelope.Points, p: RobotParams, cp: ControlParams
) -> list[Limit]:
    both = np.vstack([np.reshape(human, (-1, 2)), np.reshape(structure, (-1, 2))])
    return [Limit(0.0, Reason.ENVELOPE)] if envelope.rotation_blocked(both, p, cp) else []


def limit_command(
    request: ControlRequest,
    p: RobotParams,
    human_points: envelope.Points,
    structure_points: envelope.Points,
    current_speed: float,
    cp: ControlParams,
    mode: EnvelopeMode = EnvelopeMode.SWEPT,
) -> ControlOutput:
    """Limit a command by the separation to humans and the stopping distance to structures.

    A gap inside the stopping distance at the current speed gives a stop with reason ``ESTOP``.
    A pure rotation of a differential drive is blocked by any point inside the swept circle.
    """
    if not (math.isfinite(request.speed) and math.isfinite(request.turn)):
        return arbitrate(request, p, [])
    if p.kinematics == "differential" and abs(request.speed) <= _EPS and request.turn != 0.0:
        return arbitrate(request, p, _rotation_limits(human_points, structure_points, p, cp))
    gap_human, gap_structure = _gaps(human_points, structure_points, request, p, cp, mode)
    limits = [
        Limit(envelope.human_cap(p, gap_human, cp), Reason.ENVELOPE),
        Limit(envelope.structure_cap(p, gap_structure, cp), Reason.ENVELOPE),
    ]
    nearest = min(gap_human, gap_structure)
    if math.isfinite(nearest) and nearest <= envelope.stop_distance(p, abs(current_speed)):
        limits.append(Limit(0.0, Reason.ESTOP))
    return arbitrate(request, p, limits)
