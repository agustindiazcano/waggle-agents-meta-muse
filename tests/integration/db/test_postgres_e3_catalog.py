"""Cloud-only E3 catalog check against the PostgreSQL catalog and procurement repositories."""

from pathlib import Path

import pytest

from waggle.db.connection import Database
from waggle.db.inventory import InventoryRepository
from waggle.db.procurement import ProcurementRepository
from waggle.experiments.e3_catalog import run_catalog_check, seed_catalog
from waggle.experiments.e3_eval import load_cases

pytestmark = pytest.mark.heavy

CASES = load_cases(Path(__file__).resolve().parents[3] / "data" / "e3" / "cases.json")


def test_the_catalog_blocks_the_absent_part_and_misses_the_incompatible_one(
    database: Database,
) -> None:
    seed_catalog(InventoryRepository(database))
    report = run_catalog_check(CASES, ProcurementRepository(database))
    by_id = {o.case_id: o for o in report.outcomes}
    assert not by_id["E3-T3-01"].forwarded
    assert by_id["E3-T3-03"].forwarded
    # Expected gap: the catalog has no compatibility check, so an existing part is accepted.
    assert report.missed_injections == ("E3-T3-02",)
    assert report.false_blocks == ()


def test_a_second_run_on_the_same_database_places_no_new_order(database: Database) -> None:
    seed_catalog(InventoryRepository(database))
    first = run_catalog_check(CASES, ProcurementRepository(database))
    second = run_catalog_check(CASES, ProcurementRepository(database))
    assert [o.forwarded for o in first.outcomes] == [o.forwarded for o in second.outcomes]
