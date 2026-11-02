"""pick_package and deliver_package queue only ids the registry declares (ADR-075)."""

import pytest

from waggle.db.motion import EnqueueResult, NewOrder
from waggle.mcp_server.forwarder import FencedForwarder, ToolDenied
from waggle.mcp_server.identity import Identity

ROBOT = Identity("carrier", "carrier-0")
PICK = ("pick_package", {"task_id": "t-1", "package_id": "pk-9"})
DELIVER = ("deliver_package", {"task_id": "t-1", "package_id": "pk-9", "zone_id": "dock"})
MOVE = ("move_waypoint", {"task_id": "t-1", "x": 1.0, "y": 2.0, "speed": 1.0})


class FakeMotion:
    def __init__(self) -> None:
        self.calls: list[NewOrder] = []

    def enqueue(self, robot_id: str, order: NewOrder, now_tick: int) -> EnqueueResult:
        self.calls.append(order)
        return EnqueueResult(True, "queued", 1)


class FakeTicks:
    def now_tick(self) -> int:
        return 3


class FakePackages:
    def __init__(self, known: set[str], error: Exception | None = None) -> None:
        self.known = known
        self.error = error
        self.asked: list[str] = []

    def has(self, package_id: str) -> bool:
        self.asked.append(package_id)
        if self.error:
            raise self.error
        return package_id in self.known


def _forwarder(motion: FakeMotion, packages: FakePackages) -> FencedForwarder:
    return FencedForwarder(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        FakeTicks(),
        None,  # type: ignore[arg-type]
        motion=motion,
        packages=packages,
    )


@pytest.mark.parametrize("call", [PICK, DELIVER])
def test_a_declared_package_is_queued(call: tuple[str, dict[str, object]]) -> None:
    motion = FakeMotion()
    out = _forwarder(motion, FakePackages({"pk-9"})).forward(ROBOT, call[0], call[1], 5)
    assert out["queued"] is True and len(motion.calls) == 1


@pytest.mark.parametrize("call", [PICK, DELIVER])
def test_an_unknown_package_is_denied_and_nothing_is_queued(
    call: tuple[str, dict[str, object]],
) -> None:
    motion = FakeMotion()
    with pytest.raises(ToolDenied, match="order not available"):
        _forwarder(motion, FakePackages({"pk-1"})).forward(ROBOT, call[0], call[1], 5)
    assert motion.calls == []


@pytest.mark.parametrize("call", [PICK, DELIVER])
def test_a_registry_that_cannot_be_read_does_not_queue(
    call: tuple[str, dict[str, object]],
) -> None:
    motion = FakeMotion()
    with pytest.raises(RuntimeError):
        _forwarder(motion, FakePackages(set(), RuntimeError("down"))).forward(
            ROBOT, call[0], call[1], 5
        )
    assert motion.calls == []


def test_the_denial_text_does_not_name_the_package_or_the_check() -> None:
    with pytest.raises(ToolDenied) as error:
        _forwarder(FakeMotion(), FakePackages(set())).forward(ROBOT, PICK[0], PICK[1], 5)
    assert "pk-9" not in str(error.value) and "registry" not in str(error.value)


def test_a_move_does_not_consult_the_registry() -> None:
    packages = FakePackages(set())
    _forwarder(FakeMotion(), packages).forward(ROBOT, MOVE[0], MOVE[1], 5)
    assert packages.asked == []
