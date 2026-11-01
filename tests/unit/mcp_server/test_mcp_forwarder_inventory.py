"""get_inventory and reserve_part over an inventory port. Unknown parts and key reuse deny."""

import pytest

from waggle.db.corridors import IdempotencyConflict
from waggle.db.inventory import PartStock, ReservationResult, UnknownPart
from waggle.mcp_server.forwarder import FencedForwarder, ToolDenied, ToolUnavailable
from waggle.mcp_server.identity import Identity

MAINT = Identity("maintenance", "maint-0")


class FakeInventory:
    def __init__(self, *, conflict: bool = False, grant: bool = True) -> None:
        self.conflict = conflict
        self.grant = grant
        self.reserved: list[tuple[str, str, int, str]] = []

    def get(self, part_number: str) -> PartStock | None:
        return PartStock(part_number, 10, 4) if part_number == "P-100" else None

    def reserve(self, key: str, part_number: str, quantity: int, holder: str) -> ReservationResult:
        if part_number != "P-100":
            raise UnknownPart(part_number)
        if self.conflict:
            raise IdempotencyConflict("key reused")
        self.reserved.append((key, part_number, quantity, holder))
        if self.grant:
            return ReservationResult(True, "reserved", part_number, quantity)
        return ReservationResult(False, "insufficient_stock", part_number, quantity)


def _forwarder(inventory: FakeInventory | None) -> FencedForwarder:
    return FencedForwarder(None, None, None, None, inventory=inventory)  # type: ignore[arg-type]


def test_get_inventory_reports_available_not_internal_counts() -> None:
    out = _forwarder(FakeInventory()).forward(MAINT, "get_inventory", {"part_number": "P-100"}, 5)
    assert out == {"part_number": "P-100", "available": 6}


def test_get_inventory_unknown_part_is_denied() -> None:
    with pytest.raises(ToolDenied):
        _forwarder(FakeInventory()).forward(MAINT, "get_inventory", {"part_number": "X-1"}, 5)


def test_reserve_part_uses_the_authenticated_robot_as_holder() -> None:
    inventory = FakeInventory()
    args = {"part_number": "P-100", "quantity": 2, "idempotency_key": "evt-1"}
    out = _forwarder(inventory).forward(MAINT, "reserve_part", args, 5)
    assert out == {"reserved": True, "reason": "reserved"}
    assert inventory.reserved == [("evt-1", "P-100", 2, "maint-0")]


def test_reserve_part_shortage_is_a_result_not_an_error() -> None:
    args = {"part_number": "P-100", "quantity": 9, "idempotency_key": "evt-2"}
    out = _forwarder(FakeInventory(grant=False)).forward(MAINT, "reserve_part", args, 5)
    assert out == {"reserved": False, "reason": "insufficient_stock"}


def test_reserve_part_unknown_part_is_denied() -> None:
    args = {"part_number": "X-1", "quantity": 1, "idempotency_key": "evt-3"}
    with pytest.raises(ToolDenied):
        _forwarder(FakeInventory()).forward(MAINT, "reserve_part", args, 5)


def test_reserve_part_key_reuse_with_other_values_is_denied() -> None:
    args = {"part_number": "P-100", "quantity": 1, "idempotency_key": "evt-1"}
    with pytest.raises(ToolDenied):
        _forwarder(FakeInventory(conflict=True)).forward(MAINT, "reserve_part", args, 5)


@pytest.mark.parametrize("tool", ["get_inventory", "reserve_part"])
def test_without_an_inventory_port_the_tools_stay_unavailable(tool: str) -> None:
    with pytest.raises(ToolUnavailable):
        _forwarder(None).forward(MAINT, tool, {}, 5)
