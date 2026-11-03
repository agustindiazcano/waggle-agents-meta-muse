"""The manual sheet: a strict, validated record per machine (design section 6, step 5).

A sheet is data, never a source of authority. It lists, per failure mode, the part number and
quantity to use, and the zone where a technician is sent. Unknown fields are rejected, ids and
numbers are bounded, and free text (``notes``) is stored bounded and printable and is never read
by any decision. A missing sheet becomes the conservative default: no part is listed, so the
loop escalates instead of inventing one. A part is converted to a ``PartPlan`` only when it is
in the caller's catalog.
"""

import re
from collections.abc import Mapping, Set
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from waggle.experiments.failure_log import FailureMode
from waggle.maintenance.loop import PartPlan

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_QUANTITY_MAX = 1000
_NOTES_MAX = 500
_SHEET_KEYS = frozenset({"machine_id", "zone_id", "parts", "notes"})
_REQUIRED_KEYS = frozenset({"machine_id", "zone_id", "parts"})
_PART_KEYS = frozenset({"part_number", "quantity"})
_DEFAULT_ZONE = "zone-unset"


class SheetError(ValueError):
    """The sheet is malformed. The message names the field, never the offending value."""


@dataclass(frozen=True)
class SheetPart:
    """One part line: what to use for a mode."""

    part_number: str
    quantity: int


@dataclass(frozen=True)
class ManualSheet:
    """Validated sheet. ``parts`` maps a failure mode to a part line."""

    machine_id: str
    zone_id: str
    parts: Mapping[FailureMode, SheetPart] = field(default_factory=lambda: MappingProxyType({}))
    notes: str = ""

    def plan_for(self, mode: FailureMode | str, catalog: Set[str]) -> PartPlan | None:
        """The plan for a mode, or None when the sheet has no part or it is not in the catalog.

        Raises ValueError for an unknown mode. None means escalate: nothing is invented.
        """
        try:
            wanted = FailureMode(mode)
        except ValueError:
            raise ValueError("Invalid mode") from None
        line = self.parts.get(wanted)
        if line is None or line.part_number not in catalog:
            return None
        return PartPlan(line.part_number, line.quantity, self.zone_id)


def default_sheet(machine_id: str) -> ManualSheet:
    """The conservative default: no part for any mode, so every event escalates."""
    if not isinstance(machine_id, str) or _ID.fullmatch(machine_id) is None:
        raise SheetError("invalid machine_id")
    return ManualSheet(machine_id, _DEFAULT_ZONE)


def _ident(value: object, name: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise SheetError(f"invalid {name}")
    return value


def _part(raw: object) -> SheetPart:
    if not isinstance(raw, Mapping) or set(raw) != _PART_KEYS:
        raise SheetError("invalid part line")
    quantity = raw["quantity"]
    if type(quantity) is not int or not 1 <= quantity <= _QUANTITY_MAX:
        raise SheetError("invalid quantity")
    return SheetPart(_ident(raw["part_number"], "part_number"), quantity)


def _notes(raw: object) -> str:
    if not isinstance(raw, str) or len(raw) > _NOTES_MAX or not raw.isprintable():
        raise SheetError("invalid notes")
    return raw


def load_sheet(raw: Mapping[str, Any] | None, machine_id: str | None = None) -> ManualSheet:
    """Validate a JSON mapping into a sheet. ``None`` yields the default for ``machine_id``."""
    if raw is None:
        if machine_id is None:
            raise SheetError("a missing sheet needs a machine_id")
        return default_sheet(machine_id)
    if not isinstance(raw, Mapping):
        raise SheetError("sheet must be a mapping")
    keys = set(raw)
    if not keys >= _REQUIRED_KEYS or not keys <= _SHEET_KEYS:
        raise SheetError("unexpected or missing sheet fields")
    parts_raw = raw["parts"]
    if not isinstance(parts_raw, Mapping):
        raise SheetError("parts must be a mapping")
    parts: dict[FailureMode, SheetPart] = {}
    for key, line in parts_raw.items():
        try:
            mode = FailureMode(key)
        except ValueError:
            raise SheetError("unknown failure mode") from None
        parts[mode] = _part(line)
    return ManualSheet(
        _ident(raw["machine_id"], "machine_id"),
        _ident(raw["zone_id"], "zone_id"),
        MappingProxyType(parts),
        _notes(raw["notes"]) if "notes" in raw else "",
    )
