"""Cloud-only checks of the technician lease, ticket close and reservation settlement (rev 11)."""

from concurrent.futures import ThreadPoolExecutor

import psycopg.errors
import pytest
from catalog_support import seed_ticket
from postgres_support import isolated_database

from waggle.coordination.corridors import ZoneObservation
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository, IdempotencyConflict
from waggle.db.inventory import InventoryRepository
from waggle.db.schema import current_revision, migrate
from waggle.db.settlement import ReservationSettled, SettlementRepository, UnknownReservation
from waggle.db.ticket_lease import TicketLeaseRepository
from waggle.db.tickets import TicketRepository, UnknownTicket, UnknownZone

pytestmark = pytest.mark.heavy

ZONE = "zone-1"


def _clear(tick: int, zone: str = ZONE) -> tuple[ZoneObservation, ...]:
    return (ZoneObservation(zone, tick, ()),)


def _setup(database: Database, zones: tuple[str, ...] = (ZONE,)) -> str:
    CorridorRepository(database).register(zones)
    InventoryRepository(database).add_part("P-100", 5)
    return seed_ticket(database)


def _zone_row(database: Database, zone: str = ZONE) -> tuple[object, ...]:
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT holder, token, expires_tick FROM zones WHERE zone_id=%s", (zone,)
        ).fetchone()
    assert row is not None
    return tuple(row)


def _stock(database: Database) -> tuple[int, int]:
    stock = InventoryRepository(database).get("P-100")
    assert stock is not None
    return stock.on_hand, stock.reserved


def _status(database: Database, ticket: str) -> tuple[object, ...]:
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT status, technician, zone_token FROM maintenance_tickets WHERE ticket_id=%s",
            (ticket,),
        ).fetchone()
    assert row is not None
    return tuple(row)


def test_revision_eleven_upgrade_keeps_old_tickets_and_reservations_valid() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=10) == 10
        CorridorRepository(db).register((ZONE,))
        InventoryRepository(db).add_part("P-100", 5)
        ticket = seed_ticket(db)
        InventoryRepository(db).reserve("k-1", "P-100", 2, "maint-0", ticket)
        TicketRepository(db).dispatch(ticket, ZONE, "maint-0")
        assert migrate(db, expected_revision=10, target_revision=11) == 11
        assert current_revision(db) == 11
        assert _status(db, ticket) == ("dispatched", None, None)
        with db.transaction() as connection:
            row = connection.execute("SELECT status, settled_at FROM part_reservations").fetchone()
        assert row is not None and tuple(row) == ("reserved", None)


def test_the_widened_constraint_still_refuses_a_half_dispatched_ticket(database: Database) -> None:
    ticket = _setup(database)
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
        connection.execute(
            "UPDATE maintenance_tickets SET status='dispatched', zone_id=%s, dispatched_by='m', "
            "technician='tech-1' WHERE ticket_id=%s",
            (ZONE, ticket),
        )
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
        connection.execute(
            "UPDATE maintenance_tickets SET status='closed' WHERE ticket_id=%s", (ticket,)
        )


def test_dispatch_takes_the_zone_lease_for_the_named_technician(database: Database) -> None:
    ticket = _setup(database)
    result = TicketLeaseRepository(database).dispatch(
        ticket, ZONE, "maint-0", "tech-1", 10, _clear(10)
    )
    assert result.dispatched and result.created and result.token == 1
    assert _zone_row(database) == ("tech-1", 1, 410)
    assert _status(database, ticket) == ("dispatched", "tech-1", 1)


def test_a_repeat_replays_and_another_zone_or_technician_conflicts(database: Database) -> None:
    ticket = _setup(database, (ZONE, "zone-2"))
    repo = TicketLeaseRepository(database)
    repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    again = repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 11, _clear(11))
    assert again.dispatched and not again.created and again.token == 1
    assert _zone_row(database) == ("tech-1", 1, 410)
    with pytest.raises(IdempotencyConflict):
        repo.dispatch(ticket, "zone-2", "maint-0", "tech-1", 12, _clear(12, "zone-2"))
    with pytest.raises(IdempotencyConflict):
        repo.dispatch(ticket, ZONE, "maint-0", "tech-2", 12, _clear(12))


