"""A motion order is checked for shape before it reaches the database."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.motion import MotionOrderRepository, NewOrder


def test_move_needs_a_finite_target_and_speed_only() -> None:
    order = NewOrder("move_waypoint", "t-1", x=1.5, y=2.0, speed=1.0)
    assert (order.x, order.y, order.speed) == (1.5, 2.0, 1.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"x": 1.0, "y": 2.0},
        {"x": 1.0, "y": 2.0, "speed": 1.0, "package_id": "pk-1"},
        {"x": float("nan"), "y": 2.0, "speed": 1.0},
        {"x": 1.0, "y": float("inf"), "speed": 1.0},
        {"x": 1.0, "y": 2.0, "speed": 0.0},
        {"x": 1.0, "y": 2.0, "speed": -1.0},
        {"x": True, "y": 2.0, "speed": 1.0},
        {"x": "1", "y": 2.0, "speed": 1.0},
    ],
)
def test_malformed_move_is_refused(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        NewOrder("move_waypoint", "t-1", **kwargs)  # type: ignore[arg-type]


def test_pick_needs_a_package_only() -> None:
    assert NewOrder("pick_package", "t-1", package_id="pk-1").zone_id is None
    for kwargs in ({}, {"package_id": "pk-1", "zone_id": "z"}, {"package_id": "a b"}):
        with pytest.raises(ValueError):
            NewOrder("pick_package", "t-1", **kwargs)  # type: ignore[arg-type]


def test_deliver_needs_a_package_and_a_zone() -> None:
    assert NewOrder("deliver_package", "t-1", package_id="pk-1", zone_id="dock").zone_id == "dock"
    for kwargs in (
        {"package_id": "pk-1"},
        {"zone_id": "dock"},
        {"package_id": "pk-1", "zone_id": ""},
    ):
        with pytest.raises(ValueError):
            NewOrder("deliver_package", "t-1", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("tool", ["release_zone", "", "move", 5])
def test_unknown_tool_is_refused(tool: object) -> None:
    with pytest.raises(ValueError):
        NewOrder(tool, "t-1", package_id="pk-1")  # type: ignore[arg-type]


def test_signature_depends_on_every_field() -> None:
    base = NewOrder("move_waypoint", "t-1", x=1.0, y=2.0, speed=1.0)
    assert base.signature() == NewOrder("move_waypoint", "t-1", x=1.0, y=2.0, speed=1.0).signature()
    assert base.signature() != NewOrder("move_waypoint", "t-2", x=1.0, y=2.0, speed=1.0).signature()
    assert base.signature() != NewOrder("move_waypoint", "t-1", x=1.0, y=2.5, speed=1.0).signature()


def test_bad_robot_or_tick_or_outcome_never_connects() -> None:
    database = MagicMock(spec=Database)
    repo = MotionOrderRepository(database)
    order = NewOrder("pick_package", "t-1", package_id="pk-1")
    with pytest.raises(ValueError):
        repo.enqueue("bad robot", order, 0)
    with pytest.raises(ValueError):
        repo.enqueue("robot-0", order, -1)
    with pytest.raises(ValueError):
        repo.resolve(1, "maybe", 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repo.pending(0)
    database.transaction.assert_not_called()
