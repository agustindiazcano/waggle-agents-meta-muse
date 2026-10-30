"""waggle.control.step: scan to tracks to limited command, fail closed on bad input."""

import logging
import math
from dataclasses import replace

import numpy as np
import pytest
from control_support import make_odometry, make_scan

from waggle.control import perception, step
from waggle.control.params import DEFAULT_CONTROL_PARAMS, DEFAULT_PERCEPTION_PARAMS
from waggle.control.reflex import Geofence, TelemetryReading
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


def _crossing_run(use_cpa: bool) -> list[ControlOutput]:
    """A person walks across the lane at 1.2 m/s, one scan every four ticks."""
    state, outputs = ControlState(), []
    scan = make_scan(tick=0)
    for tick in range(0, 61):
        if tick % 4 == 0:
            scan = make_scan(tick=tick, discs=[(1.8, 3.0 - 1.2 * tick * 0.025, 0.3)])
        inputs = ControlInputs(
            request=ControlRequest(2.0, 0.0),
            params=CARRIER,
            tick=tick,
            odometry=make_odometry(tick=tick),
            scan=scan,
            use_cpa=use_cpa,
        )
        state, out = _run(state, inputs)
        outputs.append(out)
    return outputs


def test_cpa_restricts_a_crossing_person_earlier_than_the_envelope() -> None:
    without, with_cpa = _crossing_run(False), _crossing_run(True)
    assert all(a.speed <= b.speed + 1e-12 for a, b in zip(with_cpa, without, strict=True))
    assert any(Reason.CPA in out.limits_hit for out in with_cpa)
    assert all(Reason.CPA not in out.limits_hit for out in without)
    first_without = next((i for i, out in enumerate(without) if out.speed < 2.0), len(without))
    first_with = next(i for i, out in enumerate(with_cpa) if out.speed < 2.0)
    assert first_with < first_without


def _reflex_inputs(
    tick: int = 100,
    scan_tick: int | None = None,
    heartbeat: int | None = 100,
    estop: bool = False,
    geofences: tuple[Geofence, ...] = (),
    telemetry: tuple[TelemetryReading, ...] = (),
    use_reflex: bool = True,
) -> ControlInputs:
    return ControlInputs(
        request=ControlRequest(2.0, 0.0),
        params=CARRIER,
        tick=tick,
        odometry=make_odometry(tick=tick),
        scan=make_scan(tick=tick if scan_tick is None else scan_tick),
        use_reflex=use_reflex,
        heartbeat_tick=heartbeat,
        estop=estop,
        geofences=geofences,
        telemetry=telemetry,
    )


def test_reflex_is_off_by_default() -> None:
    _, out = _run(ControlState(), _reflex_inputs(heartbeat=None, estop=True, use_reflex=False))
    assert (out.speed, out.reason) == (2.0, Reason.REQUEST)


def test_a_missing_heartbeat_stops_the_robot_with_watchdog() -> None:
    _, out = _run(ControlState(), _reflex_inputs(heartbeat=None))
    assert (out.speed, out.reason) == (0.0, Reason.WATCHDOG)


def test_a_live_heartbeat_passes_the_request() -> None:
    _, out = _run(ControlState(), _reflex_inputs())
    assert (out.speed, out.reason) == (2.0, Reason.REQUEST)


def test_estop_wins_over_an_invalid_scan() -> None:
    inputs = _reflex_inputs(scan_tick=0, estop=True)
    _, out = _run(ControlState(), inputs)
    assert (out.speed, out.reason) == (0.0, Reason.ESTOP)
    assert Reason.SCAN_INVALID in out.limits_hit


def test_a_stale_heartbeat_still_stops_when_the_scan_is_invalid() -> None:
    _, out = _run(ControlState(), _reflex_inputs(scan_tick=0, heartbeat=None))
    assert out.speed == 0.0
    assert Reason.WATCHDOG in out.limits_hit


def test_a_geofence_ahead_slows_the_robot_with_reason_geofence() -> None:
    fence = Geofence("g", ((1.5, -1.0), (3.5, -1.0), (3.5, 1.0), (1.5, 1.0)))
    _, out = _run(ControlState(), _reflex_inputs(geofences=(fence,)))
    assert 0.0 < out.speed < 2.0
    assert out.reason is Reason.GEOFENCE


def test_a_hot_machine_ahead_sets_a_geofence_from_its_telemetry() -> None:
    hot = TelemetryReading("m1", 4.0, 0.0, value=99.0, warn=80.0, critical=95.0)
    cool = TelemetryReading("m1", 4.0, 0.0, value=40.0, warn=80.0, critical=95.0)
    _, slowed = _run(ControlState(), _reflex_inputs(telemetry=(hot,)))
    _, free = _run(ControlState(), _reflex_inputs(telemetry=(cool,)))
    assert slowed.speed < 2.0 and slowed.reason is Reason.GEOFENCE
    assert free.speed == 2.0


# A rack face seen at an angle is a small cluster. With the map it is structure, not a person.
RACK_FACE = np.array([[3.0, -1.0, 3.0, 1.0]])
RACK_PIECE = [(3.0, -0.3, 3.2, 0.3)]


def _with_map(scan: LidarScan, segments: np.ndarray) -> ControlInputs:
    return replace(_inputs(scan=scan), map_segments=segments, use_occlusion=True)


def test_a_small_cluster_on_the_map_is_structure_and_not_a_track() -> None:
    state, out = _run(ControlState(), _with_map(make_scan(boxes=RACK_PIECE), RACK_FACE))
    assert state.tracks.tracks == ()
    assert len(state.structure_world) > 0
    assert out.speed > 0.0


def test_the_same_cluster_without_the_map_is_still_a_human_track() -> None:
    state, _ = _run(ControlState(), _inputs(scan=make_scan(boxes=RACK_PIECE)))
    assert len(state.tracks.tracks) == 1


def test_a_human_standing_against_a_side_wall_is_still_a_track() -> None:
    side_wall = np.array([[0.0, -1.0, 10.0, -1.0]])
    scan = make_scan(discs=[(4.0, -0.7, 0.3)])
    state, _ = _run(ControlState(), _with_map(scan, side_wall))
    assert len(state.tracks.tracks) == 1


def test_a_human_far_from_the_mapped_wall_is_still_a_track() -> None:
    scan = make_scan(discs=[(2.0, 0.5, 0.3)])
    state, out = _run(ControlState(), _with_map(scan, RACK_FACE))
    assert len(state.tracks.tracks) == 1
    assert out.reason is Reason.ENVELOPE


def test_the_map_filter_is_off_without_the_occlusion_cap() -> None:
    inputs = replace(_with_map(make_scan(boxes=RACK_PIECE), RACK_FACE), use_occlusion=False)
    state, _ = _run(ControlState(), inputs)
    assert len(state.tracks.tracks) == 1
