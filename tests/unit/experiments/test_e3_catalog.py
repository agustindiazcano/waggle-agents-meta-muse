"""E3 runner for the catalog check layer, over a fake orderer (the database run is cloud-only)."""

from pathlib import Path

from waggle.db.inventory import UnknownPart
from waggle.db.procurement import OrderResult
from waggle.experiments import e3_catalog
from waggle.experiments.e3_catalog import CATALOG_LAYER, PART_FOR_CASE, PARTS, run_catalog_check
from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer == CATALOG_LAYER}


class _Orderer:
    """Orders any part in its catalog, like the production repository without compatibility."""

    def __init__(self, known: set[str]) -> None:
        self.known = known
        self.placed: list[str] = []

    def order(self, key: str, part_number: str, quantity: int, requester: str) -> OrderResult:
        if part_number not in self.known:
            raise UnknownPart(part_number)
        self.placed.append(part_number)
        return OrderResult(True, "ordered", part_number, quantity)


def test_every_catalog_case_has_exactly_one_part_fixture() -> None:
    assert set(PART_FOR_CASE) == LAYER_IDS
    assert len(LAYER_IDS) == 3


def test_the_catalog_layer_is_runnable() -> None:
    assert CATALOG_LAYER in RUNNABLE_LAYERS


def test_an_absent_part_is_blocked_and_a_compatible_part_is_served() -> None:
    orderer = _Orderer(set(PARTS))
    report = run_catalog_check(CASES, orderer)
    by_id = {o.case_id: o for o in report.outcomes}
    assert not by_id["E3-T3-01"].forwarded
    assert by_id["E3-T3-03"].forwarded
    assert report.false_blocks == ()


def test_an_existing_incompatible_part_is_reported_as_a_missed_injection() -> None:
    # The catalog has no compatibility data, so existence alone lets E3-T3-02 through.
    report = run_catalog_check(CASES, _Orderer(set(PARTS)))
    assert report.missed_injections == ("E3-T3-02",)


def test_a_catalog_that_lists_the_absent_part_is_reported_as_one_more_miss() -> None:
    report = run_catalog_check(CASES, _Orderer(set(PARTS) | {"FREE-KIT-999"}))
    assert set(report.missed_injections) == {"E3-T3-01", "E3-T3-02"}


def test_an_empty_catalog_is_reported_as_a_false_block() -> None:
    report = run_catalog_check(CASES, _Orderer(set()))
    assert report.false_blocks == ("E3-T3-03",)


def test_the_layer_name_is_the_corpus_target_layer() -> None:
    assert e3_catalog.CATALOG_LAYER == "catalog_check"
