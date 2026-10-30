"""The eight E1 configurations of ADR-028. Each differs from its neighbours in one block."""

from dataclasses import dataclass
from enum import StrEnum

from waggle.control.limiter import EnvelopeMode


class Sensing(StrEnum):
    """What the control code is given as its scan."""

    NONE = "none"
    LIDAR = "lidar"
    ORACLE = "oracle"


@dataclass(frozen=True)
class E1Config:
    """One row of the ADR-028 table."""

    name: str
    sensing: Sensing
    mode: EnvelopeMode = EnvelopeMode.SWEPT
    beacons: bool = False
    occlusion: bool = False
    cpa: bool = False

    @property
    def controlled(self) -> bool:
        """False only for the no-control baseline."""
        return self.sensing is not Sensing.NONE


CONFIGS: tuple[E1Config, ...] = (
    E1Config("no_control", Sensing.NONE),
    E1Config("radial_lidar", Sensing.LIDAR, mode=EnvelopeMode.RADIAL),
    E1Config("envelope_oracle", Sensing.ORACLE),
    E1Config("envelope_lidar", Sensing.LIDAR),
    E1Config("envelope_lidar_beacons", Sensing.LIDAR, beacons=True),
    E1Config("envelope_occlusion_lidar", Sensing.LIDAR, occlusion=True),
    E1Config("envelope_occlusion_cpa_lidar", Sensing.LIDAR, occlusion=True, cpa=True),
    E1Config(
        "envelope_occlusion_cpa_lidar_beacons",
        Sensing.LIDAR,
        beacons=True,
        occlusion=True,
        cpa=True,
    ),
)

BY_NAME = {config.name: config for config in CONFIGS}

FALSE_STOP_GAP_M = 3.0
"""A stop that starts while every human is farther than this is a false stop (ADR-028)."""
