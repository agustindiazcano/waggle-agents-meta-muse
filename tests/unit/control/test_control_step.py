"""waggle.control.step: scan to tracks to limited command, fail closed on bad input."""

import logging
import math

import pytest
from control_support import make_odometry, make_scan

from waggle.control import perception, step
from waggle.control.params import DEFAULT_CONTROL_PARAMS, DEFAULT_PERCEPTION_PARAMS
from waggle.control.step import ControlInputs, ControlState
from waggle.control.types import ControlOutput, ControlRequest, Reason
from waggle.sim.observations import BeaconReport, LidarScan, RobotOdometry
from waggle.sim.params import ROBOT_PARAMS, RobotKind

CARRIER = ROBOT_PARAMS[RobotKind.CARRIER]
HUMAN = [(3.3, 0.0, 0.3)]


def _inputs(
    tick: int = 0,
    scan: LidarScan | None = None,
    odom: RobotOdometry | None = None,
    speed: float = 2.0,
    beacons: tuple[BeaconReport, ...] = (),
) -> ControlInputs:
    return ControlInputs(
        request=ControlRequest(speed, 0.0),
        params=CARRIER,
        tick=tick,
        odometry=odom if odom is not None else make_odometry(tick=tick),
        scan=scan if scan is not None else make_scan(tick=tick),
        beacons=beacons,
    )


def _run(state: ControlState, inputs: ControlInputs) -> tuple[ControlState, ControlOutput]:
    return step.control_step(state, inputs, DEFAULT_CONTROL_PARAMS, DEFAULT_PERCEPTION_PARAMS)


def test_an_empty_scan_passes_the_request() -> None:
    _, out = _run(ControlState(), _inputs())
    assert (out.speed, out.reason) == (2.0, Reason.REQUEST)


def test_a_human_ahead_lowers_the_speed_with_reason_envelope() -> None:
    state, out = _run(ControlState(), _inputs(scan=make_scan(discs=HUMAN)))
    assert 0.0 < out.speed < 1.5
    assert out.reason is Reason.ENVELOPE
    assert len(state.tracks.tracks) == 1


def test_a_structure_ahead_only_needs_room_to_stop() -> None:
    wall = make_scan(boxes=[(1.8, -3.0, 2.2, 3.0)])
    _, out = _run(ControlState(), _inputs(scan=wall))
    human_out = _run(ControlState(), _inputs(scan=make_scan(discs=[(1.8 + 0.3, 0.0, 0.3)])))[1]
    assert 0.0 < out.speed < 2.0
    assert out.reason is Reason.ENVELOPE
    assert human_out.speed < out.speed


def test_a_missing_scan_stops_the_robot_with_scan_invalid() -> None:
    inputs = ControlInputs(ControlRequest(2.0, 0.0), CARRIER, 0, make_odometry(), None)
    state, out = _run(ControlState(), inputs)
    assert (out.speed, out.reason) == (0.0, Reason.SCAN_INVALID)
    assert state == ControlState()


def test_a_stale_scan_stops_the_robot() -> None:
    _, out = _run(ControlState(), _inputs(tick=20, scan=make_scan(tick=0), odom=make_odometry(20)))
    assert (out.speed, out.reason) == (0.0, Reason.SCAN_INVALID)


def test_missing_odometry_stops_the_robot_with_input_missing() -> None:
    inputs = ControlInputs(ControlRequest(2.0, 0.0), CARRIER, 0, None, make_scan())
    _, out = _run(ControlState(), inputs)
    assert (out.speed, out.reason) == (0.0, Reason.INPUT_MISSING)


def test_a_stopped_request_with_bad_input_is_not_blamed_on_the_input() -> None:
    inputs = ControlInputs(ControlRequest(0.0, 0.0), CARRIER, 0, make_odometry(), None)
    _, out = _run(ControlState(), inputs)
    assert (out.speed, out.reason) == (0.0, Reason.REQUEST)


def test_the_result_does_not_depend_on_where_the_robot_stands_or_faces() -> None:
    _, here = _run(ControlState(), _inputs(scan=make_scan(discs=HUMAN)))
    pose = make_odometry(x=10.0, y=5.0, theta=math.pi / 2)
    state, there = _run(ControlState(), _inputs(scan=make_scan(discs=HUMAN), odom=pose))
    assert there.speed == pytest.approx(here.speed)
    track = state.tracks.tracks[0]
    assert (track.x, track.y) == pytest.approx((10.0, 5.0 + 3.0), abs=0.15)


def test_the_same_scan_is_reused_and_the_gap_follows_the_robot() -> None:
    scan = make_scan(tick=0, discs=HUMAN)
    state, first = _run(ControlState(), _inputs(tick=0, scan=scan))
    state, later = _run(state, _inputs(tick=2, scan=scan, odom=make_odometry(tick=2, x=1.0)))
    assert later.speed < first.speed
    assert len(state.tracks.tracks) == 1


