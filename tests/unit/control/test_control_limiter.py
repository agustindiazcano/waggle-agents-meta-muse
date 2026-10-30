"""waggle.control.limiter: envelope limits for one command, composed through the arbiter."""

import math

import numpy as np
import pytest

from waggle.control.limiter import EnvelopeMode, limit_command
from waggle.control.params import DEFAULT_CONTROL_PARAMS as CP
from waggle.control.types import ControlRequest, Reason
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
NONE = np.empty((0, 2))


def _pts(*rows: tuple[float, float]) -> np.ndarray:
    return np.array(rows, dtype=np.float64).reshape(-1, 2)


def _limit(
    request: ControlRequest,
    human: np.ndarray = NONE,
    structure: np.ndarray = NONE,
    current: float = 0.0,
    mode: EnvelopeMode = EnvelopeMode.SWEPT,
) -> tuple[float, Reason]:
    out = limit_command(request, CARRIER, human, structure, current, CP, mode)
    return out.speed, out.reason


def test_nothing_detected_passes_the_request() -> None:
    assert _limit(ControlRequest(1.5, 0.0)) == (1.5, Reason.REQUEST)


def test_a_human_ahead_lowers_the_speed_to_the_separation_cap() -> None:
    gap = 3.0
    speed, reason = _limit(ControlRequest(2.0, 0.0), human=_pts((gap + CARRIER.length / 2, 0.0)))
    assert reason is Reason.ENVELOPE
    assert 0.0 < speed < 2.0
    assert (
        CP.interp_k * (1.6 * (0.1 + speed / 2.0) + (speed * 0.1 + speed**2 / 4.0) + CP.human_margin)
        <= gap + 1e-9
    )


def test_a_structure_ahead_only_needs_room_to_stop() -> None:
    point = _pts((3.0 + CARRIER.length / 2, 0.0))
    structure_speed, _ = _limit(ControlRequest(2.0, 0.0), structure=point)
    human_speed, _ = _limit(ControlRequest(2.0, 0.0), human=point)
    assert human_speed < structure_speed <= 2.0


def test_a_human_off_the_path_does_not_limit_a_straight_robot() -> None:
    off = _pts((4.0, 3.0))
    assert _limit(ControlRequest(1.5, 0.0), human=off) == (1.5, Reason.REQUEST)


def test_the_robot_stops_with_estop_when_the_gap_is_inside_the_stopping_distance() -> None:
    gap = 0.4
    speed, reason = _limit(
        ControlRequest(1.5, 0.0), human=_pts((gap + CARRIER.length / 2, 0.0)), current=1.5
    )
    assert (speed, reason) == (0.0, Reason.ESTOP)


def test_a_close_human_at_standstill_gives_a_zero_cap_with_reason_envelope() -> None:
    speed, reason = _limit(ControlRequest(1.0, 0.0), human=_pts((0.9, 0.0)), current=0.0)
    assert (speed, reason) == (0.0, Reason.ENVELOPE)


def test_a_curve_brings_an_off_axis_human_into_the_path() -> None:
    off = _pts((3.0, 0.9))
    straight, _ = _limit(ControlRequest(1.5, 0.0), human=off)
    curved, reason = _limit(ControlRequest(1.5, 0.176), human=off)
    assert straight == 1.5
    assert curved < 1.5
    assert reason is Reason.ENVELOPE


def test_reverse_looks_behind() -> None:
    behind = _pts((-3.0, 0.0))
    assert _limit(ControlRequest(-1.5, 0.0), human=behind)[0] > -1.5
    assert _limit(ControlRequest(1.5, 0.0), human=behind) == (1.5, Reason.REQUEST)


def test_pure_rotation_is_blocked_by_a_point_inside_the_swept_circle() -> None:
    out = limit_command(
        ControlRequest(0.0, 1.0), CARRIER, _pts((0.8, 0.0)), NONE, 0.0, CP, EnvelopeMode.SWEPT
    )
    assert (out.speed, out.turn, out.reason) == (0.0, 0.0, Reason.ENVELOPE)
    free = limit_command(ControlRequest(0.0, 1.0), CARRIER, NONE, NONE, 0.0, CP, EnvelopeMode.SWEPT)
    assert free.turn == 1.0


def test_radial_mode_limits_on_the_nearest_distance_even_off_the_path() -> None:
    near_off_path = _pts((0.0, 3.0))
    swept = _limit(ControlRequest(2.0, 0.0), human=near_off_path, mode=EnvelopeMode.SWEPT)
    radial = _limit(ControlRequest(2.0, 0.0), human=near_off_path, mode=EnvelopeMode.RADIAL)
    assert swept == (2.0, Reason.REQUEST)
    assert radial[0] < 2.0
    assert radial[1] is Reason.ENVELOPE


def test_a_non_finite_point_stops_the_robot() -> None:
    speed, reason = _limit(ControlRequest(1.0, 0.0), human=_pts((math.nan, 0.0)))
    assert speed == 0.0
    assert reason in (Reason.ENVELOPE, Reason.ESTOP)


@pytest.mark.parametrize("gap", [0.5, 1.0, 2.0, 4.0, 8.0])
def test_the_output_never_exceeds_the_request(gap: float) -> None:
    out = limit_command(
        ControlRequest(1.2, 0.3),
        CARRIER,
        _pts((gap + 0.6, 0.0)),
        NONE,
        1.2,
        CP,
        EnvelopeMode.SWEPT,
    )
    assert out.speed <= 1.2
    assert abs(out.turn) <= 0.3 + 1e-12
