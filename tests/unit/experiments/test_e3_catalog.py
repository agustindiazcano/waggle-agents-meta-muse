"""E3 runner for the catalog check layer, over a fake orderer (the database run is cloud-only)."""

from collections.abc import Callable
from pathlib import Path

from waggle.db.compatibility import IncompatiblePart
from waggle.db.inventory import UnknownPart
from waggle.db.procurement import OrderResult
from waggle.experiments import e3_catalog
from waggle.experiments.e3_catalog import (
    CATALOG_LAYER,
    COMPATIBILITY,
    PART_FOR_CASE,
    PARTS,
    run_catalog_check,
)
from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer == CATALOG_LAYER}
TICKET = "tkt-00000000000000c1"
Lookup = Callable[[str, str], bool]


def _listed(machine_id: str, part_number: str) -> bool:
    return (machine_id, part_number) in set(COMPATIBILITY)


class _Orderer:
    """Orders a part in its catalog when the lookup says it fits the machine of the ticket.

    The ticket maps to conveyor C1, like the ticket the cloud runner opens. The default lookup
    reads the rows the runner loads; a stub can replace it.
    """

    def __init__(self, known: set[str], lookup: Lookup = _listed) -> None:
        self.known = known
        self.lookup = lookup
        self.placed: list[str] = []
        self.tickets: list[str] = []

    def order(
        self, key: str, part_number: str, quantity: int, requester: str, ticket_id: str
    ) -> OrderResult:
        self.tickets.append(ticket_id)
        if part_number not in self.known:
            raise UnknownPart(part_number)
        if not self.lookup("C1", part_number):
            raise IncompatiblePart(part_number)
        self.placed.append(part_number)
        return OrderResult(True, "ordered", part_number, quantity)


def test_every_catalog_case_has_exactly_one_part_fixture() -> None:
    assert set(PART_FOR_CASE) == LAYER_IDS
    assert len(LAYER_IDS) == 3


def test_the_catalog_layer_is_runnable() -> None:
    assert CATALOG_LAYER in RUNNABLE_LAYERS


def test_the_fixture_rows_match_the_case_setup() -> None:
    assert set(COMPATIBILITY) == {("C1", "BRG-6204"), ("P1", "SEAL-08")}
    assert set(PARTS) == {"BRG-6204", "SEAL-08"}


def test_the_absent_part_and_the_incompatible_part_are_blocked_and_the_fit_is_served() -> None:
    orderer = _Orderer(set(PARTS))
    report = run_catalog_check(CASES, orderer, TICKET)
    by_id = {o.case_id: o for o in report.outcomes}
    assert not by_id["E3-T3-01"].forwarded
    assert not by_id["E3-T3-02"].forwarded
    assert by_id["E3-T3-03"].forwarded
    assert report.missed_injections == ()
    assert report.false_blocks == ()
    assert orderer.placed == ["BRG-6204"]


def test_the_incompatible_part_is_reported_with_its_own_block_code() -> None:
    by_id = {o.case_id: o for o in run_catalog_check(CASES, _Orderer(set(PARTS)), TICKET).outcomes}
    assert by_id["E3-T3-01"].code == "unknown_part"
    assert by_id["E3-T3-02"].code == "incompatible_part"


def test_every_order_names_the_given_ticket() -> None:
    orderer = _Orderer(set(PARTS))
    run_catalog_check(CASES, orderer, TICKET)
    assert orderer.tickets == [TICKET] * 3


def test_sensitivity_a_lookup_that_allows_every_pair_makes_the_gap_visible() -> None:
    # If the compatibility lookup is a stub that says yes to everything, the runner must report
    # E3-T3-02 as accepted. Without this the green result could come from a runner that cannot fail.
    report = run_catalog_check(CASES, _Orderer(set(PARTS), lookup=lambda m, p: True), TICKET)
    assert report.missed_injections == ("E3-T3-02",)
    assert report.false_blocks == ()


def test_a_catalog_that_lists_the_absent_part_with_an_allow_all_lookup_misses_both() -> None:
    orderer = _Orderer(set(PARTS) | {"FREE-KIT-999"}, lookup=lambda m, p: True)
    report = run_catalog_check(CASES, orderer, TICKET)
    assert set(report.missed_injections) == {"E3-T3-01", "E3-T3-02"}


def test_an_empty_catalog_is_reported_as_a_false_block() -> None:
    report = run_catalog_check(CASES, _Orderer(set()), TICKET)
    assert report.false_blocks == ("E3-T3-03",)


def test_a_lookup_that_denies_every_pair_is_reported_as_a_false_block() -> None:
    report = run_catalog_check(CASES, _Orderer(set(PARTS), lookup=lambda m, p: False), TICKET)
    assert report.false_blocks == ("E3-T3-03",)
    assert report.missed_injections == ()


def test_the_layer_name_is_the_corpus_target_layer() -> None:
    assert e3_catalog.CATALOG_LAYER == "catalog_check"


def test_the_docstring_says_the_check_was_added_after_the_case_was_seen_to_pass() -> None:
    doc = " ".join((e3_catalog.__doc__ or "").split())
    assert "added after" in doc
    assert "regression test" in doc
    assert "not an unbiased measurement" in doc
