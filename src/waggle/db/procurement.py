"""PostgreSQL simulated purchase orders (ADR-049, T16).

An order is placed only for a catalog part and only when no unit is available, once per failure
event key. The part row is locked first, so concurrent calls with one key place one order.
"""

import re
from dataclasses import dataclass
from typing import Literal, cast

from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict
from waggle.db.inventory import UnknownPart

_PART = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_REQUESTER = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_QUANTITY_MAX = 1000


@dataclass(frozen=True)
class OrderResult:
    """Outcome of one order call. Available stock is a result, not an error."""

    ordered: bool
    reason: Literal["ordered", "replayed", "stock_available"]
    part_number: str
    quantity: int


class ProcurementRepository:
    """Idempotent purchase orders over the spare parts catalog."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def order(self, key: str, part_number: str, quantity: int, requester: str) -> OrderResult:
        """Place the order for a failure event once.

        Raises UnknownPart for a part outside the catalog and IdempotencyConflict when the key
        was used with other values.
        """
        if not isinstance(key, str) or _KEY.fullmatch(key) is None:
            raise ValueError("invalid idempotency key")
        if not isinstance(part_number, str) or _PART.fullmatch(part_number) is None:
            raise ValueError("invalid part number")
        if type(quantity) is not int or not 1 <= quantity <= _QUANTITY_MAX:
            raise ValueError("invalid quantity")
        if not isinstance(requester, str) or _REQUESTER.fullmatch(requester) is None:
            raise ValueError("invalid requester")
        with self._database.transaction() as connection:
            part = connection.execute(
                "SELECT on_hand, reserved FROM spare_parts WHERE part_number=%s FOR UPDATE",
                (part_number,),
            ).fetchone()
            if part is None:
                raise UnknownPart(part_number)
            prior = connection.execute(
                "SELECT part_number, quantity, requester FROM purchase_orders "
                "WHERE idempotency_key=%s",
                (key,),
            ).fetchone()
            if prior is not None:
                if tuple(prior) != (part_number, quantity, requester):
                    raise IdempotencyConflict("idempotency key was used with other values")
                return OrderResult(True, "replayed", part_number, quantity)
            if cast(int, part[0]) - cast(int, part[1]) > 0:
                return OrderResult(False, "stock_available", part_number, quantity)
            connection.execute(
                "INSERT INTO purchase_orders (idempotency_key, part_number, quantity, requester) "
                "VALUES (%s, %s, %s, %s)",
                (key, part_number, quantity, requester),
            )
        return OrderResult(True, "ordered", part_number, quantity)
