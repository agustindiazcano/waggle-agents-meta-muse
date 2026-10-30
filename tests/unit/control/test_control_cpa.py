"""waggle.control.cpa: constant velocity closest point of approach, a limit that only restricts."""

import math

import numpy as np
import pytest
from control_support import make_odometry
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.control import cpa, envelope, tracking
from waggle.control.limiter import limit_command
from waggle.control.params import DEFAULT_CONTROL_PARAMS as CP
from waggle.control.params import DEFAULT_CPA_PARAMS as CPAP
from waggle.control.params import DEFAULT_PERCEPTION_PARAMS as PP
from waggle.control.params import ControlParamsError, CpaParams
from waggle.control.tracking import Detection, Track, TrackState
from waggle.control.types import ControlRequest, Reason
from waggle.sim.params import DT, HUMAN_RADIUS, ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
STRAIGHT = ControlRequest(2.0, 0.0)
NOW = 100
NO_POINTS = np.empty((0, 2))


def _track(x: float, y: float, vx: float, vy: float, ticks: int = 40, seen: int = NOW) -> Track:
    """A track whose trail is a straight walk of ``ticks`` ticks ending at ``(x, y)``."""
    trail = tuple((seen - k, x - vx * k * DT, y - vy * k * DT) for k in range(ticks, -1, -1))
    return Track(1, x, y, vx, vy, HUMAN_RADIUS, 0.1, seen, trail)


def _cap(tracks: tuple[Track, ...], request: ControlRequest = STRAIGHT, tick: int = NOW) -> float:
    limit = cpa.cpa_limit(request, CARRIER, make_odometry(tick=tick), tracks, tick, CP, PP, CPAP)
    assert limit.reason is Reason.CPA
    return limit.speed_cap


def test_a_human_crossing_toward_the_lane_slows_the_robot_before_the_envelope_sees_it() -> None:
    crossing = _track(1.5, 1.4, 0.0, -1.2)
    point = np.array([[1.5, 1.4]])
    envelope_only = limit_command(STRAIGHT, CARRIER, point, NO_POINTS, 0.0, CP)
    assert envelope_only.speed == STRAIGHT.speed
    assert 0.0 < _cap((crossing,)) < CARRIER.max_speed


def test_a_human_walking_away_does_not_limit_the_robot() -> None:
    assert _cap((_track(4.0, 2.4, 0.0, 1.2),)) == CARRIER.max_speed


def test_a_human_far_from_the_path_does_not_limit_the_robot() -> None:
    assert _cap((_track(4.0, 9.0, 0.0, 0.0),)) == CARRIER.max_speed


def test_a_track_without_a_velocity_estimate_adds_no_restriction() -> None:
    short = _track(4.0, 2.4, 0.0, -1.2, ticks=3)
    assert _cap((short,)) == CARRIER.max_speed


def test_a_track_not_seen_for_a_while_adds_no_restriction() -> None:
    old = _track(4.0, 2.4, 0.0, -1.2, seen=NOW - PP.max_scan_age_ticks - 1)
    assert _cap((old,)) == CARRIER.max_speed


def test_a_human_already_inside_the_widened_footprint_gives_zero() -> None:
    assert _cap((_track(0.5, 0.0, 0.0, 0.0),)) == 0.0


def test_the_cap_leaves_room_to_stop_before_the_predicted_meeting() -> None:
    track = _track(1.5, 1.4, 0.0, -1.2)
    cap = _cap((track,))
    # independent sweep: first time the human centre is inside the footprint widened by the
    # human radius and the lateral margin, robot moving straight at the requested speed
    half_length = CARRIER.length / 2 + HUMAN_RADIUS + CP.lateral_margin
    half_width = CARRIER.width / 2 + HUMAN_RADIUS + CP.lateral_margin
    meet = next(
        t
        for t in np.arange(0.0, 3.0, 0.001)
        if abs(1.5 - STRAIGHT.speed * t) <= half_length and abs(1.4 - 1.2 * t) <= half_width
    )
    room = STRAIGHT.speed * meet
    assert envelope.stop_distance(CARRIER, cap) + CP.structure_margin <= room + 0.25
    assert cap < CARRIER.max_speed


def test_a_robot_that_does_not_move_is_not_limited() -> None:
    limit = cpa.cpa_limit(
        ControlRequest(0.0, 0.4),
        CARRIER,
        make_odometry(tick=NOW),
        (_track(0.5, 0.0, 0.0, 0.0),),
        NOW,
        CP,
        PP,
        CPAP,
    )
    assert limit.speed_cap == CARRIER.max_speed


