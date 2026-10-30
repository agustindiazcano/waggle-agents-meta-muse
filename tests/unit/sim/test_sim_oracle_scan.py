"""waggle.sim.sensors.oracle_scan: the E1 oracle scan has no noise, no dropout, no shadow."""

import math

import numpy as np
import pytest

from waggle.sim import sensors
from waggle.sim.sensors import LidarConfig

CONFIG = LidarConfig(n_rays=360, max_range=12.0, range_sigma=0.0, dropout_probability=0.0)
POSE = np.array([0.0, 0.0, 0.0])
NO_SEGMENTS = np.zeros((0, 4))
NO_BOXES = np.zeros((0, 4, 2))
DISC = np.array([[3.0, 0.0, 0.3]])
WALL = np.array([[1.5, -3.0, 1.5, 3.0]])


def _ray_to(scan_angle: float) -> int:
    return round((scan_angle + math.pi) / (2 * math.pi / CONFIG.n_rays)) % CONFIG.n_rays


def test_the_oracle_scan_has_no_noise_and_no_dropped_rays() -> None:
    scan = sensors.oracle_scan(NO_SEGMENTS, DISC, NO_BOXES, POSE, CONFIG)
    assert np.isfinite(scan.ranges).all()
    again = sensors.oracle_scan(NO_SEGMENTS, DISC, NO_BOXES, POSE, CONFIG)
    assert np.array_equal(scan.ranges, again.ranges)
    assert scan.ranges[_ray_to(0.0)] == pytest.approx(2.7)


def test_a_person_behind_a_wall_is_seen_by_the_oracle_and_not_by_the_lidar() -> None:
    oracle = sensors.oracle_scan(WALL, DISC, NO_BOXES, POSE, CONFIG)
    rng = np.random.default_rng(1)
    real = sensors.lidar_scan(WALL, DISC, NO_BOXES, POSE, CONFIG, rng)
    ahead = _ray_to(0.0)
    assert oracle.ranges[ahead] == pytest.approx(2.7)
    assert real.ranges[ahead] == pytest.approx(1.5)


def test_without_an_occluder_the_oracle_equals_a_noiseless_lidar() -> None:
    rng = np.random.default_rng(1)
    real = sensors.lidar_scan(NO_SEGMENTS, DISC, NO_BOXES, POSE, CONFIG, rng)
    oracle = sensors.oracle_scan(NO_SEGMENTS, DISC, NO_BOXES, POSE, CONFIG)
    assert np.array_equal(real.ranges, oracle.ranges)


def test_walls_and_robots_still_return_their_distance_where_there_is_no_person() -> None:
    oracle = sensors.oracle_scan(WALL, DISC, NO_BOXES, POSE, CONFIG)
    up = _ray_to(math.radians(30))
    assert oracle.ranges[up] == pytest.approx(1.5 / math.cos(math.radians(30)), rel=1e-6)


def test_the_scan_type_and_geometry_match_the_real_lidar() -> None:
    oracle = sensors.oracle_scan(NO_SEGMENTS, DISC, NO_BOXES, POSE, CONFIG, tick=8, robot_index=2)
    assert (oracle.tick, oracle.robot_index) == (8, 2)
    assert oracle.angle_min == -math.pi
    assert oracle.angle_increment == pytest.approx(2 * math.pi / 360)
    assert oracle.max_range == 12.0
    assert len(oracle.ranges) == 360


def test_the_oracle_draws_nothing_from_a_random_stream() -> None:
    rng = np.random.default_rng(5)
    before = rng.bit_generator.state
    sensors.oracle_scan(WALL, DISC, NO_BOXES, POSE, CONFIG)
    assert rng.bit_generator.state == before
