"""PostgreSQL spare parts catalog and reservations (ADR-048).

The catalog is the table: a part number that is not in ``spare_parts`` does not exist, so no
text from a manual or a model can create one. Reservations lock the part row first, then look
up the idempotency key, so concurrent calls with one key reserve once and stock never goes
below zero.
"""

import re
from dataclasses import dataclass
from typing import Literal, cast

from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict

_PART = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_HOLDER = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_QUANTITY_MAX = 1000
_STOCK_MAX = 1_000_000


class UnknownPart(LookupError):
    """The part number is not in the catalog."""


@dataclass(frozen=True)
class PartStock:
    """Counts for one catalog part."""

    part_number: str
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        """Units not yet reserved."""
        return self.on_hand - self.reserved


@dataclass(frozen=True)
class ReservationResult:
    """Outcome of one reservation call. A shortage is a result, not an error."""

    granted: bool
    reason: Literal["reserved", "replayed", "insufficient_stock"]
    part_number: str
    quantity: int


def _part(value: object) -> str:
    if not isinstance(value, str) or _PART.fullmatch(value) is None:
        raise ValueError("invalid part number")
    return value


def _bounded(value: object, low: int, high: int, what: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {what}")
    return value


def _text(pattern: re.Pattern[str], value: object, what: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"invalid {what}")
    return value


class InventoryRepository:
    """Catalog reads, catalog loading for scripts, and idempotent reservations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add_part(self, part_number: str, on_hand: int) -> None:
        """Add a catalog part. Used by load scripts and tests, never by a tool."""
        _part(part_number)
        _bounded(on_hand, 0, _STOCK_MAX, "stock")
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO spare_parts (part_number, on_hand) VALUES (%s, %s)",
                (part_number, on_hand),
            )

    def get(self, part_number: str) -> PartStock | None:
        """The counts for a catalog part, or None when it is not in the catalog."""
        _part(part_number)
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT part_number, on_hand, reserved FROM spare_parts WHERE part_number=%s",
                (part_number,),
            ).fetchone()
        if row is None:
            return None
        # Column types and constraints fix the row types.
        return PartStock(cast(str, row[0]), cast(int, row[1]), cast(int, row[2]))

    def reserve(self, key: str, part_number: str, quantity: int, holder: str) -> ReservationResult:
        """Reserve stock once per key.

        Raises UnknownPart for a part outside the catalog and IdempotencyConflict when the key
        was used with other values.
        """
        _text(_KEY, key, "idempotency key")
        _part(part_number)
        _bounded(quantity, 1, _QUANTITY_MAX, "quantity")
        _text(_HOLDER, holder, "holder")
        with self._database.transaction() as connection:
            part = connection.execute(
                "SELECT on_hand, reserved FROM spare_parts WHERE part_number=%s FOR UPDATE",
                (part_number,),
            ).fetchone()
            if part is None:
                raise UnknownPart(part_number)
            prior = connection.execute(
                "SELECT part_number, quantity, holder FROM part_reservations "
                "WHERE idempotency_key=%s",
                (key,),
            ).fetchone()
            if prior is not None:
                if tuple(prior) != (part_number, quantity, holder):
                    raise IdempotencyConflict("idempotency key was used with other values")
                return ReservationResult(True, "replayed", part_number, quantity)
            if cast(int, part[0]) - cast(int, part[1]) < quantity:
                return ReservationResult(False, "insufficient_stock", part_number, quantity)
            connection.execute(
                "UPDATE spare_parts SET reserved = reserved + %s WHERE part_number=%s",
                (quantity, part_number),
            )
            connection.execute(
                "INSERT INTO part_reservations (idempotency_key, part_number, quantity, holder) "
                "VALUES (%s, %s, %s, %s)",
                (key, part_number, quantity, holder),
            )
        return ReservationResult(True, "reserved", part_number, quantity)
