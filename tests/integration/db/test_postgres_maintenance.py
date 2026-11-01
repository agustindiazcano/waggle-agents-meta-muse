"""Cloud-only ticket and procurement checks against PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository, IdempotencyConflict
from waggle.db.inventory import InventoryRepository, UnknownPart
from waggle.db.procurement import ProcurementRepository
from waggle.db.tickets import (
    TicketRepository,
    UnknownMachine,
    UnknownTicket,
    UnknownZone,
    ticket_id_for,
)

pytestmark = pytest.mark.heavy


def _tickets(database: Database) -> TicketRepository:
    repo = TicketRepository(database)
    repo.add_machine("M-1")
    return repo


def _zone(database: Database, zone_id: str = "zone-1") -> None:
    CorridorRepository(database).register((zone_id,))


def test_ticket_for_an_unknown_machine_is_refused(database: Database) -> None:
    with pytest.raises(UnknownMachine):
        TicketRepository(database).open_ticket("evt-1", "M-9", "noise", "tech-0")


def test_one_event_key_opens_one_ticket(database: Database) -> None:
    repo = _tickets(database)
    first = repo.open_ticket("evt-1", "M-1", "noise", "tech-0")
    again = repo.open_ticket("evt-1", "M-1", "noise", "tech-0")
    assert (first.created, again.created) == (True, False)
    assert first.ticket_id == again.ticket_id == ticket_id_for("evt-1")


def test_same_key_with_other_values_conflicts(database: Database) -> None:
    repo = _tickets(database)
    repo.open_ticket("evt-1", "M-1", "noise", "tech-0")
    with pytest.raises(IdempotencyConflict):
        repo.open_ticket("evt-1", "M-1", "different text", "tech-0")


def test_concurrent_calls_with_one_key_open_one_ticket(database: Database) -> None:
    repo = _tickets(database)
    rounds = 10
    for n in range(rounds):
        key = f"evt-{n}"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(lambda _i, k=key: repo.open_ticket(k, "M-1", "noise", "tech-0"), range(8))
            )
        assert sum(r.created for r in results) == 1
    with database.transaction() as connection:
        row = connection.execute("SELECT count(*) FROM maintenance_tickets").fetchone()
    assert row is not None and row[0] == rounds


def test_dispatch_requires_a_known_ticket_and_zone(database: Database) -> None:
    repo = _tickets(database)
    _zone(database)
    with pytest.raises(UnknownTicket):
        repo.dispatch("tkt-missing", "zone-1", "maint-0")
    ticket = repo.open_ticket("evt-1", "M-1", "noise", "tech-0")
    with pytest.raises(UnknownZone):
        repo.dispatch(ticket.ticket_id, "zone-9", "maint-0")


def test_dispatch_is_idempotent_for_one_zone_and_conflicts_for_another(database: Database) -> None:
    repo = _tickets(database)
    _zone(database, "zone-1")
    _zone(database, "zone-2")
    ticket = repo.open_ticket("evt-1", "M-1", "noise", "tech-0")
    first = repo.dispatch(ticket.ticket_id, "zone-1", "maint-0")
    again = repo.dispatch(ticket.ticket_id, "zone-1", "maint-0")
    assert (first.created, again.created) == (True, False)
    with pytest.raises(IdempotencyConflict):
        repo.dispatch(ticket.ticket_id, "zone-2", "maint-0")


def _procurement(database: Database, on_hand: int) -> ProcurementRepository:
    InventoryRepository(database).add_part("P-100", on_hand)
    return ProcurementRepository(database)


def test_order_for_a_part_outside_the_catalog_is_refused(database: Database) -> None:
    with pytest.raises(UnknownPart):
        ProcurementRepository(database).order("evt-1", "P-999", 1, "maint-0")


def test_order_is_refused_while_stock_is_available(database: Database) -> None:
    result = _procurement(database, 3).order("evt-1", "P-100", 2, "maint-0")
    assert (result.ordered, result.reason) == (False, "stock_available")


def test_order_is_placed_once_when_stock_is_exhausted(database: Database) -> None:
    repo = _procurement(database, 1)
    InventoryRepository(database).reserve("res-1", "P-100", 1, "maint-0")
    first = repo.order("evt-1", "P-100", 5, "maint-0")
    again = repo.order("evt-1", "P-100", 5, "maint-0")
    assert (first.ordered, first.reason) == (True, "ordered")
    assert (again.ordered, again.reason) == (True, "replayed")
    with pytest.raises(IdempotencyConflict):
        repo.order("evt-1", "P-100", 6, "maint-0")


def test_concurrent_orders_with_one_key_place_one_order(database: Database) -> None:
    repo = _procurement(database, 0)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _i: repo.order("evt-1", "P-100", 5, "maint-0"), range(6)))
    assert all(r.ordered for r in results)
    with database.transaction() as connection:
        row = connection.execute("SELECT count(*) FROM purchase_orders").fetchone()
    assert row is not None and row[0] == 1
