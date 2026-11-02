"""Seed a machine, an open ticket and compatibility rows for database tests."""

from collections.abc import Iterable

from waggle.db.compatibility import CompatibilityRepository
from waggle.db.connection import Database
from waggle.db.tickets import TicketRepository


def seed_ticket(
    database: Database,
    machine_id: str = "M-1",
    fits: Iterable[str] = ("P-100",),
    key: str = "tkt-evt-1",
    *,
    create_machine: bool = True,
) -> str:
    """Open a ticket for the machine and mark the listed parts as fitting it.

    The parts must already be in the catalog. Returns the ticket id.
    """
    tickets = TicketRepository(database)
    if create_machine:
        tickets.add_machine(machine_id)
    ticket = tickets.open_ticket(key, machine_id, "seeded for a test", "tech-0")
    compatibility = CompatibilityRepository(database)
    for part_number in fits:
        compatibility.add(machine_id, part_number)
    return ticket.ticket_id
