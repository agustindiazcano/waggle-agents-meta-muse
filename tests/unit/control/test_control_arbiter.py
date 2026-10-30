"""waggle.control.arbiter: the minimum over all limits, never above the request."""

import itertools
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.control.arbiter import arbitrate
from waggle.control.types import ControlRequest, Limit, Reason
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
FORKLIFT = ROBOT_PARAMS[RobotKind.FORKLIFT]

caps = st.floats(min_value=0.0, max_value=5.0)
reasons = st.sampled_from([r for r in Reason if r is not Reason.REQUEST])
limits = st.lists(st.builds(Limit, caps, reasons), min_size=0, max_size=6)


def test_no_limits_passes_the_request_with_reason_request() -> None:
    out = arbitrate(ControlRequest(speed=1.0, turn=0.4), CARRIER, [])
    assert (out.speed, out.turn, out.reason, out.limits_hit) == (1.0, 0.4, Reason.REQUEST, ())


def test_the_smallest_cap_wins_and_names_the_binding_reason() -> None:
    out = arbitrate(
        ControlRequest(speed=1.8, turn=0.0),
        CARRIER,
        [Limit(1.2, Reason.OCCLUSION), Limit(0.7, Reason.ENVELOPE), Limit(1.5, Reason.CPA)],
    )
    assert out.speed == pytest.approx(0.7)
    assert out.reason is Reason.ENVELOPE
    assert set(out.limits_hit) == {Reason.OCCLUSION, Reason.ENVELOPE, Reason.CPA}


def test_a_limit_above_the_request_is_not_reported() -> None:
    out = arbitrate(ControlRequest(speed=1.0, turn=0.0), CARRIER, [Limit(1.5, Reason.ENVELOPE)])
    assert out.speed == 1.0
    assert out.limits_hit == ()


def test_zero_wins_and_estop_is_the_most_severe_reason() -> None:
    out = arbitrate(
        ControlRequest(speed=1.0, turn=0.2),
        CARRIER,
        [Limit(0.0, Reason.ENVELOPE), Limit(0.0, Reason.ESTOP), Limit(0.3, Reason.CPA)],
    )
    assert out.speed == 0.0
    assert out.turn == 0.0
    assert out.reason is Reason.ESTOP


def test_class_maximum_clamps_the_request() -> None:
    out = arbitrate(ControlRequest(speed=3.5, turn=0.0), CARRIER, [])
    assert out.speed == CARRIER.max_speed
    assert out.reason is Reason.CLASS_MAX


def test_differential_drive_scales_angular_speed_by_the_same_factor() -> None:
    out = arbitrate(ControlRequest(speed=2.0, turn=1.0), CARRIER, [Limit(0.5, Reason.ENVELOPE)])
    assert out.speed == pytest.approx(0.5)
    assert out.turn == pytest.approx(0.25)
    assert out.speed / out.turn == pytest.approx(2.0 / 1.0)


def test_differential_angular_speed_is_clamped_to_the_class_maximum_on_the_same_path() -> None:
    out = arbitrate(ControlRequest(speed=1.0, turn=3.0), CARRIER, [])
    assert out.turn == pytest.approx(CARRIER.max_angular_speed)
    assert out.speed / out.turn == pytest.approx(1.0 / 3.0)
    assert out.reason is Reason.CLASS_MAX


def test_bicycle_keeps_the_steering_angle_when_the_speed_is_reduced() -> None:
    out = arbitrate(ControlRequest(speed=1.4, turn=0.3), FORKLIFT, [Limit(0.4, Reason.ENVELOPE)])
    assert out.speed == pytest.approx(0.4)
    assert out.turn == 0.3


def test_a_stop_keeps_the_steering_of_a_bicycle() -> None:
    out = arbitrate(ControlRequest(speed=1.4, turn=0.3), FORKLIFT, [Limit(0.0, Reason.ENVELOPE)])
    assert (out.speed, out.turn) == (0.0, 0.3)


def test_steering_beyond_the_maximum_is_clamped() -> None:
    out = arbitrate(ControlRequest(speed=1.0, turn=0.9), FORKLIFT, [])
    assert out.turn == FORKLIFT.max_steer
    assert out.reason is Reason.CLASS_MAX


def test_reverse_keeps_its_sign_and_is_limited_in_magnitude() -> None:
    out = arbitrate(ControlRequest(speed=-1.5, turn=0.0), CARRIER, [Limit(0.6, Reason.ENVELOPE)])
    assert out.speed == pytest.approx(-0.6)


def test_pure_rotation_is_allowed_unless_a_limit_is_zero() -> None:
    free = arbitrate(ControlRequest(speed=0.0, turn=1.0), CARRIER, [Limit(0.0, Reason.ENVELOPE)])
    assert free.turn == 0.0
    assert free.reason is Reason.ENVELOPE
    ok = arbitrate(ControlRequest(speed=0.0, turn=1.0), CARRIER, [])
    assert ok.turn == 1.0


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_a_non_finite_request_fails_closed(bad: float) -> None:
    for request in (ControlRequest(bad, 0.0), ControlRequest(1.0, bad)):
        out = arbitrate(request, CARRIER, [])
        assert (out.speed, out.turn, out.reason) == (0.0, 0.0, Reason.INPUT_MISSING)


@pytest.mark.parametrize("cap", [math.nan, -0.5, math.inf])
def test_a_malformed_limit_fails_closed(cap: float) -> None:
    out = arbitrate(ControlRequest(1.0, 0.0), CARRIER, [Limit(cap, Reason.CPA)])
    assert out.speed == 0.0
    assert out.reason is Reason.INPUT_MISSING


@given(limits=limits, speed=st.floats(min_value=-3.0, max_value=3.0))
@settings(max_examples=150, deadline=None)
def test_output_is_never_above_the_request_nor_any_limit(limits: list[Limit], speed: float) -> None:
    out = arbitrate(ControlRequest(speed=speed, turn=0.0), CARRIER, limits)
    assert abs(out.speed) <= abs(speed) + 1e-12
    assert abs(out.speed) <= CARRIER.max_speed + 1e-12
    assert out.speed == 0.0 or math.copysign(1.0, out.speed) == math.copysign(1.0, speed)
    for limit in limits:
        assert abs(out.speed) <= limit.speed_cap + 1e-12


@given(limits=st.lists(st.builds(Limit, caps, reasons), min_size=2, max_size=4))
@settings(max_examples=60, deadline=None)
def test_the_result_does_not_depend_on_the_order_of_the_limits(limits: list[Limit]) -> None:
    request = ControlRequest(speed=2.0, turn=0.8)
    first = arbitrate(request, CARRIER, limits)
    for permutation in itertools.permutations(limits):
        assert arbitrate(request, CARRIER, list(permutation)) == first


@given(limits=limits, extra=st.builds(Limit, caps, reasons))
@settings(max_examples=100, deadline=None)
def test_adding_a_limit_never_raises_the_speed(limits: list[Limit], extra: Limit) -> None:
    request = ControlRequest(speed=2.0, turn=0.0)
    before = arbitrate(request, CARRIER, limits)
    after = arbitrate(request, CARRIER, [*limits, extra])
    assert abs(after.speed) <= abs(before.speed) + 1e-12


def test_a_tiny_request_is_still_held_to_a_zero_limit() -> None:
    out = arbitrate(ControlRequest(speed=1e-9, turn=0.0), CARRIER, [Limit(0.0, Reason.ENVELOPE)])
    assert out.speed == 0.0
    assert out.reason is Reason.ENVELOPE
