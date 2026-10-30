"""Control types: request, limit and output of the fast layer (ADR-027).

Plain frozen data. The robot frame has x forward, y to the left, origin at the footprint center.
"""

from dataclasses import dataclass
from enum import StrEnum


class Reason(StrEnum):
    """Closed set of reasons a command was reduced. Values are stable strings for the run log."""

    REQUEST = "request"
    CLASS_MAX = "class_max"
    ENVELOPE = "envelope"
    OCCLUSION = "occlusion"
    CPA = "cpa"
    GEOFENCE = "geofence"
    WATCHDOG = "watchdog"
    SCAN_INVALID = "scan_invalid"
    INPUT_MISSING = "input_missing"
    ESTOP = "estop"


@dataclass(frozen=True)
class ControlRequest:
    """A motion command: speed in m/s (negative is reverse) and a turn value.

    ``turn`` is the steering angle in radians for a bicycle model and the angular speed in rad/s
    for a differential drive.
    """

    speed: float
    turn: float


@dataclass(frozen=True)
class Limit:
    """An upper bound on the speed magnitude in m/s, and the reason it exists."""

    speed_cap: float
    reason: Reason


@dataclass(frozen=True)
class ControlOutput:
    """The limited command, the binding reason, and every reason that was below the request."""

    speed: float
    turn: float
    reason: Reason
    limits_hit: tuple[Reason, ...]
