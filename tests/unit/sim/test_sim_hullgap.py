"""Batched hull gaps against the slow reference detector functions."""

import numpy as np
import pytest

from waggle.sim import detector, hullgap
from waggle.sim.params import RobotKind, RobotParams

UNIT = RobotParams(
    RobotKind.CARRIER, 2.0, 2.0, 0.10, 1.2, 0.8, "differential", max_angular_speed=1.5
)
TOLERANCE = 1e-9


def _rect_points(pose: np.ndarray) -> np.ndarray:
    return hullgap.corners(np.array([0.6]), np.array([0.4]), pose[None, None, :])[0, 0]


def test_corners_match_the_reference_footprint() -> None:
    from waggle.sim import robots

    pose = np.array([1.3, -0.4, 0.7])
    expected = robots.footprint_corners(UNIT, *pose)
    got = hullgap.corners(np.array([0.6]), np.array([0.4]), pose[None, None, :])[0, 0]
    assert np.allclose(got, expected, atol=1e-12)


@pytest.mark.parametrize("seed", range(5))
def test_hull_point_gap_equals_the_reference_point_polygon_distance(seed: int) -> None:
    rng = np.random.default_rng(seed)
    for _ in range(40):
        pa, pb = rng.uniform(-1, 1, 3), rng.uniform(-1, 1, 3)
        points = np.vstack([_rect_points(pa), _rect_points(pb)])
        hull = detector.robots.convex_hull(points)
        target = rng.uniform(-3, 3, 2)
        reference = detector.point_polygon_distance(target, hull)
        got = float(hullgap.hull_point_gap(points[None], target[None])[0])
        assert got == pytest.approx(reference, abs=TOLERANCE)


@pytest.mark.parametrize("seed", range(5))
def test_hull_hull_gap_equals_the_reference_polygon_distance(seed: int) -> None:
    rng = np.random.default_rng(100 + seed)
    for _ in range(40):
        first = np.vstack(
            [_rect_points(rng.uniform(-1, 1, 3)), _rect_points(rng.uniform(-1, 1, 3))]
        )
        shift = rng.uniform(-3, 3, 2)
        second = np.vstack([_rect_points(np.array([*shift, rng.uniform(-3, 3)]))] * 2)
        reference = detector.polygon_distance(
            detector.robots.convex_hull(first), detector.robots.convex_hull(second)
        )
        got = float(hullgap.hull_hull_gap(first[None], second[None])[0])
        assert got == pytest.approx(reference, abs=TOLERANCE)


def test_the_reduced_gap_is_a_lower_bound_above_the_reduction() -> None:
    first = np.vstack([_rect_points(np.array([0.0, 0.0, 0.0]))] * 2)
    second = np.vstack([_rect_points(np.array([5.0, 0.0, 0.0]))] * 2)
    full = float(hullgap.hull_hull_gap(first[None], second[None])[0])
    cheap = float(hullgap.hull_hull_gap(first[None], second[None], np.array([0.003]))[0])
    assert cheap > 0.003 and cheap <= full + TOLERANCE


def test_touching_hulls_are_in_contact() -> None:
    first = np.vstack([_rect_points(np.array([0.0, 0.0, 0.0]))] * 2)
    second = np.vstack([_rect_points(np.array([1.2, 0.0, 0.0]))] * 2)  # edges exactly touch
    assert float(hullgap.hull_hull_gap(first[None], second[None])[0]) == 0.0


@pytest.mark.parametrize("seed", range(4))
def test_batched_swept_gaps_agree_with_the_scalar_reference_on_a_system_run(seed: int) -> None:
    """The detector counts equal a run of the reference gaps on random moving pairs."""
    rng = np.random.default_rng(seed)
    det = detector.Detector([UNIT, UNIT], separation_margin=0.5, near_miss_margin=0.8)
    for _ in range(60):
        prev = rng.uniform(-1.5, 1.5, (2, 3))
        now = prev + rng.uniform(-0.12, 0.12, (2, 3))
        hit = bool(det._robot_contacts(now, prev)[0, 1])
        reference = detector.robot_robot_gap(UNIT, prev[0], now[0], UNIT, prev[1], now[1])
        assert hit == detector.is_contact(reference) or abs(reference) < 5e-3
        human = rng.uniform(-1.5, 1.5, 2)
        moved = human + rng.uniform(-0.1, 0.1, 2)
        gaps = det._human_gaps(now, prev, moved[None], human[None])
        ref_h = [
            detector.robot_human_gap(UNIT, prev[i], now[i], human, moved, det.radius)
            for i in range(2)
        ]
        for i in range(2):
            if np.isfinite(gaps[i, 0]):
                assert gaps[i, 0] == pytest.approx(ref_h[i], abs=1e-9)
            else:
                assert ref_h[i] > det.margin
