"""Ticket and procurement repositories reject malformed input before any transaction."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.procurement import ProcurementRepository
from waggle.db.tickets import TicketRepository, ticket_id_for

BAD_IDS = ["", "a b", "x" * 65, "m;DROP", "café"]


def _bad_key(bad: str) -> str:
    """Keys allow 128 characters, so the 65 character case becomes a 129 character one."""
    return "k" * 129 if len(bad) == 65 else bad


def test_ticket_id_is_derived_from_the_key() -> None:
    assert ticket_id_for("evt-1") == ticket_id_for("evt-1")
    assert ticket_id_for("evt-1") != ticket_id_for("evt-2")
    assert ticket_id_for("evt-1").startswith("tkt-")


@pytest.mark.parametrize("bad", BAD_IDS)
def test_malformed_ids_never_connect(bad: str) -> None:
    database = MagicMock(spec=Database)
    repo = TicketRepository(database)
    with pytest.raises(ValueError):
        repo.add_machine(bad)
    with pytest.raises(ValueError):
        repo.open_ticket(_bad_key(bad), "M-1", "summary", "tech-0")
    with pytest.raises(ValueError):
        repo.open_ticket("evt-1", bad, "summary", "tech-0")
    with pytest.raises(ValueError):
        repo.dispatch(bad, "zone-1", "maint-0")
    with pytest.raises(ValueError):
        repo.dispatch("tkt-1", bad, "maint-0")
    database.transaction.assert_not_called()


@pytest.mark.parametrize("summary", ["", "x" * 501, "line\nbreak", "nul\x00", 5])
def test_invalid_summary_never_connects(summary: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        TicketRepository(database).open_ticket("evt-1", "M-1", summary, "tech-0")  # type: ignore[arg-type]
    database.transaction.assert_not_called()


@pytest.mark.parametrize("bad", BAD_IDS)
def test_malformed_order_ids_never_connect(bad: str) -> None:
    database = MagicMock(spec=Database)
    repo = ProcurementRepository(database)
    with pytest.raises(ValueError):
        repo.order(_bad_key(bad), "P-100", 1, "maint-0")
    with pytest.raises(ValueError):
        repo.order("evt-1", bad, 1, "maint-0")
    database.transaction.assert_not_called()


@pytest.mark.parametrize("quantity", [0, -1, 1001, True, 2.0, "3"])
def test_invalid_order_quantity_never_connects(quantity: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        ProcurementRepository(database).order("evt-1", "P-100", quantity, "maint-0")  # type: ignore[arg-type]
    database.transaction.assert_not_called()