def test_reverse_looks_behind() -> None:
    behind = _track(-1.5, 1.4, 0.0, -1.2)
    assert _cap((behind,), ControlRequest(-2.0, 0.0)) < CARRIER.max_speed
    assert _cap((behind,)) == CARRIER.max_speed


def test_the_robot_pose_is_taken_from_the_odometry() -> None:
    track = _track(11.5, 1.4, 0.0, -1.2)
    moved = make_odometry(tick=NOW, x=10.0)
    limit = cpa.cpa_limit(STRAIGHT, CARRIER, moved, (track,), NOW, CP, PP, CPAP)
    assert limit.speed_cap < CARRIER.max_speed


def test_a_turn_follows_the_arc() -> None:
    track = _track(1.2, 0.9, 0.0, 0.0)
    straight = _cap((track,))
    arc = _cap((track,), ControlRequest(2.0, 0.5))
    assert straight == CARRIER.max_speed
    assert arc < CARRIER.max_speed


def test_more_tracks_never_raise_the_cap() -> None:
    one = _track(1.5, 1.4, 0.0, -1.2)
    two = _track(2.5, 1.6, 0.0, -1.0)
    assert _cap((one, two)) <= _cap((one,))


def test_a_non_finite_track_fails_closed() -> None:
    bad = _track(math.nan, 2.0, 0.0, -1.0)
    assert _cap((bad,)) == 0.0


@given(
    x=st.floats(-8.0, 12.0),
    y=st.floats(-6.0, 6.0),
    vx=st.floats(-1.6, 1.6),
    vy=st.floats(-1.6, 1.6),
    turn=st.floats(-0.8, 0.8),
)
@settings(max_examples=80, deadline=None)
def test_the_cap_stays_between_zero_and_the_class_maximum(
    x: float, y: float, vx: float, vy: float, turn: float
) -> None:
    cap = _cap((_track(x, y, vx, vy),), ControlRequest(2.0, turn))
    assert 0.0 <= cap <= CARRIER.max_speed


def test_the_cap_is_deterministic() -> None:
    tracks = (_track(1.5, 1.4, 0.0, -1.2),)
    assert _cap(tracks) == _cap(tracks)


@pytest.mark.parametrize("name", ["horizon", "step"])
@pytest.mark.parametrize("bad", [0.0, -1.0, math.inf, math.nan])
def test_params_reject_values_that_are_not_finite_and_positive(name: str, bad: float) -> None:
    with pytest.raises(ControlParamsError):
        CpaParams(**{name: bad})


def test_a_trail_gives_a_smoothed_velocity_over_more_than_one_tick() -> None:
    rng = np.random.default_rng(3)
    track = _track(5.0, 3.0, 0.0, -1.2)
    noisy = tuple(
        (t, x + float(rng.normal(0, 0.1)), y + float(rng.normal(0, 0.1))) for t, x, y in track.trail
    )
    velocity = tracking.smoothed_velocity(Track(1, 5.0, 3.0, 0.0, 0.0, 0.3, 0.1, NOW, noisy), PP)
    assert velocity is not None
    assert velocity[1] == pytest.approx(-1.2, abs=0.35)
    assert abs(velocity[0]) < 0.35


def test_a_short_trail_has_no_velocity() -> None:
    assert tracking.smoothed_velocity(_track(5.0, 3.0, 0.0, -1.2, ticks=2), PP) is None


def test_the_smoothed_velocity_is_clipped_to_the_human_speed_bound() -> None:
    fast = _track(5.0, 3.0, 0.0, -5.0)
    velocity = tracking.smoothed_velocity(fast, PP)
    assert velocity is not None
    assert math.hypot(*velocity) <= PP.human_speed_bound + 1e-9


def test_tracks_keep_a_trail_of_recent_detections_only() -> None:
    state = TrackState()
    for k in range(PP.trail_ticks * 2):
        det = Detection(1.0 + 0.01 * k, 2.0, HUMAN_RADIUS, 0.1, k)
        state = tracking.update_tracks(state, [det], k, PP)
    trail = state.tracks[0].trail
    assert trail[-1][0] == PP.trail_ticks * 2 - 1
    assert trail[-1][0] - trail[0][0] <= PP.trail_ticks
