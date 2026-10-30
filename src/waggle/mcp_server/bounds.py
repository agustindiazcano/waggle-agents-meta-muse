"""Physical bounds per chassis and the map extent (ADR-032).

The speed limits repeat ``waggle.sim.params.ROBOT_PARAMS``; a test checks they agree, so this
package does not import the simulator.
"""

import math
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ChassisBounds:
    """Limits a request is checked against. Speeds in m/s."""

    max_speed: float


CHASSIS_BOUNDS = MappingProxyType(
    {
        "carrier": ChassisBounds(2.0),
        "forklift": ChassisBounds(1.5),
        "parts_runner": ChassisBounds(1.8),
        "tech_repair": ChassisBounds(1.2),
    }
)


@dataclass(frozen=True)
class MapExtent:
    """Axis-aligned map rectangle in meters. Edges are inside."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        values = (self.x_min, self.y_min, self.x_max, self.y_max)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("map extent must be finite")
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("map extent must have positive width and height")
