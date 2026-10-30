"""waggle.sim.params: one dt constant, class parameters, and the delay-in-ticks rule."""

import math

import pytest

from waggle.sim import params


def test_dt_is_40_hz_and_lidar_runs_every_4_ticks() -> None:
    assert params.DT == 0.025
    assert params.LIDAR_PERIOD_TICKS == 4
    assert math.isclose(params.LIDAR_PERIOD_TICKS * params.DT, 0.1)


@pytest.mark.parametrize(
    ("kind", "ticks"),
    [
        (params.RobotKind.CARRIER, 4),
        (params.RobotKind.PARTS_RUNNER, 4),
        (params.RobotKind.TECH_REPAIR, 4),
        (params.RobotKind.FORKLIFT, 6),
    ],
)
def test_default_class_delays_are_whole_ticks(kind: params.RobotKind, ticks: int) -> None:
    assert params.ROBOT_PARAMS[kind].delay_ticks == ticks


def test_all_four_classes_exist_with_the_architecture_values() -> None:
    table = params.ROBOT_PARAMS
    assert set(table) == set(params.RobotKind)
    assert (table[params.RobotKind.CARRIER].max_speed, table[params.RobotKind.CARRIER].decel) == (
        2.0,
        2.0,
    )
    assert table[params.RobotKind.FORKLIFT].max_speed == 1.5
    assert table[params.RobotKind.FORKLIFT].decel == 0.8


def test_forklift_turning_radius_comes_from_wheelbase_and_steering() -> None:
    forklift = params.ROBOT_PARAMS[params.RobotKind.FORKLIFT]
    assert forklift.kinematics == "bicycle"
    assert forklift.min_turn_radius == pytest.approx(2.5, abs=0.01)


def test_other_classes_are_differential_drive_with_an_angular_limit() -> None:
    for kind in (
        params.RobotKind.CARRIER,
        params.RobotKind.PARTS_RUNNER,
        params.RobotKind.TECH_REPAIR,
    ):
        p = params.ROBOT_PARAMS[kind]
        assert p.kinematics == "differential"
        assert p.max_angular_speed is not None and p.max_angular_speed > 0
        assert p.min_turn_radius == 0.0


def good() -> dict[str, object]:
    return {
        "kind": "carrier",
        "max_speed": 2.0,
        "decel": 2.0,
        "actuation_delay": 0.10,
        "length": 1.2,
        "width": 0.8,
        "kinematics": "differential",
        "max_angular_speed": 1.5,
    }


def test_loader_accepts_a_valid_config() -> None:
    p = params.parse_robot_params(good())
    assert p.delay_ticks == 4


@pytest.mark.parametrize("delay", [0.12, 0.03, 0.0125, 0.1000001, -0.025])
def test_loader_rejects_a_delay_that_is_not_a_multiple_of_dt(delay: float) -> None:
    data = good()
    data["actuation_delay"] = delay
    with pytest.raises(params.ParamsError, match="multiple of dt"):
        params.parse_robot_params(data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_speed", 0),
        ("max_speed", -1.0),
        ("decel", 0),
        ("length", 0),
        ("width", -0.1),
        ("kinematics", "holonomic"),
        ("kind", "tractor"),
        ("max_speed", "fast"),
        ("max_speed", math.nan),
        ("max_speed", True),
    ],
)
def test_loader_rejects_bad_values(key: str, value: object) -> None:
    data = good()
    data[key] = value
    with pytest.raises(params.ParamsError):
        params.parse_robot_params(data)


def test_loader_rejects_unknown_and_missing_fields() -> None:
    data = good()
    data["turbo"] = 1
    with pytest.raises(params.ParamsError, match="unknown"):
        params.parse_robot_params(data)
    data = good()
    del data["length"]
    with pytest.raises(params.ParamsError, match="missing"):
        params.parse_robot_params(data)


def test_bicycle_requires_wheelbase_and_steering_and_differential_requires_angular_speed() -> None:
    data = good()
    data["kinematics"] = "bicycle"
    with pytest.raises(params.ParamsError, match="wheelbase"):
        params.parse_robot_params(data)
    data = good()
    del data["max_angular_speed"]
    with pytest.raises(params.ParamsError, match="max_angular_speed"):
        params.parse_robot_params(data)
