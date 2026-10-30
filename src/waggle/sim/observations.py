"""Observation types: the only part of waggle.sim that waggle.control may read besides params.

Leaf module: it imports nothing from the project, so importing it never loads ground truth.
These are plain frozen data. They carry no logic.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class LidarScan:
    """One 2D scan from a robot, in the robot frame.

    ``ranges[i]`` is the distance in meters along ``angle_min + i * angle_increment`` radians.
    A value equal to ``max_range`` means no return. NaN means the ray was dropped.
    """

    tick: int
    robot_index: int
    angle_min: float
    angle_increment: float
    max_range: float
    ranges: NDArray[np.float64]


@dataclass(frozen=True)
class RobotOdometry:
    """Noisy own-state estimate of a robot: pose in meters and radians, speeds in m/s and rad/s."""

    tick: int
    robot_index: int
    x: float
    y: float
    theta: float
    speed: float
    angular_speed: float


@dataclass(frozen=True)
class BeaconReport:
    """A human beacon position as the robot receives it, with noise and delay applied.

    ``delay_ticks`` is how many ticks old the position is when it arrives.
    """

    tick: int
    robot_index: int
    human_index: int
    x: float
    y: float
    delay_ticks: int
