"""reserve and order check the ticket machine against the compatibility table (ADR-065).

The order of statements matters: the part row is locked first, then the ticket and the pair are
read, then the idempotency row, then stock. A refused call changes nothing.
"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from db_fakes import FakeDatabase

from waggle.db.compatibility import IncompatiblePart
from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict
from waggle.db.inventory import InventoryRepository, UnknownPart
from waggle.db.procurement import ProcurementRepository
from waggle.db.tickets import UnknownTicket

Row = tuple[object, ...] | None
TICKET = "tkt-0000000000000001"
OTHER = "tkt-0000000000000002"


def _database(
    *,
    part: Row = (5, 0),
    ticket: Row = ("open", "C1"),
    pair: Row = (1,),
    prior: Row = None,
) -> FakeDatabase:
    def handler(sql: str, params: tuple[object, ...]) -> Row:
        if "FROM spare_parts" in sql:
            return part
        if "FROM maintenance_tickets" in sql:
            return ticket
        if "FROM part_compatibility" in sql:
            return pair
        if "FROM part_reservations" in sql or "FROM purchase_orders" in sql:
            return prior
        return None

    return FakeDatabase(handler)


def _reserve(db: FakeDatabase, ticket_id: str = TICKET, part: str = "P-1") -> object:
    return InventoryRepository(db).reserve("k-1", part, 2, "maint-0", ticket_id)  # type: ignore[arg-type]


def _order(db: FakeDatabase, ticket_id: str = TICKET, part: str = "P-1") -> object:
    return ProcurementRepository(db).order("k-1", part, 2, "maint-0", ticket_id)  # type: ignore[arg-type]


CALLS = pytest.mark.parametrize("call", [_reserve, _order], ids=["reserve", "order"])


def _first_index(db: FakeDatabase, fragment: str) -> int:
    return next(i for i, s in enumerate(db.log) if fragment in s)


@CALLS
def test_a_listed_pair_reaches_the_stock_logic(call: Callable[..., object]) -> None:
    db = _database(part=(0, 0)) if call is _order else _database()
    call(db)
    assert db.writes() != []


@CALLS
def test_an_incompatible_part_is_refused_and_writes_nothing(call: Callable[..., object]) -> None:
    db = _database(pair=None, part=(0, 0))
    with pytest.raises(IncompatiblePart):
        call(db)
    assert db.writes() == []
    assert not any("part_reservations" in s or "purchase_orders" in s for s in db.log)


@CALLS
def test_an_unknown_ticket_is_refused_and_writes_nothing(call: Callable[..., object]) -> None:
    db = _database(ticket=None)
    with pytest.raises(UnknownTicket):
        call(db)
    assert db.writes() == []


@CALLS
def test_a_ticket_that_is_not_live_is_refused(call: Callable[..., object]) -> None:
    with pytest.raises(UnknownTicket):
        call(_database(ticket=("closed", "C1")))


@CALLS
def test_an_unknown_part_is_refused_before_the_ticket_is_read(call: Callable[..., object]) -> None:
    db = _database(part=None)
    with pytest.raises(UnknownPart):
        call(db)
    assert not any("maintenance_tickets" in s for s in db.log)


@CALLS
def test_statements_run_in_the_documented_order(call: Callable[..., object]) -> None:
    db = _database(part=(0, 0), prior=None)
    call(db)
    lock = _first_index(db, "FROM spare_parts")
    ticket = _first_index(db, "FROM maintenance_tickets")
    pair = _first_index(db, "FROM part_compatibility")
    prior = next(i for i, s in enumerate(db.log) if "idempotency_key=%s" in s and "SELECT" in s)
    assert "FOR UPDATE" in db.log[lock]
    assert lock < ticket < pair < prior


@CALLS
def test_the_whole_check_runs_in_one_transaction(call: Callable[..., object]) -> None:
    db = _database(part=(0, 0))
    call(db)
    assert db.transactions == 1


def test_reserve_stores_the_ticket_with_the_key_row() -> None:
    db = _database()
    _reserve(db)
    insert = next(s for s in db.writes() if s.startswith("INSERT INTO part_reservations"))
    assert "ticket_id" in insert


def test_order_stores_the_ticket_with_the_key_row() -> None:
    db = _database(part=(0, 0))
    _order(db)
    insert = next(s for s in db.writes() if s.startswith("INSERT INTO purchase_orders"))
    assert "ticket_id" in insert


def test_reserve_replay_on_the_same_ticket_is_not_a_conflict() -> None:
    db = _database(prior=("P-1", 2, "maint-0", TICKET))
    assert _reserve(db).reason == "replayed"  # type: ignore[attr-defined]
    assert db.writes() == []


def test_order_replay_on_the_same_ticket_is_not_a_conflict() -> None:
    db = _database(prior=("P-1", 2, "maint-0", TICKET))
    assert _order(db).reason == "replayed"  # type: ignore[attr-defined]
    assert db.writes() == []


@CALLS
def test_one_key_cannot_be_reused_on_another_ticket(call: Callable[..., object]) -> None:
    db = _database(prior=("P-1", 2, "maint-0", OTHER))
    with pytest.raises(IdempotencyConflict):
        call(db)
    assert db.writes() == []


@CALLS
def test_a_key_row_written_before_the_migration_conflicts_with_any_ticket(
    call: Callable[..., object],
) -> None:
    db = _database(prior=("P-1", 2, "maint-0", None))
    with pytest.raises(IdempotencyConflict):
        call(db)


@pytest.mark.parametrize("bad", ["", "a b", "x" * 65, "t;DROP", "café", None, 5])
def test_a_malformed_ticket_id_never_connects(bad: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        InventoryRepository(database).reserve("k-1", "P-1", 1, "maint-0", bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProcurementRepository(database).order("k-1", "P-1", 1, "maint-0", bad)  # type: ignore[arg-type]
    database.transaction.assert_not_called()
