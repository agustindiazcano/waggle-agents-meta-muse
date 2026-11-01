"""Motion tools queue an order for the authenticated robot. Nothing moves in the server."""

import pytest

from waggle.db.motion import EnqueueResult, MotionRefused, NewOrder
from waggle.mcp_server.forwarder import FencedForwarder, ToolDenied, ToolUnavailable
from waggle.mcp_server.identity import Identity

ROBOT = Identity("carrier", "carrier-0")


class FakeMotion:
    def __init__(self, result: EnqueueResult | None = None, error: Exception | None = None) -> None:
        self.result = result or EnqueueResult(True, "queued", 7)
        self.error = error
        self.calls: list[tuple[str, NewOrder, int]] = []

    def enqueue(self, robot_id: str, order: NewOrder, now_tick: int) -> EnqueueResult:
        if self.error:
            raise self.error
        self.calls.append((robot_id, order, now_tick))
        return self.result


class FakeTicks:
    def now_tick(self) -> int:
        return 42


def _forwarder(motion: FakeMotion | None) -> FencedForwarder:
    return FencedForwarder(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        FakeTicks(),
        None,  # type: ignore[arg-type]
        motion=motion,
    )


def test_move_waypoint_queues_for_the_authenticated_robot_at_the_trusted_tick() -> None:
    motion = FakeMotion()
    args = {"task_id": "t-1", "x": 3.0, "y": 4.0, "speed": 1.0}
    out = _forwarder(motion).forward(ROBOT, "move_waypoint", args, 5)
    assert out == {"queued": True, "reason": "queued", "order_id": 7}
    robot, order, tick = motion.calls[0]
    assert (robot, tick) == ("carrier-0", 42)
    assert (order.tool, order.task_id, order.x, order.y, order.speed) == (
        "move_waypoint",
        "t-1",
        3.0,
        4.0,
        1.0,
    )


def test_pick_and_deliver_pass_their_fields() -> None:
    motion = FakeMotion()
    forwarder = _forwarder(motion)
    forwarder.forward(ROBOT, "pick_package", {"task_id": "t-1", "package_id": "pk-1"}, 5)
    forwarder.forward(
        ROBOT, "deliver_package", {"task_id": "t-1", "package_id": "pk-1", "zone_id": "dock"}, 5
    )
    assert [c[1].tool for c in motion.calls] == ["pick_package", "deliver_package"]
    assert motion.calls[1][1].zone_id == "dock"


def test_a_busy_robot_gets_a_result_not_an_error() -> None:
    motion = FakeMotion(EnqueueResult(False, "busy", None))
    out = _forwarder(motion).forward(
        ROBOT, "pick_package", {"task_id": "t-1", "package_id": "pk-1"}, 5
    )
    assert out == {"queued": False, "reason": "busy", "order_id": None}


def test_a_refused_order_is_denied_without_the_reason() -> None:
    motion = FakeMotion(error=MotionRefused("zone_not_held"))
    with pytest.raises(ToolDenied) as caught:
        _forwarder(motion).forward(
            ROBOT, "deliver_package", {"task_id": "t-1", "package_id": "p", "zone_id": "z"}, 5
        )
    assert "zone_not_held" not in str(caught.value)


@pytest.mark.parametrize("tool", ["move_waypoint", "pick_package", "deliver_package"])
def test_without_a_motion_port_the_tools_stay_unavailable(tool: str) -> None:
    with pytest.raises(ToolUnavailable):
        _forwarder(None).forward(ROBOT, tool, {}, 5)
