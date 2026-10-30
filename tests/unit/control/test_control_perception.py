"""waggle.control.perception: input checks, dropped rays, clusters and the human size class."""

import math

import numpy as np
import pytest
from control_support import make_odometry, make_scan

from waggle.control import perception
from waggle.control.params import DEFAULT_PERCEPTION_PARAMS as PP
from waggle.control.types import Reason
from waggle.sim.observations import LidarScan


def _check(scan: LidarScan | None, tick: int = 0, odom_tick: int | None = None) -> Reason | None:
    odom = make_odometry(tick=tick if odom_tick is None else odom_tick)
    return perception.check_inputs(scan, odom, tick, PP)


def test_a_fresh_scan_and_odometry_are_valid() -> None:
    assert _check(make_scan(tick=10), tick=10) is None


def test_a_missing_scan_is_scan_invalid() -> None:
    assert _check(None) is Reason.SCAN_INVALID


def test_missing_odometry_is_input_missing() -> None:
    assert perception.check_inputs(make_scan(), None, 0, PP) is Reason.INPUT_MISSING


def test_a_scan_older_than_the_limit_is_stale_and_exactly_the_limit_is_not() -> None:
    assert _check(make_scan(tick=0), tick=PP.max_scan_age_ticks) is None
    assert _check(make_scan(tick=0), tick=PP.max_scan_age_ticks + 1) is Reason.SCAN_INVALID


def test_a_scan_from_the_future_is_invalid() -> None:
    assert _check(make_scan(tick=5), tick=4) is Reason.SCAN_INVALID


def test_stale_odometry_is_input_missing() -> None:
    old = _check(make_scan(tick=20), tick=20, odom_tick=20 - PP.max_scan_age_ticks - 1)
    assert old is Reason.INPUT_MISSING


def test_too_many_dropped_rays_make_the_scan_invalid() -> None:
    limit = int(PP.max_nan_fraction * 360)
    assert _check(make_scan(nan_rays=range(limit))) is None
    assert _check(make_scan(nan_rays=range(limit + 1))) is Reason.SCAN_INVALID


@pytest.mark.parametrize(
    "scan",
    [
        LidarScan(0, 0, -math.pi, 0.0175, 12.0, np.empty(0)),
        LidarScan(0, 0, -math.pi, 0.0, 12.0, np.full(10, 12.0)),
        LidarScan(0, 0, -math.pi, 0.0175, 0.0, np.full(10, 12.0)),
        LidarScan(0, 0, math.nan, 0.0175, 12.0, np.full(10, 12.0)),
    ],
)
def test_a_malformed_scan_is_invalid(scan: LidarScan) -> None:
    assert _check(scan) is Reason.SCAN_INVALID


def test_a_dropped_ray_takes_the_smaller_neighbour_within_the_window() -> None:
    ranges = np.array([5.0, 3.0, math.nan, 4.0, 6.0])
    filled = perception.fill_dropped(ranges, 2)
    assert filled[2] == 3.0


def test_a_dropped_ray_with_one_valid_side_takes_that_side() -> None:
    filled = perception.fill_dropped(np.array([math.nan, math.nan, 4.0, 4.5]), 2)
    assert filled[1] == 4.0
    assert filled[0] == 4.0


def test_a_dropped_ray_with_no_valid_neighbour_takes_zero() -> None:
    filled = perception.fill_dropped(np.array([2.0, math.nan, math.nan, math.nan, 2.0]), 1)
    assert filled[2] == 0.0
    assert filled[1] == 2.0


def test_non_finite_and_negative_ranges_count_as_dropped() -> None:
    filled = perception.fill_dropped(np.array([3.0, math.inf, -1.0, 3.0]), 2)
    assert np.all(np.isfinite(filled)) and np.all(filled >= 0.0)


def test_no_returns_gives_no_clusters() -> None:
    assert perception.clusters_from_scan(make_scan(), PP) == []


def test_a_human_sized_disc_is_one_cluster_in_the_robot_frame() -> None:
    clusters = perception.clusters_from_scan(make_scan(discs=[(3.0, 0.0, 0.3)]), PP)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert 2.6 < cluster.points[:, 0].min() < 2.75
    assert 0.4 < cluster.extent <= 0.6  # at most the diameter: grazing rays are not sampled
    assert perception.is_human_candidate(cluster, PP)


def test_two_objects_apart_are_two_clusters() -> None:
    scan = make_scan(discs=[(3.0, 0.0, 0.3), (0.0, 4.0, 0.3)])
    assert len(perception.clusters_from_scan(scan, PP)) == 2


def test_a_long_wall_is_a_structure_not_a_human_candidate() -> None:
    clusters = perception.clusters_from_scan(make_scan(boxes=[(2.0, -3.0, 2.4, 3.0)]), PP)
    assert len(clusters) == 1
    assert clusters[0].extent > PP.human_max_extent
    assert not perception.is_human_candidate(clusters[0], PP)


def test_a_dropped_ray_inside_an_object_does_not_split_the_cluster() -> None:
    clean = make_scan(discs=[(3.0, 0.0, 0.3)])
    hit = np.flatnonzero(clean.ranges < clean.max_range)
    assert len(hit) > 4
    holed = make_scan(discs=[(3.0, 0.0, 0.3)], nan_rays=[int(hit[len(hit) // 2])])
    assert len(perception.clusters_from_scan(holed, PP)) == 1


def test_an_object_behind_the_robot_across_the_scan_seam_is_one_cluster() -> None:
    clusters = perception.clusters_from_scan(make_scan(discs=[(-3.0, 0.0, 0.3)]), PP)
    assert len(clusters) == 1


def test_five_dropped_rays_in_a_row_put_a_point_at_the_robot() -> None:
    scan = make_scan(nan_rays=range(100, 105))
    clusters = perception.clusters_from_scan(scan, PP)
    nearest = min(float(np.min(np.hypot(c.points[:, 0], c.points[:, 1]))) for c in clusters)
    assert nearest == 0.0


WALL_FACE = np.array([[3.0, -1.0, 3.0, 1.0]])


def test_points_on_a_mapped_segment_are_on_the_map() -> None:
    points = np.array([[3.0, -0.4], [3.05, 0.0], [2.95, 0.5]])
    assert perception.on_static_map(points, WALL_FACE, PP.map_margin)


def test_one_point_off_the_map_makes_the_cluster_not_on_it() -> None:
    points = np.array([[3.0, -0.4], [3.4, 0.0]])
    assert not perception.on_static_map(points, WALL_FACE, PP.map_margin)


def test_an_empty_map_or_empty_cluster_is_never_on_the_map() -> None:
    points = np.array([[3.0, 0.0]])
    assert not perception.on_static_map(points, np.empty((0, 4)), PP.map_margin)
    assert not perception.on_static_map(np.empty((0, 2)), WALL_FACE, PP.map_margin)


def test_a_point_past_the_end_of_a_segment_is_measured_to_its_end() -> None:
    points = np.array([[3.0, 1.5]])
    assert not perception.on_static_map(points, WALL_FACE, PP.map_margin)
