"""open_ticket, dispatch_tech and create_purchase_order over ports. Unknown references deny."""

import pytest

from waggle.db.corridors import IdempotencyConflict
from waggle.db.inventory import UnknownPart
from waggle.db.procurement import OrderResult
from waggle.db.tickets import TicketResult, UnknownMachine, UnknownTicket, UnknownZone
from waggle.mcp_server.forwarder import FencedForwarder, ToolDenied, ToolUnavailable
from waggle.mcp_server.identity import Identity

MAINT = Identity("maintenance", "maint-0")
TECH = Identity("tech_repair", "tech-0")


class FakeTickets:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.opened: list[tuple[str, str, str, str]] = []
        self.dispatched: list[tuple[str, str, str]] = []

    def open_ticket(self, key: str, machine_id: str, summary: str, opener: str) -> TicketResult:
        if self.error:
            raise self.error
        self.opened.append((key, machine_id, summary, opener))
        return TicketResult("tkt-abc", True)

    def dispatch(self, ticket_id: str, zone_id: str, dispatcher: str) -> TicketResult:
        if self.error:
            raise self.error
        self.dispatched.append((ticket_id, zone_id, dispatcher))
        return TicketResult(ticket_id, True)


class FakeProcurement:
    def __init__(self, error: Exception | None = None, reason: str = "ordered") -> None:
        self.error = error
        self.reason = reason
        self.calls: list[tuple[str, str, int, str]] = []

    def order(self, key: str, part_number: str, quantity: int, requester: str) -> OrderResult:
        if self.error:
            raise self.error
        self.calls.append((key, part_number, quantity, requester))
        if self.reason == "stock_available":
            return OrderResult(False, "stock_available", part_number, quantity)
        return OrderResult(True, "ordered", part_number, quantity)


def _forwarder(
    tickets: FakeTickets | None = None, procurement: FakeProcurement | None = None
) -> FencedForwarder:
    return FencedForwarder(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        tickets=tickets,
        procurement=procurement,
    )


OPEN = {"machine_id": "M-1", "idempotency_key": "evt-1", "summary": "bearing noise"}


def test_open_ticket_uses_the_authenticated_robot_as_opener() -> None:
    tickets = FakeTickets()
    out = _forwarder(tickets).forward(TECH, "open_ticket", OPEN, 5)
    assert out == {"ticket_id": "tkt-abc", "created": True}
    assert tickets.opened == [("evt-1", "M-1", "bearing noise", "tech-0")]


@pytest.mark.parametrize("error", [UnknownMachine("M-1"), IdempotencyConflict("reuse")])
def test_open_ticket_denies_unknown_machine_and_key_reuse(error: Exception) -> None:
    with pytest.raises(ToolDenied):
        _forwarder(FakeTickets(error)).forward(MAINT, "open_ticket", OPEN, 5)


def test_dispatch_tech_records_the_dispatcher() -> None:
    tickets = FakeTickets()
    out = _forwarder(tickets).forward(
        MAINT, "dispatch_tech", {"ticket_id": "tkt-abc", "zone_id": "zone-1"}, 5
    )
    assert out == {"dispatched": True, "ticket_id": "tkt-abc", "zone_id": "zone-1"}
    assert tickets.dispatched == [("tkt-abc", "zone-1", "maint-0")]


@pytest.mark.parametrize(
    "error", [UnknownTicket("t"), UnknownZone("z"), IdempotencyConflict("other zone")]
)
def test_dispatch_tech_denies_unknown_references_and_a_second_zone(error: Exception) -> None:
    with pytest.raises(ToolDenied):
        _forwarder(FakeTickets(error)).forward(
            MAINT, "dispatch_tech", {"ticket_id": "tkt-abc", "zone_id": "zone-1"}, 5
        )


ORDER = {"part_number": "P-100", "quantity": 4, "idempotency_key": "evt-9"}


def test_purchase_order_is_placed_for_the_requester() -> None:
    procurement = FakeProcurement()
    out = _forwarder(procurement=procurement).forward(MAINT, "create_purchase_order", ORDER, 5)
    assert out == {"ordered": True, "reason": "ordered"}
    assert procurement.calls == [("evt-9", "P-100", 4, "maint-0")]


def test_purchase_order_with_stock_available_is_a_result_not_an_error() -> None:
    out = _forwarder(procurement=FakeProcurement(reason="stock_available")).forward(
        MAINT, "create_purchase_order", ORDER, 5
    )
    assert out == {"ordered": False, "reason": "stock_available"}


@pytest.mark.parametrize("error", [UnknownPart("P-100"), IdempotencyConflict("reuse")])
def test_purchase_order_denies_unknown_part_and_key_reuse(error: Exception) -> None:
    with pytest.raises(ToolDenied):
        _forwarder(procurement=FakeProcurement(error)).forward(
            MAINT, "create_purchase_order", ORDER, 5
        )


@pytest.mark.parametrize("tool", ["open_ticket", "dispatch_tech", "create_purchase_order"])
def test_without_ports_the_tools_stay_unavailable(tool: str) -> None:
    with pytest.raises(ToolUnavailable):
        _forwarder().forward(MAINT, tool, {}, 5)
