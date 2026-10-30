"""Simulation constants and robot class parameters (ADR-021).

Leaf module: it imports nothing from the project, so ``waggle.control`` can read it without
reaching ground truth. A robot knows these values about itself. All values are assumptions to
calibrate and make no claim of any standard.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

DT = 0.025
"""Fixed step in seconds (40 Hz). Every layer reads this constant, never a wall clock."""

LIDAR_PERIOD_TICKS = 4
"""Lidar rate: every 4 ticks, which is 10 Hz at DT = 0.025 s."""

LOAD_RAISED_SPEED_FACTOR = 0.6
"""Forklift with the load raised: maximum speed is multiplied by this factor (assumption)."""

LOAD_RAISED_DECEL_FACTOR = 0.7
"""Forklift with the load raised: the deceleration limit is multiplied by this (assumption)."""

HUMAN_RADIUS = 0.30
"""Default human footprint: a disc of this radius in meters (assumption)."""

HUMAN_WALK_SPEED = 1.4
"""Assumed human walking and approach speed in m/s (assumption)."""

_TICK_TOLERANCE = 1e-9
_KINEMATICS = ("bicycle", "differential")


class ParamsError(ValueError):
    """A robot parameter set is malformed or breaks the tick rule."""


class RobotKind(StrEnum):
    """The four robot classes."""

    CARRIER = "carrier"
    FORKLIFT = "forklift"
    PARTS_RUNNER = "parts_runner"
    TECH_REPAIR = "tech_repair"


def ticks_for(seconds: float) -> int:
    """Whole ticks in ``seconds``. Raises ParamsError unless it is a non-negative multiple of dt."""
    ticks = round(seconds / DT)
    if ticks < 0 or abs(ticks * DT - seconds) > _TICK_TOLERANCE:
        raise ParamsError(f"{seconds} s is not a non-negative multiple of dt = {DT} s")
    return ticks


@dataclass(frozen=True)
class RobotParams:
    """Parameters of one robot class. Lengths in meters, speeds in m/s, angles in radians."""

    kind: RobotKind
    max_speed: float
    decel: float
    actuation_delay: float
    length: float
    width: float
    kinematics: str
    wheelbase: float | None = None
    max_steer: float | None = None
    max_angular_speed: float | None = None

    @property
    def delay_ticks(self) -> int:
        """Actuation delay in whole ticks."""
        return ticks_for(self.actuation_delay)

    @property
    def min_turn_radius(self) -> float:
        """Minimum turning radius. Zero for a differential drive, which turns in place."""
        if self.kinematics == "bicycle":
            assert self.wheelbase is not None and self.max_steer is not None
            return self.wheelbase / math.tan(self.max_steer)
        return 0.0


ROBOT_PARAMS: Mapping[RobotKind, RobotParams] = {
    RobotKind.CARRIER: RobotParams(
        RobotKind.CARRIER, 2.0, 2.0, 0.10, 1.2, 0.8, "differential", max_angular_speed=1.5
    ),
    RobotKind.FORKLIFT: RobotParams(
        RobotKind.FORKLIFT, 1.5, 0.8, 0.15, 2.4, 1.1, "bicycle", wheelbase=1.6, max_steer=0.569
    ),
    RobotKind.PARTS_RUNNER: RobotParams(
        RobotKind.PARTS_RUNNER, 1.8, 1.5, 0.10, 0.9, 0.6, "differential", max_angular_speed=1.8
    ),
    RobotKind.TECH_REPAIR: RobotParams(
        RobotKind.TECH_REPAIR, 1.2, 1.5, 0.10, 0.8, 0.6, "differential", max_angular_speed=1.2
    ),
}

_FIELDS = {
    "kind",
    "max_speed",
    "decel",
    "actuation_delay",
    "length",
    "width",
    "kinematics",
    "wheelbase",
    "max_steer",
    "max_angular_speed",
}
_REQUIRED = {"kind", "max_speed", "decel", "actuation_delay", "length", "width", "kinematics"}


def _positive(data: Mapping[str, object], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ParamsError(f"{key} must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ParamsError(f"{key} must be a finite number above zero")
    return float(value)


def _optional_positive(data: Mapping[str, object], key: str) -> float | None:
    return _positive(data, key) if key in data else None


def parse_robot_params(data: Mapping[str, object]) -> RobotParams:
    """Validate a parameter mapping. Unknown or missing fields, bad numbers and a delay that is
    not a multiple of dt raise ParamsError."""
    unknown = set(data) - _FIELDS
    if unknown:
        raise ParamsError(f"unknown fields: {sorted(unknown)}")
    missing = _REQUIRED - set(data)
    if missing:
        raise ParamsError(f"missing fields: {sorted(missing)}")
    raw_kind = data["kind"]
    try:
        kind = RobotKind(raw_kind if isinstance(raw_kind, str) else "")
    except ValueError as err:
        raise ParamsError(f"unknown robot kind: {data['kind']!r}") from err
    kinematics = data["kinematics"]
    if kinematics not in _KINEMATICS:
        raise ParamsError(f"kinematics must be one of {_KINEMATICS}")
    delay = data["actuation_delay"]
    if isinstance(delay, bool) or not isinstance(delay, int | float) or not math.isfinite(delay):
        raise ParamsError("actuation_delay must be a finite number")
    try:
        ticks_for(float(delay))
    except ParamsError as err:
        raise ParamsError(f"actuation_delay must be a multiple of dt: {err}") from err
    params = RobotParams(
        kind=kind,
        max_speed=_positive(data, "max_speed"),
        decel=_positive(data, "decel"),
        actuation_delay=float(delay),
        length=_positive(data, "length"),
        width=_positive(data, "width"),
        kinematics=str(kinematics),
        wheelbase=_optional_positive(data, "wheelbase"),
        max_steer=_optional_positive(data, "max_steer"),
        max_angular_speed=_optional_positive(data, "max_angular_speed"),
    )
    if params.kinematics == "bicycle" and (params.wheelbase is None or params.max_steer is None):
        raise ParamsError("a bicycle model needs a wheelbase and max_steer")
    if params.kinematics == "differential" and params.max_angular_speed is None:
        raise ParamsError("a differential drive needs max_angular_speed")
    return params
