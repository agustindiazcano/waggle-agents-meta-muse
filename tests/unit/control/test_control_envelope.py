"""waggle.control.envelope: stopping and separation distance, speed caps, swept path gap."""

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.control import envelope
from waggle.control.params import DEFAULT_CONTROL_PARAMS as CP
from waggle.sim.params import ROBOT_PARAMS, RobotKind, RobotParams

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
FORKLIFT = ROBOT_PARAMS[RobotKind.FORKLIFT]
KINDS = list(RobotKind)


def _pts(*rows: tuple[float, float]) -> np.ndarray:
    return np.array(rows, dtype=np.float64).reshape(-1, 2)


def test_stop_distance_matches_the_formula() -> None:
    # carrier: v = 2, t_r = 0.10, a = 2 -> 0.2 + 1.0
    assert envelope.stop_distance(CARRIER, 2.0) == pytest.approx(1.2)
    assert envelope.stop_distance(CARRIER, 0.0) == 0.0


def test_separation_distance_matches_the_formula() -> None:
    # v_h*(t_r + v/a) + S_stop + C = 1.6*(0.1 + 1.0) + 1.2 + 0.3
    assert envelope.separation_distance(CARRIER, 2.0, CP) == pytest.approx(3.26)
    assert envelope.separation_distance(CARRIER, 0.0, CP) == pytest.approx(1.6 * 0.1 + 0.3)


@pytest.mark.parametrize("kind", KINDS)
def test_human_cap_is_full_speed_far_away_and_zero_when_too_close(kind: RobotKind) -> None:
    p = ROBOT_PARAMS[kind]
    assert envelope.human_cap(p, 1000.0, CP) == p.max_speed
    assert envelope.human_cap(p, 0.0, CP) == 0.0
    floor = CP.interp_k * envelope.separation_distance(p, 0.0, CP)
    assert envelope.human_cap(p, floor, CP) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("kind", KINDS)
@given(gap=st.floats(min_value=0.0, max_value=30.0))
@settings(max_examples=60, deadline=None)
def test_human_cap_keeps_the_separation_at_the_capped_speed(kind: RobotKind, gap: float) -> None:
    p = ROBOT_PARAMS[kind]
    cap = envelope.human_cap(p, gap, CP)
    assert 0.0 <= cap <= p.max_speed
    if cap > 0.0:
        assert CP.interp_k * envelope.separation_distance(p, cap, CP) <= gap + 1e-9


@pytest.mark.parametrize("kind", KINDS)
def test_human_cap_never_decreases_with_the_gap(kind: RobotKind) -> None:
    p = ROBOT_PARAMS[kind]
    caps = [envelope.human_cap(p, g, CP) for g in np.linspace(0.0, 25.0, 400)]
    assert all(b >= a - 1e-12 for a, b in itertools.pairwise(caps))


@pytest.mark.parametrize("kind", KINDS)
@given(gap=st.floats(min_value=0.0, max_value=30.0))
@settings(max_examples=60, deadline=None)
def test_structure_cap_leaves_room_to_stop(kind: RobotKind, gap: float) -> None:
    p = ROBOT_PARAMS[kind]
    cap = envelope.structure_cap(p, gap, CP)
    assert 0.0 <= cap <= p.max_speed
    if cap > 0.0:
        assert envelope.stop_distance(p, cap) + CP.structure_margin <= gap + 1e-9


def test_structure_cap_is_larger_than_human_cap_at_the_same_gap() -> None:
    assert envelope.structure_cap(CARRIER, 4.0, CP) > envelope.human_cap(CARRIER, 4.0, CP)


def test_straight_path_gap_is_the_distance_to_the_front_face() -> None:
    gap = envelope.path_gap(_pts((3.0, 0.0)), CARRIER, math.inf, CP)
    assert gap == pytest.approx(3.0 - CARRIER.length / 2)


def test_a_point_beside_the_lane_or_behind_is_ignored() -> None:
    wide = CARRIER.width / 2 + CP.lateral_margin + 0.05
    assert envelope.path_gap(_pts((3.0, wide), (3.0, -wide)), CARRIER, math.inf, CP) == math.inf
    assert envelope.path_gap(_pts((-3.0, 0.0)), CARRIER, math.inf, CP) == math.inf


def test_a_point_inside_the_footprint_gives_zero() -> None:
    assert envelope.path_gap(_pts((0.1, 0.1)), CARRIER, math.inf, CP) == 0.0


def test_no_points_gives_infinity() -> None:
    assert envelope.path_gap(np.empty((0, 2)), CARRIER, math.inf, CP) == math.inf


