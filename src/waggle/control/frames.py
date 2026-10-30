"""Frame changes between the world and the robot, from the odometry pose. Meters and radians."""

import math

import numpy as np
from numpy.typing import NDArray

from waggle.sim.observations import RobotOdometry

Points = NDArray[np.float64]


def to_world(points: Points, odom: RobotOdometry) -> Points:
    """Robot frame (x forward, y left) to world frame."""
    c, s = math.cos(odom.theta), math.sin(odom.theta)
    return np.column_stack(
        [odom.x + c * points[:, 0] - s * points[:, 1], odom.y + s * points[:, 0] + c * points[:, 1]]
    )


def to_robot(points: Points, odom: RobotOdometry) -> Points:
    """World frame to robot frame."""
    c, s = math.cos(odom.theta), math.sin(odom.theta)
    dx, dy = points[:, 0] - odom.x, points[:, 1] - odom.y
    return np.column_stack([c * dx + s * dy, -s * dx + c * dy])
