"""Fast layer assumptions (ADR-026, ADR-027). Every value is an assumption to calibrate."""

import math
from dataclasses import dataclass


class ControlParamsError(ValueError):
    """A control parameter is not a finite positive number."""


@dataclass(frozen=True)
class ControlParams:
    """Margins and bounds used by the envelope.

    ``human_speed_bound`` is a worst case speed for a human in m/s. It is higher than the nominal
    walking speed of the simulator on purpose. ``interp_k`` multiplies the separation distance: a
    robot reaches full speed only when the gap is at least ``interp_k`` times ``S_sep``.
    """

    human_speed_bound: float = 1.6
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
