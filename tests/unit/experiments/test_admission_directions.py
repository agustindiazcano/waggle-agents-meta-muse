"""Admission retries retain the direction of each resource in a route bundle."""

from dataclasses import replace

import numpy as np

from waggle.coordination.corridors import CorridorRequest, Direction
from waggle.experiments.corridor_admission import CorridorAdmission, build_s03_admission
from waggle.sim.params import RobotKind
from waggle.sim.robots import RobotFleet
from waggle.sim.scenarios import load_map


def test_mixed_direction_bundle_stays_admitted_on_the_next_tick() -> None:
    sim, _, _ = build_s03_admission(7)
    box = load_map("A")
    admission = CorridorAdmission(
        RobotFleet([RobotKind.CARRIER, RobotKind.CARRIER]),
        (box.zone("lane_1"), replace(box.zone("station_1"), capacity=1)),
        (
            CorridorRequest(
                "robot-0",
                ("lane_1", "station_1"),
                Direction.FORWARD,
                (("lane_1", Direction.FORWARD), ("station_1", Direction.REVERSE)),
            ),
            CorridorRequest("robot-1", ("lane_1",), Direction.REVERSE),
        ),
        (2, 3),
        100,
    )
    sim.state.arrays.update(admission.initial_arrays())
    admission.step(sim.state, {})
    np.testing.assert_array_equal(sim.state.arrays["admission_owner"], [0, 0])
    tokens = sim.state.arrays["admission_token"].copy()
    sim.state.tick = 1
    sim.state.arrays["robot_pending"][:] = 1
    sim.state.arrays["robot_active"][:] = 1

    admission.step(sim.state, {})

    assert np.all(sim.state.arrays["robot_pending"][0] == 1)
    assert np.all(sim.state.arrays["robot_active"][0] == 1)
    assert not np.any(sim.state.arrays["robot_pending"][1])
    np.testing.assert_array_equal(sim.state.arrays["admission_token"], tokens)
