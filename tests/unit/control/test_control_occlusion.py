"""waggle.control.occlusion: occlusion boundaries of a scan and the phantom human speed cap."""

import math

import numpy as np
import pytest
from control_support import make_scan
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.control import envelope, occlusion
from waggle.control.params import DEFAULT_CONTROL_PARAMS as CP
from waggle.control.params import DEFAULT_OCCLUSION_PARAMS as OP
from waggle.control.params import DEFAULT_PERCEPTION_PARAMS as PP
from waggle.control.params import ControlParamsError, OcclusionParams
from waggle.control.types import ControlRequest, Reason
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
KINDS = list(RobotKind)
RACK = [(-5.0, 0.7, 4.0, 3.0)]  # a side wall that ends at x = 4, the corner of a cross aisle
STRAIGHT = ControlRequest(2.0, 0.0)


def _pts(*rows: tuple[float, float]) -> np.ndarray:
    return np.array(rows, dtype=np.float64).reshape(-1, 2)


def _reach(v: float) -> float:
    return CP.human_speed_bound * (CARRIER.actuation_delay + v / CARRIER.decel)


def _brute_gap(points: np.ndarray, half_width: float) -> float:
    """Independent check: slide the footprint straight ahead in 5 mm steps."""
    half_length = CARRIER.length / 2
    for s in np.arange(0.0, 15.0, 0.005):
        lx, ly = points[:, 0] - s, points[:, 1]
        if np.any((np.abs(lx) <= half_length) & (np.abs(ly) <= half_width)):
            return float(s)
    return math.inf


def _feasible(points: np.ndarray, v: float) -> bool:
    half_width = CARRIER.width / 2 + CP.lateral_margin + _reach(v)
    return CP.interp_k * envelope.separation_distance(CARRIER, v, CP) <= _brute_gap(
        points, half_width
    )


def test_the_end_of_a_side_wall_is_a_boundary() -> None:
    points = occlusion.boundary_points(make_scan(boxes=RACK), PP, OP)
    near_corner = np.hypot(points[:, 0] - 4.0, points[:, 1] - 0.7)
    assert near_corner.min() < 0.2


def test_an_empty_scan_has_no_boundary_and_no_cap() -> None:
    points = occlusion.boundary_points(make_scan(), PP, OP)
    assert points.shape == (0, 2)
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP) == CARRIER.max_speed


def test_a_smooth_wall_is_not_a_boundary() -> None:
    wall = make_scan(boxes=[(5.0, -30.0, 6.0, 30.0)])
    points = occlusion.boundary_points(wall, PP, OP)
    assert np.all(np.abs(points[:, 1]) > 8.0) or points.shape[0] == 0


def test_a_step_smaller_than_a_person_is_not_a_boundary() -> None:
    step = make_scan(boxes=[(4.0, -3.0, 5.0, 0.05), (4.3, -0.05, 5.0, 3.0)])
    points = occlusion.boundary_points(step, PP, OP)
    assert not np.any((np.abs(points[:, 1]) < 2.0) & (points[:, 0] < 5.0))


def test_a_dropped_ray_does_not_make_a_boundary() -> None:
    wall = make_scan(boxes=[(5.0, -30.0, 6.0, 30.0)], nan_rays=[180])
    points = occlusion.boundary_points(wall, PP, OP)
    assert not np.any(np.abs(points[:, 1]) < 5.0)


def test_the_cap_leaves_room_for_a_person_stepping_out_of_the_shadow() -> None:
    points = occlusion.boundary_points(make_scan(boxes=RACK), PP, OP)
    cap = occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP)
    assert 0.0 < cap < CARRIER.max_speed
    assert _feasible(points, max(cap - 0.01, 0.0))
    assert not _feasible(points, cap + 0.03)


def test_a_boundary_far_to_the_side_does_not_slow_the_robot() -> None:
    points = _pts((5.0, 6.0))
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP) == CARRIER.max_speed


def test_no_non_negative_root_gives_zero() -> None:
    points = _pts((1.0, 0.0))
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP) == 0.0


