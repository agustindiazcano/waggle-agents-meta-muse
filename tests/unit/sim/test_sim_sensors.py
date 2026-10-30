"""Simulated lidar, odometry and beacons: known geometry, occlusion, noise, dropout, seeds."""

import dataclasses
import math

import numpy as np
import pytest
from numpy.typing import NDArray

from waggle.sim import observations, params, sensors, streams, world

Floats = NDArray[np.float64]
NO_NOISE = sensors.LidarConfig(range_sigma=0.0, dropout_probability=0.0)


def rng(seed: int = 1) -> np.random.Generator:
    return streams.make_streams(seed, "lidar", 1)[0]


def box_world(extra_racks: list[list[list[float]]] | None = None) -> world.World:
    return world.parse_world(
        {
            "version": 1,
            "name": "room",
            "bounds": [-20.0, -20.0, 20.0, 20.0],
            "walls": [[[5.0, -5.0], [6.0, -5.0], [6.0, 5.0], [5.0, 5.0]]],
            "racks": extra_racks or [],
            "zones": [
                {"id": "a", "kind": "aisle", "polygon": [[-1, -1], [1, -1], [1, 1], [-1, 1]]}
            ],
        }
    )


def ray_index(angle: float, cfg: sensors.LidarConfig = NO_NOISE) -> int:
    return round((angle - (-math.pi)) / (2 * math.pi / cfg.n_rays)) % cfg.n_rays


def scan(
    static: Floats,
    pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
    discs: list[tuple[float, float, float]] | None = None,
    boxes: list[Floats] | None = None,
    cfg: sensors.LidarConfig = NO_NOISE,
    seed: int = 1,
) -> observations.LidarScan:
    disc_array = np.array(discs or [], dtype=np.float64).reshape(-1, 3)
    box_array = np.array(boxes or [], dtype=np.float64).reshape(-1, 4, 2)
    return sensors.lidar_scan(static, disc_array, box_array, np.array(pose), cfg, rng(seed))


# ---------------------------------------------------------------- defaults and validation


def test_documented_defaults() -> None:
    cfg = sensors.LidarConfig()
    assert (cfg.n_rays, cfg.max_range, cfg.range_sigma, cfg.dropout_probability) == (
        360,
        12.0,
        0.02,
        0.01,
    )
    assert params.LIDAR_PERIOD_TICKS == 4
    assert sensors.lidar_due(0) and sensors.lidar_due(4) and not sensors.lidar_due(3)


