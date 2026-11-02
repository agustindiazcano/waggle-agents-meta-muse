"""Reservation settlement: a reservation ends consumed or released, once (revision 11).

Both outcomes lock the part row first, then the reservation row, the same order as ``reserve``,
so concurrent calls on one key change stock once. ``reserved <= on_hand`` holds after each: a
consumption lowers both counts, a release lowers only ``reserved``.
"""

import re
from dataclasses import dataclass
from typing import Literal, cast

import psycopg

from waggle.db.connection import Database, Row

_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
Outcome = Literal["consumed", "released"]


class UnknownReservation(LookupError):
    """No reservation has this key."""


class ReservationSettled(ValueError):
    """The reservation already ended the other way."""


@dataclass(frozen=True)
class SettlementResult:
    """The final status and whether this call changed anything. A repeat reports False."""

    status: Outcome
    changed: bool


def _key(value: object) -> str:
    if not isinstance(value, str) or _KEY.fullmatch(value) is None:
        raise ValueError("invalid idempotency key")
    return value


def settle_ticket_reservations(connection: psycopg.Connection[Row], ticket_id: str) -> int:
    """Release every still reserved reservation of a ticket, in the caller's transaction.

    Part rows are locked in sorted order. Returns the number of reservations released.
    """
    parts = connection.execute(
        "SELECT DISTINCT part_number FROM part_reservations "
        "WHERE ticket_id=%s AND status='reserved' ORDER BY part_number",
        (ticket_id,),
    ).fetchall()
    released = 0
    for (part_number,) in parts:
        connection.execute(
            "SELECT 1 FROM spare_parts WHERE part_number=%s FOR UPDATE", (part_number,)
        )
        rows = connection.execute(
            "SELECT idempotency_key, quantity FROM part_reservations "
            "WHERE ticket_id=%s AND part_number=%s AND status='reserved' "
            "ORDER BY idempotency_key FOR UPDATE",
            (ticket_id, part_number),
        ).fetchall()
        for key, quantity in rows:
            _end(
                connection, cast(str, key), cast(str, part_number), cast(int, quantity), "released"
            )
            released += 1
    return released


def _end(
    connection: psycopg.Connection[Row], key: str, part_number: str, quantity: int, status: Outcome
) -> None:
    if status == "consumed":
        connection.execute(
            "UPDATE spare_parts SET on_hand = on_hand - %s, reserved = reserved - %s "
            "WHERE part_number=%s",
            (quantity, quantity, part_number),
        )
    else:
        connection.execute(
            "UPDATE spare_parts SET reserved = reserved - %s WHERE part_number=%s",
            (quantity, part_number),
        )
    connection.execute(
        "UPDATE part_reservations SET status=%s, settled_at=clock_timestamp() "
        "WHERE idempotency_key=%s",
        (status, key),
    )


class SettlementRepository:
    """Consume or release one reservation by its idempotency key."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def consume(self, key: str) -> SettlementResult:
        """Confirm the part was used. Raises UnknownReservation or ReservationSettled."""
        return self._settle(_key(key), "consumed")

    def release(self, key: str) -> SettlementResult:
        """Give the reserved units back. Raises UnknownReservation or ReservationSettled."""
        return self._settle(_key(key), "released")

    def _settle(self, key: str, status: Outcome) -> SettlementResult:
        with self._database.transaction() as connection:
            found = connection.execute(
                "SELECT part_number FROM part_reservations WHERE idempotency_key=%s", (key,)
            ).fetchone()
            if found is None:
                raise UnknownReservation(key)
            part_number = cast(str, found[0])
            connection.execute(
                "SELECT 1 FROM spare_parts WHERE part_number=%s FOR UPDATE", (part_number,)
            )
            row = connection.execute(
                "SELECT quantity, status FROM part_reservations "
                "WHERE idempotency_key=%s FOR UPDATE",
                (key,),
            ).fetchone()
            if row is None:
                raise UnknownReservation(key)
            if row[1] == status:
                return SettlementResult(status, False)
            if row[1] != "reserved":
                raise ReservationSettled(key)
            _end(connection, key, part_number, cast(int, row[0]), status)
        return SettlementResult(status, True)
