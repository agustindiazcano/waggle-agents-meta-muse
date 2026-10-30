"""waggle.control.tracking: association, velocity estimate, coasting and the points of a track."""

import math

import numpy as np
import pytest

from waggle.control import tracking
from waggle.control.params import DEFAULT_PERCEPTION_PARAMS as PP
from waggle.control.tracking import Detection, TrackState
from waggle.sim.params import DT


def _det(x: float, y: float, tick: int, sigma: float = 0.0, body: float = 0.3) -> Detection:
    return Detection(x, y, body, sigma, tick)


def _radius(points: np.ndarray) -> float:
    return float(np.max(np.hypot(points[:, 0] - 3.0, points[:, 1])))


def _step(state: TrackState, tick: int, *dets: Detection) -> TrackState:
    return tracking.update_tracks(state, list(dets), tick, PP)


def test_a_first_detection_starts_a_track_with_zero_velocity() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    assert len(state.tracks) == 1
    track = state.tracks[0]
    assert (track.track_id, track.vx, track.vy) == (0, 0.0, 0.0)


def test_the_same_object_keeps_its_id_and_gets_a_smoothed_velocity() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    state = _step(state, 4, _det(3.1, 0.0, 4))
    track = state.tracks[0]
    assert track.track_id == 0
    measured = 0.1 / (4 * DT)
    assert track.vx == pytest.approx(PP.velocity_alpha * measured)


def test_velocity_converges_to_a_steady_motion() -> None:
    state = TrackState()
    for step in range(12):
        state = _step(state, 4 * step, _det(3.0 + 0.1 * step, 0.0, 4 * step))
    assert state.tracks[0].vx == pytest.approx(1.0, abs=0.02)


def test_velocity_is_clipped_to_the_human_speed_bound() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    state = _step(state, 4, _det(3.9, 0.0, 4))
    assert math.hypot(state.tracks[0].vx, state.tracks[0].vy) <= PP.human_speed_bound + 1e-9


def test_a_detection_outside_the_gate_starts_a_new_track() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    state = _step(state, 4, _det(8.0, 0.0, 4))
    assert {t.track_id for t in state.tracks} == {0, 1}


def test_two_tracks_are_matched_to_their_nearest_detection() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0), _det(3.0, 1.5, 0))
    state = _step(state, 4, _det(3.0, 1.55, 4), _det(3.05, 0.0, 4))
    by_id = {t.track_id: t for t in state.tracks}
    assert by_id[0].y == pytest.approx(0.0)
    assert by_id[1].y == pytest.approx(1.55)


def test_an_unseen_track_coasts_and_keeps_its_last_position() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    state = _step(state, 8)
    assert len(state.tracks) == 1
    assert (state.tracks[0].x, state.tracks[0].y) == (3.0, 0.0)


def test_a_coasting_track_is_dropped_after_the_coast_limit() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    assert len(_step(state, PP.max_coast_ticks).tracks) == 1
    assert len(_step(state, PP.max_coast_ticks + 1).tracks) == 0


def test_the_uncertainty_ring_grows_with_the_time_since_seen() -> None:
    state = _step(TrackState(), 0, _det(3.0, 0.0, 0))
    near = tracking.track_points(state, 0, PP)
    far = tracking.track_points(state, 40, PP)
    assert _radius(far) == pytest.approx(_radius(near) + PP.human_speed_bound * 40 * DT)


def test_track_points_are_a_ring_around_the_track() -> None:
    state = _step(TrackState(), 0, _det(3.0, 1.0, 0, body=0.4))
    points = tracking.track_points(state, 0, PP)
    assert points.shape == (PP.ring_points, 2)
    assert np.allclose(np.hypot(points[:, 0] - 3.0, points[:, 1] - 1.0), 0.4)


def test_no_tracks_gives_an_empty_point_array() -> None:
    assert tracking.track_points(TrackState(), 0, PP).shape == (0, 2)


def test_an_older_detection_does_not_move_a_fresher_track() -> None:
    state = _step(TrackState(), 8, _det(3.0, 0.0, 8))
    state = _step(state, 9, _det(3.2, 0.0, 5))
    assert state.tracks[0].x == 3.0
    assert len(state.tracks) == 1


def test_a_delayed_detection_starts_a_track_seen_in_the_past() -> None:
    state = _step(TrackState(), 10, _det(3.0, 0.0, 6, sigma=0.1))
    assert state.tracks[0].seen_tick == 6


def test_tracking_is_deterministic() -> None:
    def run() -> TrackState:
        state = TrackState()
        for step in range(8):
            state = _step(
                state, 4 * step, _det(3.0 + 0.1 * step, 0.5, 4 * step), _det(6.0, -2.0, 4 * step)
            )
        return state

    a, b = run(), run()
    assert [(t.track_id, t.x, t.y, t.vx, t.vy) for t in a.tracks] == [
        (t.track_id, t.x, t.y, t.vx, t.vy) for t in b.tracks
    ]