@pytest.mark.parametrize(
    "bad",
    [
        {"n_rays": 0},
        {"max_range": 0.0},
        {"max_range": -1.0},
        {"range_sigma": -0.1},
        {"dropout_probability": -0.1},
        {"dropout_probability": 1.1},
    ],
)
def test_bad_configuration_is_rejected(bad: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        sensors.LidarConfig(**bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------- known geometry


def test_a_wall_straight_ahead_is_hit_at_the_known_range() -> None:
    result = scan(sensors.static_segments(box_world()))
    assert result.ranges[ray_index(0.0)] == pytest.approx(5.0)
    assert result.max_range == 12.0 and result.angle_min == pytest.approx(-math.pi)


def test_rays_that_see_nothing_return_max_range() -> None:
    result = scan(sensors.static_segments(box_world()))
    assert result.ranges[ray_index(math.pi)] == pytest.approx(12.0)  # bounds are 20 m away


def test_the_pose_heading_rotates_the_scan() -> None:
    result = scan(sensors.static_segments(box_world()), pose=(0.0, 0.0, math.pi))
    assert result.ranges[ray_index(math.pi)] == pytest.approx(5.0)


def test_a_human_disc_is_hit_at_its_near_edge() -> None:
    result = scan(sensors.static_segments(box_world()), discs=[(3.0, 0.0, 0.3)])
    assert result.ranges[ray_index(0.0)] == pytest.approx(2.7)


def test_another_robot_footprint_is_hit() -> None:
    rect = np.array([[4.5, -0.5], [4.5, 0.5], [3.5, 0.5], [3.5, -0.5]])
    result = scan(sensors.static_segments(box_world()), boxes=[rect])
    assert result.ranges[ray_index(0.0)] == pytest.approx(3.5)


def test_the_origin_inside_a_disc_does_not_hit_it() -> None:
    result = scan(sensors.static_segments(box_world()), discs=[(0.0, 0.0, 0.5)])
    assert result.ranges[ray_index(0.0)] == pytest.approx(5.0)


# ---------------------------------------------------------------- occlusion


def test_a_human_behind_a_rack_is_not_in_the_scan() -> None:
    rack = [[[2.0, 1.0], [3.0, 1.0], [3.0, 3.0], [2.0, 3.0]]]
    static = sensors.static_segments(box_world(rack))
    hidden = (4.0, 2.5, 0.3)  # behind the rack as seen from the origin
    without = scan(static)
    with_human = scan(static, discs=[hidden])
    assert with_human.ranges.tolist() == without.ranges.tolist()
    direction = math.atan2(2.5, 4.0)
    assert with_human.ranges[ray_index(direction)] < math.hypot(4.0, 2.5) - 0.3


def test_the_same_human_is_seen_once_it_steps_out_of_the_shadow() -> None:
    rack = [[[2.0, 1.0], [3.0, 1.0], [3.0, 3.0], [2.0, 3.0]]]
    static = sensors.static_segments(box_world(rack))
    seen = scan(static, discs=[(4.0, 0.0, 0.3)])
    assert seen.ranges[ray_index(0.0)] == pytest.approx(3.7)


# ---------------------------------------------------------------- noise and dropout


def test_range_noise_stays_within_bounds_and_is_unbiased() -> None:
    static = sensors.static_segments(box_world())
    cfg = sensors.LidarConfig(dropout_probability=0.0)
    errors = []
    for seed in range(20):
        result = scan(static, cfg=cfg, seed=seed)
        clean = scan(static)
        hits = clean.ranges < clean.max_range
        errors.extend((result.ranges[hits] - clean.ranges[hits]).tolist())
    errors_array = np.array(errors)
    assert np.max(np.abs(errors_array)) <= 6 * cfg.range_sigma
    assert abs(float(errors_array.mean())) <= 10 * cfg.range_sigma / math.sqrt(len(errors_array))
    assert 0.8 * cfg.range_sigma <= float(errors_array.std()) <= 1.2 * cfg.range_sigma


def test_noisy_ranges_never_leave_zero_to_max_range() -> None:
    static = sensors.static_segments(box_world())
    cfg = sensors.LidarConfig(range_sigma=3.0, dropout_probability=0.0)
    for seed in range(10):
        ranges = scan(static, cfg=cfg, seed=seed).ranges
        assert np.all((ranges >= 0.0) & (ranges <= cfg.max_range))


def test_dropout_rate_is_within_four_standard_deviations_of_nominal() -> None:
    static = sensors.static_segments(box_world())
    cfg = sensors.LidarConfig(range_sigma=0.0)
    scans = 50
    dropped = sum(int(np.isnan(scan(static, cfg=cfg, seed=s).ranges).sum()) for s in range(scans))
    total = scans * cfg.n_rays
    p = cfg.dropout_probability
    tolerance = 4 * math.sqrt(p * (1 - p) / total)
    assert abs(dropped / total - p) <= tolerance


def test_dropout_extremes() -> None:
    static = sensors.static_segments(box_world())
    none = scan(static, cfg=sensors.LidarConfig(dropout_probability=0.0))
    every = scan(static, cfg=sensors.LidarConfig(dropout_probability=1.0))
    assert not np.isnan(none.ranges).any()
    assert np.isnan(every.ranges).all()


# ---------------------------------------------------------------- determinism and purity


def test_same_seed_gives_the_same_scan_and_different_seeds_differ() -> None:
    static = sensors.static_segments(box_world())
    cfg = sensors.LidarConfig()
    a, b, c = (
        scan(static, cfg=cfg, seed=3),
        scan(static, cfg=cfg, seed=3),
        scan(static, cfg=cfg, seed=4),
    )
    assert np.array_equal(a.ranges, b.ranges, equal_nan=True)
    assert not np.array_equal(a.ranges, c.ranges, equal_nan=True)


def test_the_number_of_random_draws_does_not_depend_on_the_geometry() -> None:
    cfg = sensors.LidarConfig()
    rack = [[[2.0, 1.0], [3.0, 1.0], [3.0, 3.0], [2.0, 3.0]]]
    states = []
    for static in (sensors.static_segments(box_world()), sensors.static_segments(box_world(rack))):
        generator = rng(9)
        sensors.lidar_scan(
            static, np.zeros((0, 3)), np.zeros((0, 4, 2)), np.zeros(3), cfg, generator
        )
        states.append(generator.bit_generator.state["state"]["state"])
    assert states[0] == states[1]


def test_the_scan_does_not_change_its_inputs() -> None:
    static = sensors.static_segments(box_world())
    pose = np.array([0.5, 0.2, 0.3])
    before = (static.copy(), pose.copy())
    sensors.lidar_scan(
        static, np.zeros((0, 3)), np.zeros((0, 4, 2)), pose, sensors.LidarConfig(), rng()
    )
    assert np.array_equal(static, before[0]) and np.array_equal(pose, before[1])


def test_the_output_is_a_frozen_lidar_scan() -> None:
    result = scan(sensors.static_segments(box_world()))
    assert isinstance(result, observations.LidarScan)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.tick = 5  # type: ignore[misc]


def test_static_segments_cover_walls_racks_and_bounds() -> None:
    segments = sensors.static_segments(box_world([[[2, 1], [3, 1], [3, 3], [2, 3]]]))
    assert segments.shape == (4 + 4 + 4, 4)  # wall, rack and the four bounds edges


# ---------------------------------------------------------------- odometry


def test_odometry_without_noise_is_exact_and_with_noise_is_seeded() -> None:
    pose = np.array([1.0, 2.0, 0.5])
    exact = sensors.odometry(3, 0, pose, 1.2, 0.1, sensors.OdometryNoise(0.0, 0.0, 0.0), rng())
    assert (exact.x, exact.y, exact.theta, exact.speed, exact.angular_speed) == (
        1.0,
        2.0,
        0.5,
        1.2,
        0.1,
    )
    noise = sensors.OdometryNoise()
    a = sensors.odometry(3, 0, pose, 1.2, 0.1, noise, rng(5))
    b = sensors.odometry(3, 0, pose, 1.2, 0.1, noise, rng(5))
    c = sensors.odometry(3, 0, pose, 1.2, 0.1, noise, rng(6))
    assert a == b and a != c
    assert abs(a.x - 1.0) < 0.5 and isinstance(a, observations.RobotOdometry)


# ---------------------------------------------------------------- beacons


HISTORY = [np.array([[10.0 + k, 0.0], [0.0, 5.0 + k]]) for k in range(8)]


def test_beacons_are_off_by_default() -> None:
    reports = sensors.beacon_reports(8, 0, np.zeros(2), HISTORY, sensors.BeaconConfig(), rng())
    assert reports == ()


def test_beacons_report_delayed_noisy_positions_around_corners() -> None:
    cfg = sensors.BeaconConfig(enabled=True, position_sigma=0.0, delay_ticks=4, max_range=30.0)
    reports = sensors.beacon_reports(8, 0, np.zeros(2), HISTORY, cfg, rng())
    assert [r.human_index for r in reports] == [0, 1]
    assert all(isinstance(r, observations.BeaconReport) for r in reports)
    assert reports[0].delay_ticks == 4
    assert (reports[0].x, reports[0].y) == (HISTORY[-1 - 4][0, 0], HISTORY[-1 - 4][0, 1])


def test_beacons_beyond_range_are_not_reported_and_noise_is_seeded() -> None:
    near = sensors.BeaconConfig(enabled=True, position_sigma=0.0, delay_ticks=0, max_range=12.0)
    assert [
        r.human_index for r in sensors.beacon_reports(8, 0, np.zeros(2), HISTORY, near, rng())
    ] == [1]
    noisy = sensors.BeaconConfig(enabled=True, position_sigma=0.3, delay_ticks=0, max_range=40.0)
    a = sensors.beacon_reports(8, 0, np.zeros(2), HISTORY, noisy, rng(2))
    b = sensors.beacon_reports(8, 0, np.zeros(2), HISTORY, noisy, rng(2))
    assert a == b


def test_a_delay_longer_than_the_history_uses_the_oldest_position() -> None:
    cfg = sensors.BeaconConfig(enabled=True, position_sigma=0.0, delay_ticks=50, max_range=40.0)
    first = sensors.beacon_reports(8, 0, np.zeros(2), HISTORY, cfg, rng())[0]
    assert first.x == HISTORY[0][0, 0]
