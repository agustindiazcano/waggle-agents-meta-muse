"""Fast layer assumptions (ADR-026, ADR-027). Every value is an assumption to calibrate."""

import math
from dataclasses import dataclass

HUMAN_SPEED_BOUND = 1.6
"""Worst case human speed in m/s, above the nominal walking speed of the simulator (assumption)."""


class ControlParamsError(ValueError):
    """A control parameter is not a finite positive number."""


@dataclass(frozen=True)
class ControlParams:
    """Margins and bounds used by the envelope.

    ``human_speed_bound`` is a worst case speed for a human in m/s. It is higher than the nominal
    walking speed of the simulator on purpose. ``interp_k`` multiplies the separation distance: a
    robot reaches full speed only when the gap is at least ``interp_k`` times ``S_sep``.
    """

    human_speed_bound: float = HUMAN_SPEED_BOUND
    human_margin: float = 0.3
    structure_margin: float = 0.2
    lateral_margin: float = 0.1
    interp_k: float = 1.5

    def __post_init__(self) -> None:
        for name in ("human_speed_bound", "human_margin", "structure_margin", "lateral_margin"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ControlParamsError(f"{name} must be a finite number above zero")
        if not math.isfinite(self.interp_k) or self.interp_k < 1.0:
            raise ControlParamsError("interp_k must be a finite number of at least 1")


DEFAULT_CONTROL_PARAMS = ControlParams()


@dataclass(frozen=True)
class PerceptionParams:
    """Thresholds of scan checks, clustering and tracking (ADR-026). All are assumptions.

    Ticks are simulator ticks of 0.025 s. ``gap_base`` plus ``gap_per_meter`` times the range is
    the largest gap between two neighbouring returns of one cluster.
    """

    max_scan_age_ticks: int = 8
    max_nan_fraction: float = 0.2
    nan_window: int = 2
    gap_base: float = 0.15
    gap_per_meter: float = 0.05
    human_max_extent: float = 1.0
    assoc_gate_base: float = 0.5
    velocity_alpha: float = 0.5
    max_coast_ticks: int = 80
    ring_points: int = 12
    beacon_sigma: float = 0.1
    human_speed_bound: float = HUMAN_SPEED_BOUND

    def __post_init__(self) -> None:
        for name in ("max_scan_age_ticks", "nan_window", "max_coast_ticks", "ring_points"):
            if getattr(self, name) < 1:
                raise ControlParamsError(f"{name} must be at least 1")
        for name in (
            "gap_base",
            "gap_per_meter",
            "human_max_extent",
            "assoc_gate_base",
            "beacon_sigma",
            "human_speed_bound",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ControlParamsError(f"{name} must be a finite number above zero")
        if not 0.0 <= self.max_nan_fraction < 1.0:
            raise ControlParamsError("max_nan_fraction must be in [0, 1)")
        if not 0.0 < self.velocity_alpha <= 1.0:
            raise ControlParamsError("velocity_alpha must be in (0, 1]")
        if self.ring_points < 4:
            raise ControlParamsError("ring_points must be at least 4")


DEFAULT_PERCEPTION_PARAMS = PerceptionParams()


@dataclass(frozen=True)
class OcclusionParams:
    """Thresholds of the occlusion cap (ADR-024). Both are assumptions.

    ``jump_min`` is the smallest range jump between two neighbouring rays that counts as an
    occlusion boundary: the depth of a pocket that can hold a person (twice the human radius).
    ``speed_floor`` is the speed used to size the turning circle when the requested speed is near
    zero, so the curvature stays finite.
    """

    jump_min: float = 0.6
    speed_floor: float = 0.05

    def __post_init__(self) -> None:
        for name in ("jump_min", "speed_floor"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ControlParamsError(f"{name} must be a finite number above zero")


DEFAULT_OCCLUSION_PARAMS = OcclusionParams()
