"""E3 runner for the catalog check layer (ADR-054).

Each case is run by placing the purchase order its text tries to cause (or, if benign, the
ordinary one) through the production procurement repository over a synthetic catalog. An
injection counts as blocked when no order is placed. The catalog has no compatibility data, so
an existing but incompatible part (E3-T3-02) is expected to be accepted: the run reports that
gap and does not hide it.

``PART_FOR_CASE`` is a fixture written from the case text. It is not a label and needs the same
maintainer review as ``ATTEMPTS`` in ``e3_mcp_layers``.
"""

from collections.abc import Mapping
from typing import Protocol

from waggle.db.inventory import InventoryRepository, UnknownPart
from waggle.db.procurement import OrderResult
from waggle.experiments.e3_eval import Case
from waggle.experiments.e3_mcp_layers import LayerOutcome, LayerReport

CATALOG_LAYER = "catalog_check"
# The synthetic catalog of the case setups. Stock is zero so an order is never skipped for stock.
PARTS: tuple[str, ...] = ("BRG-6204", "SEAL-08")
PART_FOR_CASE: Mapping[str, str] = {
    "E3-T3-01": "FREE-KIT-999",
    "E3-T3-02": "SEAL-08",
    "E3-T3-03": "BRG-6204",
}
_REQUESTER = "e3-catalog"


class Orderer(Protocol):
    """The order call of the procurement repository."""

    def order(self, key: str, part_number: str, quantity: int, requester: str) -> OrderResult:
        """Place an order or raise UnknownPart."""


def seed_catalog(inventory: InventoryRepository) -> None:
    """Load the synthetic catalog with no stock. For the E3 run and its tests only."""
    for part in PARTS:
        inventory.add_part(part, 0)


def _run(case: Case, part: str, orderer: Orderer) -> LayerOutcome:
    if case.label not in ("injection", "benign"):
        raise ValueError(f"{case.id}: only injection and benign cases can be run")
    try:
        result = orderer.order(f"e3-{case.id}", part, 1, _REQUESTER)
        placed, code = result.ordered, None
    except UnknownPart:
        placed, code = False, "unknown_part"
    return LayerOutcome(case.id, case.target_layer, case.label, placed, code)


def run_catalog_check(cases: tuple[Case, ...], orderer: Orderer) -> LayerReport:
    """Run every reviewed catalog case through ``orderer`` in id order."""
    chosen = sorted((c for c in cases if c.target_layer == CATALOG_LAYER), key=lambda c: c.id)
    missing = [c.id for c in chosen if c.id not in PART_FOR_CASE]
    if missing:
        raise KeyError("no part fixture for: " + ", ".join(missing))
    return LayerReport(tuple(_run(c, PART_FOR_CASE[c.id], orderer) for c in chosen))
