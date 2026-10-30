"""waggle.control.reflex: heartbeat watchdog, e-stop, hazard geofences, telemetry thresholds."""

import math

import numpy as np
import pytest
from control_support import make_odometry
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.control import envelope, reflex
from waggle.control.params import DEFAULT_CONTROL_PARAMS as CP
from waggle.control.params import DEFAULT_REFLEX_PARAMS as RP
from waggle.control.params import ControlParamsError, ReflexParams
from waggle.control.reflex import Geofence, TelemetryReading
from waggle.control.types import ControlRequest, Reason
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
STRAIGHT = ControlRequest(2.0, 0.0)
NOW = 200


def _square(x0: float, y0: float, x1: float, y1: float) -> Geofence:
    return Geofence("g", ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


def _cap(
    fences: tuple[Geofence, ...],
    request: ControlRequest = STRAIGHT,
    x: float = 0.0,
    y: float = 0.0,
    theta: float = 0.0,
) -> float:
    odom = make_odometry(tick=NOW, x=x, y=y, theta=theta)
    limit = reflex.geofence_limit(request, CARRIER, odom, fences, CP, RP)
    assert limit.reason is Reason.GEOFENCE
    return limit.speed_cap


def test_a_fresh_heartbeat_does_not_limit() -> None:
    assert reflex.watchdog_limit(NOW - 5, NOW, RP) is None


def test_a_missing_or_stale_heartbeat_stops_with_watchdog() -> None:
    for beat in (None, NOW - RP.heartbeat_timeout_ticks - 1):
        limit = reflex.watchdog_limit(beat, NOW, RP)
        assert limit is not None
        assert (limit.speed_cap, limit.reason) == (0.0, Reason.WATCHDOG)


def test_the_heartbeat_at_the_timeout_is_still_valid() -> None:
    assert reflex.watchdog_limit(NOW - RP.heartbeat_timeout_ticks, NOW, RP) is None


def test_a_heartbeat_from_the_future_fails_closed() -> None:
    limit = reflex.watchdog_limit(NOW + 1, NOW, RP)
    assert limit is not None and limit.speed_cap == 0.0


def test_estop_stops_and_no_estop_does_not_limit() -> None:
    limit = reflex.estop_limit(True)
    assert limit is not None and (limit.speed_cap, limit.reason) == (0.0, Reason.ESTOP)
    assert reflex.estop_limit(False) is None


def test_a_reading_below_the_warning_threshold_sets_no_geofence() -> None:
    reading = TelemetryReading("m1", 5.0, 5.0, value=60.0, warn=80.0, critical=95.0)
    assert reflex.telemetry_geofences((reading,), RP) == ()


@pytest.mark.parametrize(
    ("value", "radius"),
    [(85.0, RP.warn_radius), (95.0, RP.critical_radius), (120.0, RP.critical_radius)],
)
def test_a_reading_over_a_threshold_sets_a_geofence_of_its_severity(
    value: float, radius: float
) -> None:
    reading = TelemetryReading("m1", 5.0, 5.0, value=value, warn=80.0, critical=95.0)
    (fence,) = reflex.telemetry_geofences((reading,), RP)
    assert len(fence.vertices) == RP.polygon_sides
    distances = [math.hypot(x - 5.0, y - 5.0) for x, y in fence.vertices]
    outer = radius / math.cos(math.pi / RP.polygon_sides)
    assert min(distances) == pytest.approx(outer, rel=1e-9)
    assert max(distances) == pytest.approx(outer, rel=1e-9)


def test_a_reading_that_is_not_a_number_is_treated_as_critical() -> None:
    reading = TelemetryReading("m1", 5.0, 5.0, value=math.nan, warn=80.0, critical=95.0)
    (fence,) = reflex.telemetry_geofences((reading,), RP)
    assert max(math.hypot(x - 5.0, y - 5.0) for x, y in fence.vertices) >= RP.critical_radius


def test_a_fence_ahead_leaves_room_to_stop_before_it() -> None:
    cap = _cap((_square(1.5, -1.0, 3.5, 1.0),))
    gap = 1.5 - CARRIER.length / 2
    assert 0.0 < cap < CARRIER.max_speed
    assert envelope.stop_distance(CARRIER, cap) + CP.structure_margin == pytest.approx(
        gap, abs=0.03
    )


def test_a_fence_beside_the_lane_does_not_limit() -> None:
    assert _cap((_square(2.0, 2.0, 4.0, 4.0),)) == CARRIER.max_speed


def test_a_fence_far_ahead_does_not_limit() -> None:
    assert _cap((_square(30.0, -1.0, 32.0, 1.0),)) == CARRIER.max_speed


def test_a_robot_inside_a_fence_may_only_creep_out() -> None:
    assert _cap((_square(-2.0, -2.0, 2.0, 2.0),)) == RP.escape_speed


def test_a_fence_edge_under_the_footprint_counts_as_inside() -> None:
    assert _cap((_square(0.2, -3.0, 5.0, 3.0),)) == RP.escape_speed


def test_a_fence_behind_matters_only_in_reverse() -> None:
    fence = _square(-3.5, -1.0, -1.5, 1.0)
    assert _cap((fence,)) == CARRIER.max_speed
    assert _cap((fence,), ControlRequest(-2.0, 0.0)) < CARRIER.max_speed


def test_the_pose_and_heading_come_from_the_odometry() -> None:
    fence = _square(-1.0, 11.5, 1.0, 13.5)
    assert _cap((fence,)) == CARRIER.max_speed
    assert _cap((fence,), y=10.0, theta=math.pi / 2) < CARRIER.max_speed


def test_a_robot_that_does_not_move_is_not_limited_by_a_fence() -> None:
    assert _cap((_square(0.8, -1.0, 2.0, 1.0),), ControlRequest(0.0, 0.5)) == CARRIER.max_speed


def test_a_malformed_fence_fails_closed() -> None:
    too_few = Geofence("g", ((1.0, 1.0), (2.0, 2.0)))
    not_finite = Geofence("g", ((1.0, 1.0), (math.nan, 2.0), (3.0, 1.0)))
    assert _cap((too_few,)) == 0.0
    assert _cap((not_finite,)) == 0.0


def test_more_fences_never_raise_the_cap() -> None:
    one = _square(4.0, -1.0, 6.0, 1.0)
    two = _square(1.5, -1.0, 2.0, 1.0)
    assert _cap((one, two)) <= _cap((one,))


@given(
    x0=st.floats(-10.0, 10.0),
    y0=st.floats(-6.0, 6.0),
    w=st.floats(0.2, 6.0),
    h=st.floats(0.2, 6.0),
    turn=st.floats(-0.8, 0.8),
)
@settings(max_examples=80, deadline=None)
def test_the_cap_stays_between_zero_and_the_class_maximum(
    x0: float, y0: float, w: float, h: float, turn: float
) -> None:
    cap = _cap((_square(x0, y0, x0 + w, y0 + h),), ControlRequest(2.0, turn))
    assert 0.0 <= cap <= CARRIER.max_speed


def test_the_fence_boundary_is_sampled_finer_than_the_footprint() -> None:
    points = reflex.boundary_samples(_square(0.0, 0.0, 2.0, 0.0 + 1.0), RP)
    gaps = np.hypot(*np.diff(points, axis=0).T)
    assert gaps.max() <= RP.edge_spacing + 1e-9


@pytest.mark.parametrize("bad", [0.0, -1.0, math.inf, math.nan])
def test_params_reject_values_that_are_not_finite_and_positive(bad: float) -> None:
    with pytest.raises(ControlParamsError):
        ReflexParams(escape_speed=bad)
    with pytest.raises(ControlParamsError):
        ReflexParams(edge_spacing=bad)
    with pytest.raises(ControlParamsError):
        ReflexParams(warn_radius=bad)
    with pytest.raises(ControlParamsError):
        ReflexParams(critical_radius=bad)


def test_params_reject_a_critical_radius_below_the_warning_radius() -> None:
    with pytest.raises(ControlParamsError):
        ReflexParams(warn_radius=3.0, critical_radius=2.0)