def test_a_zone_held_elsewhere_leaves_the_ticket_open_and_the_zone_unchanged(
    database: Database,
) -> None:
    ticket = _setup(database)
    other = seed_ticket(database, "M-2", key="tkt-evt-2")
    repo = TicketLeaseRepository(database)
    assert repo.dispatch(other, ZONE, "maint-0", "tech-9", 10, _clear(10)).dispatched
    before = _zone_row(database)
    result = repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 11, _clear(11))
    assert not result.dispatched and result.token is None
    assert _zone_row(database) == before
    assert _status(database, ticket) == ("open", None, None)


def test_one_technician_cannot_hold_two_tickets_on_one_zone(database: Database) -> None:
    first = _setup(database)
    second = seed_ticket(database, "M-2", key="tkt-evt-2")
    repo = TicketLeaseRepository(database)
    assert repo.dispatch(first, ZONE, "maint-0", "tech-1", 10, _clear(10)).dispatched
    denied = repo.dispatch(second, ZONE, "maint-0", "tech-1", 11, _clear(11))
    assert not denied.dispatched
    assert _status(database, second) == ("open", None, None)


def test_an_unknown_or_closed_ticket_and_an_unknown_zone_are_refused(database: Database) -> None:
    ticket = _setup(database)
    repo = TicketLeaseRepository(database)
    with pytest.raises(UnknownTicket):
        repo.dispatch("tkt-0000000000000009", ZONE, "maint-0", "tech-1", 10, _clear(10))
    with pytest.raises(UnknownZone):
        repo.dispatch(ticket, "zone-9", "maint-0", "tech-1", 10, ())
    assert _status(database, ticket) == ("open", None, None)


def test_an_unknown_occupancy_denies_the_dispatch(database: Database) -> None:
    ticket = _setup(database)
    result = TicketLeaseRepository(database).dispatch(ticket, ZONE, "maint-0", "tech-1", 10, ())
    assert not result.dispatched
    assert _status(database, ticket) == ("open", None, None)
    assert _zone_row(database)[0] is None


def test_concurrent_dispatches_of_one_ticket_give_one_lease(database: Database) -> None:
    ticket = _setup(database)
    repo = TicketLeaseRepository(database)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _i: repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10)),
                range(8),
            )
        )
    assert all(r.dispatched for r in results)
    assert sum(r.created for r in results) == 1
    assert {r.token for r in results} == {1}
    assert _zone_row(database) == ("tech-1", 1, 410)


def test_close_releases_the_zone_and_settles_reservations_together(database: Database) -> None:
    ticket = _setup(database)
    InventoryRepository(database).reserve("k-1", "P-100", 2, "maint-0", ticket)
    repo = TicketLeaseRepository(database)
    repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    closed = repo.close(ticket, "maint-0", 50, _clear(50))
    assert closed.closed and closed.created
    assert _zone_row(database)[0] is None
    assert _status(database, ticket)[0] == "closed"
    assert _stock(database) == (5, 0)
    with database.transaction() as connection:
        row = connection.execute("SELECT status FROM part_reservations").fetchone()
    assert row is not None and row[0] == "released"
    again = repo.close(ticket, "maint-0", 51, _clear(51))
    assert again.closed and not again.created
    assert _stock(database) == (5, 0)


def test_close_is_denied_while_the_zone_is_occupied_or_unknown(database: Database) -> None:
    ticket = _setup(database)
    InventoryRepository(database).reserve("k-1", "P-100", 2, "maint-0", ticket)
    repo = TicketLeaseRepository(database)
    repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    for observations in ((), (ZoneObservation(ZONE, 50, ("tech-1",)),)):
        denied = repo.close(ticket, "maint-0", 50, observations)
        assert not denied.closed
        assert _status(database, ticket) == ("dispatched", "tech-1", 1)
        assert _zone_row(database)[0] == "tech-1"
        assert _stock(database) == (5, 2)


