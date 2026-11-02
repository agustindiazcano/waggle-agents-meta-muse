"""Argument checks of the technician lease and settlement repositories run before any query."""

from collections.abc import Callable
from typing import Any

import pytest
from db_fakes import FakeDatabase

from waggle.db.settlement import SettlementRepository
from waggle.db.ticket_lease import TicketLeaseRepository

TICKET = "tkt-0000000000000001"


def _db() -> FakeDatabase:
    return FakeDatabase(lambda sql, params: None)


def _lease(db: FakeDatabase) -> TicketLeaseRepository:
    return TicketLeaseRepository(db)  # type: ignore[arg-type]


def _settlement(db: FakeDatabase) -> SettlementRepository:
    return SettlementRepository(db)  # type: ignore[arg-type]


BAD_CALLS: list[Callable[[FakeDatabase], Any]] = [
    lambda db: _lease(db).dispatch("bad id", "zone-1", "maint-0", "tech-1", 0, ()),
    lambda db: _lease(db).dispatch(TICKET, "", "maint-0", "tech-1", 0, ()),
    lambda db: _lease(db).dispatch(TICKET, "zone-1", "maint-0", "tech 1", 0, ()),
    lambda db: _lease(db).dispatch(TICKET, "zone-1", "maint-0", "tech-1", -1, ()),
    lambda db: _lease(db).dispatch(TICKET, "zone-1", "maint-0", "tech-1", True, ()),
    lambda db: _lease(db).dispatch(TICKET, "zone-1", "maint-0", "tech-1", 0, (), lease_ticks=0),
    lambda db: _lease(db).close("bad id", "maint-0", 0, ()),
    lambda db: _lease(db).close(TICKET, "", 0, ()),
    lambda db: _lease(db).close(TICKET, "maint-0", -3, ()),
    lambda db: _lease(db).reopen_expired(-1, ()),
    lambda db: _settlement(db).consume("bad key!"),
    lambda db: _settlement(db).release(""),
]


@pytest.mark.parametrize("call", BAD_CALLS)
def test_a_malformed_argument_is_refused_before_any_query(
    call: Callable[[FakeDatabase], Any],
) -> None:
    db = _db()
    with pytest.raises(ValueError):
        call(db)
    assert db.log == [] and db.transactions == 0