def test_a_non_finite_point_fails_closed_to_zero() -> None:
    assert envelope.path_gap(_pts((math.nan, 1.0)), CARRIER, math.inf, CP) == 0.0
    assert envelope.path_gap(_pts((5.0, math.inf)), CARRIER, 8.0, CP) == 0.0


def test_reverse_mirrors_the_points_through_the_robot() -> None:
    behind = _pts((-3.0, 0.0))
    assert envelope.path_gap(behind, CARRIER, math.inf, CP, reverse=True) == pytest.approx(
        3.0 - CARRIER.length / 2
    )
    assert envelope.path_gap(behind, CARRIER, math.inf, CP) == math.inf


def _brute_gap(points: np.ndarray, p: RobotParams, radius: float) -> float:
    """Independent check: move the rectangle along the arc in 2 mm steps."""
    half_length, half_width = p.length / 2, p.width / 2 + CP.lateral_margin
    best = math.inf
    step = 0.002
    max_s = min(math.pi * abs(radius), 15.0) if math.isfinite(radius) else 15.0
    for s in np.arange(0.0, max_s, step):
        if math.isfinite(radius):
            ang = s / abs(radius)
            sign = 1.0 if radius > 0 else -1.0
            cx, cy = abs(radius) * math.sin(ang), sign * abs(radius) * (1 - math.cos(ang))
            heading = sign * ang
        else:
            cx, cy, heading = s, 0.0, 0.0
        dx, dy = points[:, 0] - cx, points[:, 1] - cy
        lx = dx * math.cos(heading) + dy * math.sin(heading)
        ly = -dx * math.sin(heading) + dy * math.cos(heading)
        if np.any((np.abs(lx) <= half_length) & (np.abs(ly) <= half_width)):
            best = s
            break
    return best


@pytest.mark.parametrize("radius", [4.0, -4.0, 9.0, -2.5])
def test_curved_gap_matches_a_brute_force_sweep(radius: float) -> None:
    rng = np.random.default_rng(7)
    p = CARRIER
    for _ in range(12):
        point = rng.uniform(-3.0, 8.0, size=(1, 2))
        expected = _brute_gap(point, p, radius)
        got = envelope.path_gap(point, p, radius, CP)
        if math.isinf(expected):
            assert got == math.inf or got > 15.0 or got > math.pi * abs(radius) - 0.01
        else:
            assert got == pytest.approx(expected, abs=0.006)


def test_a_curve_makes_a_point_off_axis_reachable() -> None:
    point = _pts((4.0, 1.0))
    assert envelope.path_gap(point, CARRIER, math.inf, CP) == math.inf
    assert math.isfinite(envelope.path_gap(point, CARRIER, 8.5, CP))


def test_path_radius_for_each_kinematics() -> None:
    # bicycle: R = wheelbase / tan(steer)
    assert envelope.path_radius(FORKLIFT, 1.0, 0.3) == pytest.approx(1.6 / math.tan(0.3))
    assert envelope.path_radius(FORKLIFT, -1.0, 0.3) == pytest.approx(1.6 / math.tan(0.3))
    assert envelope.path_radius(FORKLIFT, 1.0, 0.0) == math.inf
    # differential: R = v / omega
    assert envelope.path_radius(CARRIER, 1.0, 0.5) == pytest.approx(2.0)
    assert envelope.path_radius(CARRIER, 1.0, 0.0) == math.inf
    assert envelope.path_radius(CARRIER, 0.0, 0.5) == math.inf


def test_radial_gap_is_the_nearest_distance_minus_the_circumradius() -> None:
    circumradius = math.hypot(CARRIER.length, CARRIER.width) / 2
    gap = envelope.radial_gap(_pts((0.0, 5.0), (-3.0, 0.0)), CARRIER)
    assert gap == pytest.approx(3.0 - circumradius)
    assert envelope.radial_gap(_pts((0.1, 0.0)), CARRIER) == 0.0
    assert envelope.radial_gap(np.empty((0, 2)), CARRIER) == math.inf
    assert envelope.radial_gap(_pts((math.nan, 0.0)), CARRIER) == 0.0


def test_rotation_blocked_when_a_point_is_inside_the_swept_circle() -> None:
    circumradius = math.hypot(CARRIER.length, CARRIER.width) / 2
    near = _pts((circumradius + CP.lateral_margin - 0.01, 0.0))
    far = _pts((circumradius + CP.lateral_margin + 0.05, 0.0))
    assert envelope.rotation_blocked(near, CARRIER, CP)
    assert not envelope.rotation_blocked(far, CARRIER, CP)
    assert not envelope.rotation_blocked(np.empty((0, 2)), CARRIER, CP)
    assert envelope.rotation_blocked(_pts((math.nan, 0.0)), CARRIER, CP)
