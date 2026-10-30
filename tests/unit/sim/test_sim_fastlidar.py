"""Fast rollout lidar against the exact reference lidar."""

import math

import numpy as np
import pytest

from waggle.sim import fastlidar, robots, scenarios, sensors
from waggle.sim.observations import LidarScan
from waggle.sim.params import HUMAN_RADIUS, ROBOT_PARAMS, RobotKind

CONFIG = sensors.LidarConfig()
EMPTY = np.zeros((0, 4))


def _fleet(seed: int, count: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    poses = np.column_stack([rng.uniform(2, 14, (count, 2)), rng.uniform(-3, 3, count)])
    people = rng.uniform(2, 14, (3, 2))
    discs = np.hstack([people, np.full((3, 1), HUMAN_RADIUS)])
    p = ROBOT_PARAMS[RobotKind.CARRIER]
    corners = np.array([robots.footprint_corners(p, *pose) for pose in poses])
    return poses, discs, corners


def _reference(
    static: np.ndarray, poses: np.ndarray, discs: np.ndarray, corners: np.ndarray, seed: int
) -> list[LidarScan]:
    return [
        sensors.lidar_scan(
            static, discs, np.delete(corners, i, axis=0), poses[i], CONFIG,
            np.random.default_rng(seed + i), 0, i,
        )
        for i in range(len(poses))
    ]  # fmt: skip


def _fast(
    cache: fastlidar.StaticScanCache,
    poses: np.ndarray,
    discs: np.ndarray,
    corners: np.ndarray,
    seed: int,
) -> list[LidarScan]:
    rngs = [np.random.default_rng(seed + i) for i in range(len(poses))]
    return fastlidar.fleet_scans(cache, poses, discs, corners, rngs, 0)


@pytest.mark.parametrize("seed", range(6))
def test_dynamic_hits_equal_the_reference_exactly(seed: int) -> None:
    poses, discs, corners = _fleet(seed)
    cache = fastlidar.StaticScanCache(EMPTY, CONFIG)
    for got, ref in zip(
        _fast(cache, poses, discs, corners, seed),
        _reference(EMPTY, poses, discs, corners, seed),
        strict=True,
    ):
        assert np.array_equal(np.isnan(got.ranges), np.isnan(ref.ranges))
        assert np.nanmax(np.abs(got.ranges - ref.ranges)) < 1e-9


def test_a_robot_inside_a_disc_or_next_to_a_robot_still_matches() -> None:
    poses = np.array([[5.0, 5.0, 0.3], [5.4, 5.0, -1.0], [9.0, 9.0, 0.0]])
    discs = np.array([[5.0, 5.1, 0.30], [9.0, 9.5, 0.30]])
    p = ROBOT_PARAMS[RobotKind.CARRIER]
    corners = np.array([robots.footprint_corners(p, *pose) for pose in poses])
    cache = fastlidar.StaticScanCache(EMPTY, CONFIG)
    for got, ref in zip(
        _fast(cache, poses, discs, corners, 3),
        _reference(EMPTY, poses, discs, corners, 3),
        strict=True,
    ):
        assert np.nanmax(np.abs(got.ranges - ref.ranges)) < 1e-9


def test_the_noise_stream_advances_as_in_the_reference() -> None:
    poses, discs, corners = _fleet(1)
    cache = fastlidar.StaticScanCache(EMPTY, CONFIG)
    fast_rngs = [np.random.default_rng(10 + i) for i in range(len(poses))]
    fastlidar.fleet_scans(cache, poses, discs, corners, fast_rngs, 0)
    ref_rngs = [np.random.default_rng(10 + i) for i in range(len(poses))]
    for i, rng in enumerate(ref_rngs):
        sensors.lidar_scan(EMPTY, discs, np.delete(corners, i, axis=0), poses[i], CONFIG, rng)
    assert [r.random() for r in fast_rngs] == [r.random() for r in ref_rngs]


def _trajectory_poses(scenario_id: str) -> tuple[np.ndarray, np.ndarray]:
    scenario = scenarios.generate(scenario_id, 1)
    static = sensors.static_segments(scenarios.load_map(scenario.map_name))
    sim, _ = scenarios.build_engine(scenario)
    taken = []
    for tick in range(600):
        sim.step()
        if tick % 8 == 0:
            taken.append(np.array(sim.state.arrays["robot_pose"]))
    return static, np.concatenate(taken)


def _map_scene() -> tuple[np.ndarray, np.ndarray]:
    return _trajectory_poses("S14")


def test_static_ranges_stay_close_to_the_exact_ones_on_real_trajectories() -> None:
    """Measured on S14 robot poses: p99 error 10 cm, 0.1 percent of rays differ by over 1 m."""
    static, poses = _map_scene()
    got = fastlidar.StaticScanCache(static, CONFIG).static_ranges(poses)
    errors = []
    for pose, row in zip(poses, got, strict=True):
        angles = pose[2] + (-math.pi + 2 * math.pi / CONFIG.n_rays * np.arange(CONFIG.n_rays))
        dirs = np.stack([np.cos(angles), np.sin(angles)], axis=1)
        exact = np.minimum(sensors.segment_hits(pose[:2], dirs, static), CONFIG.max_range)
        errors.append(np.abs(exact - np.minimum(row, CONFIG.max_range)))
    error = np.concatenate(errors)
    assert np.quantile(error, 0.90) < 0.05
    assert np.quantile(error, 0.99) < 0.15
    assert np.mean(error > 1.0) < 0.005, "a different surface is hit only at corners and edges"


def test_the_cache_does_not_change_a_scan_whatever_was_scanned_before() -> None:
    static, poses = _map_scene()
    fresh = fastlidar.StaticScanCache(static, CONFIG).static_ranges(poses[:5])
    used = fastlidar.StaticScanCache(static, CONFIG)
    used.static_ranges(poses[5:40])
    assert np.array_equal(used.static_ranges(poses[:5]), fresh)
    assert len(used) > 5


def test_a_full_scan_is_repeatable_by_seed() -> None:
    static, poses = _map_scene()
    poses = poses[:4]
    discs = np.array([[10.0, 10.0, HUMAN_RADIUS]])
    p = ROBOT_PARAMS[RobotKind.CARRIER]
    corners = np.array([robots.footprint_corners(p, *pose) for pose in poses])
    cache = fastlidar.StaticScanCache(static, CONFIG)
    one = _fast(cache, poses, discs, corners, 8)
    two = _fast(fastlidar.StaticScanCache(static, CONFIG), poses, discs, corners, 8)
    for a, b in zip(one, two, strict=True):
        assert np.array_equal(a.ranges, b.ranges, equal_nan=True)


def test_invalid_cache_settings_are_rejected() -> None:
    with pytest.raises(ValueError):
        fastlidar.StaticScanCache(EMPTY, CONFIG, cell=0.0)
    with pytest.raises(ValueError):
        fastlidar.StaticScanCache(EMPTY, CONFIG, world_factor=0)


def test_the_rollout_system_scans_every_robot_on_lidar_ticks_only() -> None:
    scenario = scenarios.generate("S14", 1)
    sim, _ = scenarios.build_engine(scenario, {"lidar": len(scenario.robots)})
    static = sensors.static_segments(scenarios.load_map(scenario.map_name))
    sink: list[LidarScan] = []
    cache = fastlidar.StaticScanCache(static, CONFIG)
    params_list = [ROBOT_PARAMS[r.kind] for r in scenario.robots]
    sim.systems.append(fastlidar.rollout_system(cache, params_list, sink.extend))
    sim.run(9)  # ticks 0..8: scans on ticks 0, 4 and 8
    assert len(sink) == 3 * len(scenario.robots)
    assert {s.tick for s in sink} == {0, 4, 8}