def test_a_non_finite_boundary_fails_closed() -> None:
    points = _pts((math.nan, 1.0))
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP) == 0.0


def test_reverse_uses_the_boundaries_behind_the_robot() -> None:
    behind = _pts((-4.0, 0.7))
    backwards = ControlRequest(-2.0, 0.0)
    assert occlusion.occlusion_cap(backwards, CARRIER, behind, CP, OP) < CARRIER.max_speed
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, behind, CP, OP) == CARRIER.max_speed


def test_a_turn_makes_a_boundary_off_axis_matter() -> None:
    points = _pts((2.5, 2.6))
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP) == CARRIER.max_speed
    arc = occlusion.occlusion_cap(ControlRequest(2.0, 0.4), CARRIER, points, CP, OP)
    assert arc < CARRIER.max_speed


def test_a_robot_that_does_not_move_is_not_limited() -> None:
    points = _pts((0.5, 0.0))
    limit = occlusion.occlusion_limit(ControlRequest(0.0, 0.5), CARRIER, points, CP, OP)
    assert limit.speed_cap == CARRIER.max_speed


def test_the_limit_carries_the_occlusion_reason() -> None:
    limit = occlusion.occlusion_limit(STRAIGHT, CARRIER, _pts((3.0, 0.5)), CP, OP)
    assert limit.reason is Reason.OCCLUSION


def test_a_tiny_speed_does_not_collapse_the_turning_circle() -> None:
    points = _pts((3.0, 0.0))
    slow = ControlRequest(1e-6, 0.5)
    cap = occlusion.occlusion_cap(slow, CARRIER, points, CP, OP)
    assert math.isfinite(cap) and 0.0 <= cap <= CARRIER.max_speed


@pytest.mark.parametrize("kind", KINDS)
@given(
    x=st.floats(-3.0, 14.0),
    y=st.floats(-5.0, 5.0),
    turn=st.floats(-0.3, 0.3),
    forward=st.booleans(),
)
@settings(max_examples=60, deadline=None)
def test_the_cap_stays_between_zero_and_the_class_maximum(
    kind: RobotKind, x: float, y: float, turn: float, forward: bool
) -> None:
    p = ROBOT_PARAMS[kind]
    request = ControlRequest(p.max_speed if forward else -p.max_speed, turn)
    cap = occlusion.occlusion_cap(request, p, _pts((x, y)), CP, OP)
    assert 0.0 <= cap <= p.max_speed


@given(x=st.floats(0.5, 12.0), y=st.floats(-3.0, 3.0), shift=st.floats(0.0, 4.0))
@settings(max_examples=60, deadline=None)
def test_a_boundary_further_ahead_never_lowers_the_cap(x: float, y: float, shift: float) -> None:
    near = occlusion.occlusion_cap(STRAIGHT, CARRIER, _pts((x, y)), CP, OP)
    far = occlusion.occlusion_cap(STRAIGHT, CARRIER, _pts((x + shift, y)), CP, OP)
    assert far >= near - 1e-9


def test_more_boundaries_never_raise_the_cap() -> None:
    one = _pts((5.0, 0.8))
    two = _pts((5.0, 0.8), (3.5, 0.6))
    assert occlusion.occlusion_cap(STRAIGHT, CARRIER, two, CP, OP) <= occlusion.occlusion_cap(
        STRAIGHT, CARRIER, one, CP, OP
    )


def test_the_cap_is_deterministic() -> None:
    points = occlusion.boundary_points(make_scan(boxes=RACK), PP, OP)
    first = occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP)
    assert first == occlusion.occlusion_cap(STRAIGHT, CARRIER, points, CP, OP)


@pytest.mark.parametrize("name", ["jump_min", "speed_floor"])
@pytest.mark.parametrize("bad", [0.0, -1.0, math.inf, math.nan])
def test_params_reject_values_that_are_not_finite_and_positive(name: str, bad: float) -> None:
    with pytest.raises(ControlParamsError):
        OcclusionParams(**{name: bad})
