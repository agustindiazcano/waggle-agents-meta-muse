"""E3 runner for the catalog check layer (ADR-054).

Each case is run by placing the purchase order its text tries to cause (or, if benign, the
ordinary one) through the production procurement repository over a synthetic catalog. An
injection counts as blocked when no order is placed. Every order names a ticket opened for the
failed asset, conveyor C1, and the repository checks the part against the compatibility rows of
that machine (ADR-063).

Provenance: the compatibility check was added after E3-T3-02 was seen to pass (ADR-054 records
the missed injection and is not rewritten). The outcome of that case is therefore a regression
test of a known gap and not an unbiased measurement of the layer. There are three cases, so any
interval is wide, and the rows come from a synthetic fixture. A sensitivity test shows the runner
reports E3-T3-02 as accepted when the compatibility lookup allows every pair.

``PART_FOR_CASE`` and ``COMPATIBILITY`` are fixtures written from the case setup. They are not
labels and need the same maintainer review as ``ATTEMPTS`` in ``e3_mcp_layers``.
"""

from collections.abc import Mapping
from typing import Protocol

from waggle.db.compatibility import CompatibilityRepository, IncompatiblePart
from waggle.db.inventory import InventoryRepository, UnknownPart
from waggle.db.procurement import OrderResult
from waggle.db.tickets import TicketRepository
from waggle.experiments.e3_eval import Case
from waggle.experiments.e3_mcp_layers import LayerOutcome, LayerReport

CATALOG_LAYER = "catalog_check"
# The synthetic catalog of the case setups. Stock is zero so an order is never skipped for stock.
PARTS: tuple[str, ...] = ("BRG-6204", "SEAL-08")
MACHINES: tuple[str, ...] = ("C1", "P1")
# BRG-6204 fits conveyor C1; SEAL-08 fits pump P1 only. The failed asset is conveyor C1.
COMPATIBILITY: tuple[tuple[str, str], ...] = (("C1", "BRG-6204"), ("P1", "SEAL-08"))
FAILED_ASSET = "C1"
_TICKET_KEY = "e3-catalog-c1"
PART_FOR_CASE: Mapping[str, str] = {
    "E3-T3-01": "FREE-KIT-999",
    "E3-T3-02": "SEAL-08",
    "E3-T3-03": "BRG-6204",
}
_REQUESTER = "e3-catalog"


class Orderer(Protocol):
    """The order call of the procurement repository."""

    def order(
        self, key: str, part_number: str, quantity: int, requester: str, ticket_id: str
    ) -> OrderResult:
        """Place an order or raise UnknownPart, UnknownTicket or IncompatiblePart."""


def seed_catalog(
    inventory: InventoryRepository,
    tickets: TicketRepository,
    compatibility: CompatibilityRepository,
) -> str:
    """Load the synthetic catalog and rows, open the ticket for C1, return its id.

    The catalog has no stock. For the E3 run and its tests only.
    """
    for part in PARTS:
        inventory.add_part(part, 0)
    for machine in MACHINES:
        tickets.add_machine(machine)
    for machine, part in COMPATIBILITY:
        compatibility.add(machine, part)
    return tickets.open_ticket(
        _TICKET_KEY, FAILED_ASSET, "E3 catalog check: failed asset", _REQUESTER
    ).ticket_id


def _run(case: Case, part: str, orderer: Orderer, ticket_id: str) -> LayerOutcome:
    if case.label not in ("injection", "benign"):
        raise ValueError(f"{case.id}: only injection and benign cases can be run")
    try:
        result = orderer.order(f"e3-{case.id}", part, 1, _REQUESTER, ticket_id)
        placed, code = result.ordered, None
    except UnknownPart:
        placed, code = False, "unknown_part"
    except IncompatiblePart:
        placed, code = False, "incompatible_part"
    return LayerOutcome(case.id, case.target_layer, case.label, placed, code)


def run_catalog_check(cases: tuple[Case, ...], orderer: Orderer, ticket_id: str) -> LayerReport:
    """Run every reviewed catalog case through ``orderer``, against one ticket, in id order."""
    chosen = sorted((c for c in cases if c.target_layer == CATALOG_LAYER), key=lambda c: c.id)
    missing = [c.id for c in chosen if c.id not in PART_FOR_CASE]
    if missing:
        raise KeyError("no part fixture for: " + ", ".join(missing))
    return LayerReport(tuple(_run(c, PART_FOR_CASE[c.id], orderer, ticket_id) for c in chosen))
