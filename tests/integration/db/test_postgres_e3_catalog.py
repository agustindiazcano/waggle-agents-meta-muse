"""Cloud-only E3 catalog check against the PostgreSQL catalog, tickets and procurement."""

from pathlib import Path

import pytest

from waggle.db.compatibility import CompatibilityRepository
from waggle.db.connection import Database
from waggle.db.inventory import InventoryRepository
from waggle.db.procurement import ProcurementRepository
from waggle.db.tickets import TicketRepository
from waggle.experiments.e3_catalog import run_catalog_check, seed_catalog
from waggle.experiments.e3_eval import load_cases

pytestmark = pytest.mark.heavy

CASES = load_cases(Path(__file__).resolve().parents[3] / "data" / "e3" / "cases.json")


def _seed(database: Database) -> str:
    return seed_catalog(
        InventoryRepository(database),
        TicketRepository(database),
        CompatibilityRepository(database),
    )


def test_the_catalog_blocks_the_absent_part_and_the_incompatible_one(database: Database) -> None:
    ticket_id = _seed(database)
    report = run_catalog_check(CASES, ProcurementRepository(database), ticket_id)
    by_id = {o.case_id: o for o in report.outcomes}
    assert not by_id["E3-T3-01"].forwarded
    assert not by_id["E3-T3-02"].forwarded
    assert by_id["E3-T3-03"].forwarded
    assert report.missed_injections == ()
    assert report.false_blocks == ()


def test_a_second_run_on_the_same_database_places_no_new_order(database: Database) -> None:
    ticket_id = _seed(database)
    first = run_catalog_check(CASES, ProcurementRepository(database), ticket_id)
    second = run_catalog_check(CASES, ProcurementRepository(database), ticket_id)
    assert [o.forwarded for o in first.outcomes] == [o.forwarded for o in second.outcomes]


def test_without_the_compatibility_rows_every_order_is_blocked(database: Database) -> None:
    inventory, tickets = InventoryRepository(database), TicketRepository(database)
    # The check fails closed: with an empty table even the compatible part is refused.
    for part in ("BRG-6204", "SEAL-08"):
        inventory.add_part(part, 0)
    tickets.add_machine("C1")
    ticket_id = tickets.open_ticket("e3-catalog-c1", "C1", "no rows loaded", "e3-catalog").ticket_id
    report = run_catalog_check(CASES, ProcurementRepository(database), ticket_id)
    assert report.false_blocks == ("E3-T3-03",)
