"""Machine to part compatibility (ADR-063).

A part fits a machine only when a ``part_compatibility`` row says so; no row means incompatible,
so the check fails closed. The machine is never an argument: it is read from the ticket row, in
the transaction that already holds the part row lock. Only load scripts write the table.
"""

import re
from typing import cast

import psycopg

from waggle.db.connection import Database, Row
from waggle.db.tickets import UnknownTicket

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_LIVE_STATUSES = frozenset({"open", "dispatched"})


class IncompatiblePart(LookupError):
    """The part has no compatibility row for the machine of the ticket."""


def _id(value: object, what: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"invalid {what}")
    return value


def require_compatible(
    connection: psycopg.Connection[Row], ticket_id: str, part_number: str
) -> None:
    """Check, inside the caller's transaction, that the part fits the machine of the ticket.

    Raises UnknownTicket when the ticket does not exist, is not open or dispatched, or has no
    machine, and IncompatiblePart when the pair has no row.
    """
    ticket = connection.execute(
        "SELECT status, machine_id FROM maintenance_tickets WHERE ticket_id=%s", (ticket_id,)
    ).fetchone()
    if ticket is None or ticket[0] not in _LIVE_STATUSES or not isinstance(ticket[1], str):
        raise UnknownTicket(ticket_id)
    pair = connection.execute(
        "SELECT 1 FROM part_compatibility WHERE machine_id=%s AND part_number=%s",
        (ticket[1], part_number),
    ).fetchone()
    if pair is None:
        raise IncompatiblePart(part_number)


class CompatibilityRepository:
    """Compatibility rows for load scripts and tests, never for a tool."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, machine_id: str, part_number: str) -> None:
        """Add one row. A repeat raises psycopg UniqueViolation; unknown ids raise a foreign key
        violation."""
        _id(machine_id, "machine id")
        _id(part_number, "part number")
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO part_compatibility (machine_id, part_number) VALUES (%s, %s)",
                (machine_id, part_number),
            )

    def exists(self, machine_id: str, part_number: str) -> bool:
        """Whether the pair has a row."""
        _id(machine_id, "machine id")
        _id(part_number, "part number")
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM part_compatibility WHERE machine_id=%s AND part_number=%s",
                (machine_id, part_number),
            ).fetchone()
        return row is not None

    def count(self) -> int:
        """The number of rows."""
        with self._database.transaction() as connection:
            row = connection.execute("SELECT count(*) FROM part_compatibility").fetchone()
        # count(*) always returns one integer row.
        return cast(int, row[0]) if row is not None else 0