def test_a_stale_technician_cannot_close_after_the_lease_expired(database: Database) -> None:
    ticket = _setup(database)
    InventoryRepository(database).reserve("k-1", "P-100", 2, "maint-0", ticket)
    repo = TicketLeaseRepository(database)
    repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    other = seed_ticket(database, "M-2", key="tkt-evt-2")
    assert repo.dispatch(other, ZONE, "maint-0", "tech-2", 500, _clear(500)).dispatched
    stale = repo.close(ticket, "maint-0", 501, _clear(501))
    assert not stale.closed
    assert _zone_row(database)[0] == "tech-2"
    assert _stock(database) == (5, 2)


def test_close_of_an_open_or_unknown_ticket_is_refused(database: Database) -> None:
    ticket = _setup(database)
    repo = TicketLeaseRepository(database)
    with pytest.raises(UnknownTicket):
        repo.close(ticket, "maint-0", 10, _clear(10))
    with pytest.raises(UnknownTicket):
        repo.close("tkt-0000000000000009", "maint-0", 10, _clear(10))


def test_a_lease_that_expired_reopens_the_ticket_once_and_frees_the_zone(
    database: Database,
) -> None:
    ticket = _setup(database)
    repo = TicketLeaseRepository(database)
    repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    assert repo.reopen_expired(100, _clear(100)) == ()
    assert _status(database, ticket)[0] == "dispatched"
    assert repo.reopen_expired(410, _clear(410)) == (ticket,)
    assert _status(database, ticket) == ("open", None, None)
    assert _zone_row(database)[0] is None
    assert repo.reopen_expired(411, _clear(411)) == ()


def test_an_expired_lease_in_an_occupied_zone_keeps_the_ticket_and_the_zone_blocked(
    database: Database,
) -> None:
    ticket = _setup(database)
    repo = TicketLeaseRepository(database)
    repo.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    assert repo.reopen_expired(410, (ZoneObservation(ZONE, 410, ("tech-1",)),)) == ()
    assert _status(database, ticket)[0] == "dispatched"
    assert _zone_row(database)[0] == "tech-1"


def test_consume_takes_stock_out_once(database: Database) -> None:
    ticket = _setup(database)
    InventoryRepository(database).reserve("k-1", "P-100", 2, "maint-0", ticket)
    settle = SettlementRepository(database)
    assert settle.consume("k-1").changed
    assert _stock(database) == (3, 0)
    assert not settle.consume("k-1").changed
    assert _stock(database) == (3, 0)
    with pytest.raises(ReservationSettled):
        settle.release("k-1")
    assert _stock(database) == (3, 0)


def test_release_returns_the_reserved_units_once(database: Database) -> None:
    ticket = _setup(database)
    InventoryRepository(database).reserve("k-1", "P-100", 2, "maint-0", ticket)
    settle = SettlementRepository(database)
    assert settle.release("k-1").changed
    assert _stock(database) == (5, 0)
    assert not settle.release("k-1").changed
    with pytest.raises(ReservationSettled):
        settle.consume("k-1")
    assert _stock(database) == (5, 0)


def test_an_unknown_reservation_is_refused(database: Database) -> None:
    _setup(database)
    with pytest.raises(UnknownReservation):
        SettlementRepository(database).consume("k-9")


def test_concurrent_consumes_change_stock_once(database: Database) -> None:
    ticket = _setup(database)
    InventoryRepository(database).reserve("k-1", "P-100", 2, "maint-0", ticket)
    settle = SettlementRepository(database)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _i: settle.consume("k-1"), range(8)))
    assert sum(r.changed for r in results) == 1
    assert _stock(database) == (3, 0)


def test_zone_of_reports_the_zone_of_a_dispatched_ticket_and_none_before(
    database: Database,
) -> None:
    ticket = _setup(database)
    leases = TicketLeaseRepository(database)
    assert leases.zone_of(ticket) is None
    assert leases.zone_of("tkt-0000000000000099") is None
    leases.dispatch(ticket, ZONE, "maint-0", "tech-1", 10, _clear(10))
    assert leases.zone_of(ticket) == ZONE
