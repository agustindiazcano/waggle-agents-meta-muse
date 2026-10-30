"""Admission before entry for the S03 simulator integration."""

import numpy as np

from waggle.experiments.corridor_admission import build_s03_admission


def test_opposing_robot_waits_outside_before_whole_route_grant() -> None:
    sim, admission, _ = build_s03_admission(7)
    initial = np.asarray(sim.state.arrays["robot_pose"]).copy()
    sim.run(40)
    poses = np.asarray(sim.state.arrays["robot_pose"])
    assert poses[0, 1] > initial[0, 1]
    np.testing.assert_array_equal(poses[1], initial[1])
    assert admission.occupancy(sim.state)[0].occupants == ()


def test_s03_completes_without_shared_corridor_or_robot_collision() -> None:
    sim, admission, detector = build_s03_admission(7)
    for _ in range(3200):
        sim.step()
        assert len(admission.occupancy(sim.state)[0].occupants or ()) <= 1
        if np.all(np.asarray(sim.state.arrays["script_wp"]) == [2, 3]):
            break
    assert np.all(np.asarray(sim.state.arrays["script_wp"]) == [2, 3])
    assert detector.counts(sim.state)["robot_collisions"] == 0


def test_unknown_pose_denies_both_robots() -> None:
    sim, admission, _ = build_s03_admission(7)
    sim.state.arrays["robot_pose"][1, 0] = np.nan
    assert admission.occupancy(sim.state)[0].occupants is None
    admission.step(sim.state, {})
    assert not np.any(sim.state.arrays["robot_pending"])


def test_expired_occupied_grant_never_admits_opponent() -> None:
    sim, admission, _ = build_s03_admission(7, lease_ticks=200)
    sim.run(240)
    assert admission.occupancy(sim.state)[0].occupants == ("robot-0",)
    np.testing.assert_array_equal(sim.state.arrays["robot_pose"][1, :2], [9.0, 22.0])
    assert sim.state.arrays["admission_fault"][0] == 1


def test_release_admits_waiter_only_after_route_done_and_clear() -> None:
    sim, admission, _ = build_s03_admission(7)
    admission.step(sim.state, {})
    assert sim.state.arrays["admission_owner"][0] == 0
    sim.state.tick = 1
    sim.state.arrays["robot_pose"][0] = [3.0, 10.0, 0.0]
    sim.state.arrays["script_wp"][0] = 2
    admission.step(sim.state, {})
    assert sim.state.arrays["admission_owner"][0] == 0
    sim.state.tick = 2
    sim.state.arrays["robot_pose"][0] = [0.9, 23.0, 0.0]
    admission.step(sim.state, {})
    assert sim.state.arrays["admission_owner"][0] == 1
    assert sim.state.arrays["admission_token"][0] == 2


def test_admission_snapshot_replay_keeps_reservation_and_fault() -> None:
    from waggle.sim.engine import Engine

    sim, admission, _ = build_s03_admission(7, lease_ticks=2)
    sim.systems = [admission.step]
    sim.step()
    sim.state.arrays["robot_pose"][0] = [3.0, 10.0, 0.0]
    snap = sim.snapshot()
    fork = Engine.from_snapshot(snap, [admission.step])
    sim.run(3)
    fork.run(3)
    assert sim.state_hash() == fork.state_hash()
    assert sim.state.arrays["admission_fault"][0] == 1


def test_whole_route_denial_cancels_all_queued_commands() -> None:
    from waggle.coordination.corridors import CorridorRequest, Direction
    from waggle.experiments.corridor_admission import CorridorAdmission
    from waggle.sim.params import RobotKind
    from waggle.sim.robots import RobotFleet
    from waggle.sim.scenarios import load_map

    sim, _, _ = build_s03_admission(7)
    box = load_map("A")
    from dataclasses import replace

    second = replace(box.zone("station_1"), capacity=1)
    fleet = RobotFleet([RobotKind.CARRIER, RobotKind.CARRIER])
    admission = CorridorAdmission(
        fleet,
        (box.zone("lane_1"), second),
        (
            CorridorRequest("robot-0", ("lane_1", "station_1"), Direction.FORWARD),
            CorridorRequest("robot-1", ("lane_1",), Direction.REVERSE),
        ),
        (2, 3),
        100,
    )
    sim.state.arrays.update(admission.initial_arrays())
    sim.state.arrays["robot_pose"][1] = [7.5, 22.0, 0.0]
    sim.state.arrays["robot_pending"][:] = 1.0
    sim.state.arrays["robot_active"][:] = 1.0
    admission.step(sim.state, {})
    assert sim.state.arrays["admission_owner"][0] == 1
    assert sim.state.arrays["admission_owner"][1] == -1
    assert not np.any(sim.state.arrays["robot_pending"][0])
    assert not np.any(sim.state.arrays["robot_active"][0])


def test_touching_footprint_counts_as_occupied() -> None:
    sim, admission, _ = build_s03_admission(7)
    sim.state.arrays["robot_pose"][0] = [3.0, 4.6, 0.0]
    assert admission.occupancy(sim.state)[0].occupants == ("robot-0",)


def test_original_s03_still_has_original_geometry() -> None:
    from waggle.sim.scenarios import generate

    original = generate("S03", 7)
    assert original.robots[0].pose[:2] == (3.0, 6.0)
    assert original.robots[1].pose[:2] == (3.0, 18.0)


def test_invalid_zone_configuration_is_rejected() -> None:
    import pytest

    from waggle.coordination.corridors import CorridorRequest, Direction
    from waggle.experiments.corridor_admission import CorridorAdmission
    from waggle.sim.params import RobotKind
    from waggle.sim.robots import RobotFleet
    from waggle.sim.scenarios import load_map

    with pytest.raises(ValueError, match="capacity-one"):
        CorridorAdmission(
            RobotFleet([RobotKind.CARRIER]),
            (load_map("A").zone("station_1"),),
            (CorridorRequest("robot-0", ("station_1",), Direction.FORWARD),),
            (1,),
            100,
        )