def test_a_human_who_leaves_the_scan_is_remembered_then_released() -> None:
    state, seen = _run(ControlState(), _inputs(scan=make_scan(discs=HUMAN)))
    state, coasting = _run(state, _inputs(tick=4))
    assert coasting.speed < 2.0
    assert coasting.reason is Reason.ENVELOPE
    limit = DEFAULT_PERCEPTION_PARAMS.max_coast_ticks
    state, almost = _run(state, _inputs(tick=limit))
    state, released = _run(state, _inputs(tick=limit + 4))
    assert almost.speed < 2.0
    assert (released.speed, released.reason) == (2.0, Reason.REQUEST)
    assert seen.speed < 2.0


def test_a_beacon_reveals_a_human_the_lidar_cannot_see() -> None:
    beacon = BeaconReport(0, 0, 0, 4.0, 0.0, 0)
    _, without = _run(ControlState(), _inputs())
    state, with_beacon = _run(ControlState(), _inputs(beacons=(beacon,)))
    assert without.speed == 2.0
    assert with_beacon.speed < 2.0
    assert len(state.tracks.tracks) == 1


def test_a_delayed_beacon_is_treated_as_older_and_less_certain() -> None:
    fresh = BeaconReport(8, 0, 0, 4.0, 0.0, 0)
    old = BeaconReport(8, 0, 0, 4.0, 0.0, 4)
    _, a = _run(
        ControlState(),
        _inputs(tick=8, scan=make_scan(tick=8), odom=make_odometry(8), beacons=(fresh,)),
    )
    _, b = _run(
        ControlState(),
        _inputs(tick=8, scan=make_scan(tick=8), odom=make_odometry(8), beacons=(old,)),
    )
    assert b.speed < a.speed


def test_a_beacon_on_a_visible_human_does_not_add_a_second_track() -> None:
    beacon = BeaconReport(0, 0, 0, 3.0, 0.02, 0)
    state, _ = _run(ControlState(), _inputs(scan=make_scan(discs=HUMAN), beacons=(beacon,)))
    assert len(state.tracks.tracks) == 1


def test_a_beacon_beside_a_wall_gives_a_human_track_and_keeps_the_wall() -> None:
    wall = make_scan(boxes=[(5.0, -3.0, 5.4, 3.0)])
    beacon = BeaconReport(0, 0, 0, 4.8, 0.5, 0)
    state, _ = _run(ControlState(), _inputs(scan=wall, beacons=(beacon,)))
    assert len(state.tracks.tracks) == 1
    assert len(state.structure_world) > 0


def test_the_step_is_deterministic() -> None:
    def run() -> list[ControlOutput]:
        state, outputs = ControlState(), []
        for tick in range(0, 40, 4):
            scan = make_scan(tick=tick, discs=[(3.3 + 0.05 * tick, 0.0, 0.3)])
            state, out = _run(state, _inputs(tick=tick, scan=scan))
            outputs.append(out)
        return outputs

    assert run() == run()


def test_an_exception_in_perception_is_logged_and_stops_the_robot(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(perception, "clusters_from_scan", boom)
    with caplog.at_level(logging.ERROR):
        state, out = _run(ControlState(), _inputs(scan=make_scan(discs=HUMAN)))
    assert (out.speed, out.reason) == (0.0, Reason.INPUT_MISSING)
    assert state == ControlState()
    assert "boom" in caplog.text


SIDE_WALL = [(-5.0, 1.2, 4.0, 3.5)]
HIDDEN_HUMAN = [(4.5, 2.2, 0.3)]


def _occluded_inputs(use_occlusion: bool) -> ControlInputs:
    scan = make_scan(boxes=SIDE_WALL, discs=HIDDEN_HUMAN)
    base = _inputs(scan=scan)
    return ControlInputs(
        request=base.request,
        params=base.params,
        tick=base.tick,
        odometry=base.odometry,
        scan=base.scan,
        use_occlusion=use_occlusion,
    )


def test_without_the_occlusion_cap_a_hidden_human_is_not_seen() -> None:
    _, out = _run(ControlState(), _occluded_inputs(False))
    assert (out.speed, out.reason) == (2.0, Reason.REQUEST)


def test_the_occlusion_cap_slows_the_robot_for_a_human_behind_a_wall_corner() -> None:
    _, out = _run(ControlState(), _occluded_inputs(True))
    assert 0.0 < out.speed < 2.0
    assert out.reason is Reason.OCCLUSION
    assert Reason.OCCLUSION in out.limits_hit


def test_the_occlusion_cap_is_inactive_on_an_open_floor() -> None:
    inputs = ControlInputs(
        request=ControlRequest(2.0, 0.0),
        params=CARRIER,
        tick=0,
        odometry=make_odometry(),
        scan=make_scan(),
        use_occlusion=True,
    )
    _, out = _run(ControlState(), inputs)
    assert (out.speed, out.reason) == (2.0, Reason.REQUEST)
