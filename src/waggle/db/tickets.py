"""PostgreSQL machines and maintenance tickets (ADR-049).

A ticket id is derived from the failure event key, so one event opens at most one ticket (T9).
A machine outside ``machines`` and a zone outside ``zones`` do not exist for these calls. The
summary is untrusted text: it is stored bounded and never returned or logged here.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import cast

from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_SUMMARY_MAX = 500


class UnknownMachine(LookupError):
    """The machine id is not in the catalog."""


class UnknownTicket(LookupError):
    """No ticket has this id."""


class UnknownZone(LookupError):
    """The zone is not registered."""


@dataclass(frozen=True)
class TicketResult:
    """The ticket id and whether this call changed anything. A repeat reports False."""

    ticket_id: str
    created: bool


def ticket_id_for(key: str) -> str:
    """The ticket id for a failure event key."""
    return "tkt-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _id(value: object, what: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"invalid {what}")
    return value


def _key(value: object) -> str:
    if not isinstance(value, str) or _KEY.fullmatch(value) is None:
        raise ValueError("invalid idempotency key")
    return value


def _summary(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= _SUMMARY_MAX or not value.isprintable():
        raise ValueError("invalid summary")
    return value


class TicketRepository:
    """Machine catalog, idempotent ticket opening and dispatch."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add_machine(self, machine_id: str) -> None:
        """Add a catalog machine. Used by load scripts and tests, never by a tool."""
        _id(machine_id, "machine id")
        with self._database.transaction() as connection:
            connection.execute("INSERT INTO machines (machine_id) VALUES (%s)", (machine_id,))

    def open_ticket(self, key: str, machine_id: str, summary: str, opener: str) -> TicketResult:
        """Open the ticket for a failure event once.

        Raises UnknownMachine, or IdempotencyConflict when the key was used with other values.
        """
        _key(key)
        _id(machine_id, "machine id")
        _summary(summary)
        _id(opener, "opener")
        ticket_id = ticket_id_for(key)
        with self._database.transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM machines WHERE machine_id=%s", (machine_id,)
                ).fetchone()
                is None
            ):
                raise UnknownMachine(machine_id)
            inserted = connection.execute(
                "INSERT INTO maintenance_tickets "
                "(ticket_id, idempotency_key, machine_id, summary, opened_by) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (ticket_id) DO NOTHING "
                "RETURNING ticket_id",
                (ticket_id, key, machine_id, summary, opener),
            ).fetchone()
            if inserted is not None:
                return TicketResult(ticket_id, True)
            prior = connection.execute(
                "SELECT idempotency_key, machine_id, summary, opened_by "
                "FROM maintenance_tickets WHERE ticket_id=%s",
                (ticket_id,),
            ).fetchone()
        if prior is None or tuple(prior) != (key, machine_id, summary, opener):
            raise IdempotencyConflict("idempotency key was used with other values")
        return TicketResult(ticket_id, False)

    def dispatch(self, ticket_id: str, zone_id: str, dispatcher: str) -> TicketResult:
        """Send a technician to a zone for an open ticket, once.

        Raises UnknownTicket or UnknownZone, or IdempotencyConflict for a second, different zone.
        """
        _id(ticket_id, "ticket id")
        _id(zone_id, "zone id")
        _id(dispatcher, "dispatcher")
        with self._database.transaction() as connection:
            ticket = connection.execute(
                "SELECT status, zone_id FROM maintenance_tickets WHERE ticket_id=%s FOR UPDATE",
                (ticket_id,),
            ).fetchone()
            if ticket is None:
                raise UnknownTicket(ticket_id)
            if cast(str, ticket[0]) == "dispatched":
                if ticket[1] != zone_id:
                    raise IdempotencyConflict("ticket was dispatched to another zone")
                return TicketResult(ticket_id, False)
            if (
                connection.execute("SELECT 1 FROM zones WHERE zone_id=%s", (zone_id,)).fetchone()
                is None
            ):
                raise UnknownZone(zone_id)
            connection.execute(
                "UPDATE maintenance_tickets SET status='dispatched', zone_id=%s, "
                "dispatched_by=%s WHERE ticket_id=%s",
                (zone_id, dispatcher, ticket_id),
            )
        return TicketResult(ticket_id, True)
