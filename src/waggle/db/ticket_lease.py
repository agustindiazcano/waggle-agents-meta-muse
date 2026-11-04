"""Technician zone lease at dispatch, ticket close and lease expiry (revision 11).

Lock order in every call is the ticket row, then the zone rows, then part rows. A dispatch is
granted only if the zone lease for the named technician is granted in the same transaction, so a
dispatch cannot succeed with the zone unprotected. A denial changes no ticket and no stock, but
the zone transitions the pure model produced (an expiry) are kept, as in ``CorridorRepository``.
"""

import re
from dataclasses import dataclass
from typing import cast

from waggle.coordination.corridors import (
    CorridorReason,
    CorridorRequest,
    Direction,
    ZoneObservation,
    ZoneToken,
    expire_corridors,
    release_corridor,
    request_corridor,
)
from waggle.coordination.leases import DEFAULT_LEASE_TICKS, check_token
from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict, lock_zones, write_zones
from waggle.db.settlement import settle_ticket_reservations
from waggle.db.tickets import UnknownTicket, UnknownZone

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")


@dataclass(frozen=True)
class DispatchOutcome:
    """Whether the technician now holds the zone for the ticket, and this call's effect."""

    dispatched: bool
    created: bool
    reason: str
    token: int | None


@dataclass(frozen=True)
class CloseOutcome:
    """Whether the ticket is closed, and whether this call closed it."""

    closed: bool
    created: bool
    reason: str


def _id(value: object, what: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"invalid {what}")
    return value


def _tick(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("invalid tick")
    return value


class TicketLeaseRepository:
    """Dispatch with a zone lease, close with a fenced release, and reopen on expiry."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def dispatch(
        self,
        ticket_id: str,
        zone_id: str,
        dispatcher: str,
        technician: str,
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
        lease_ticks: int = DEFAULT_LEASE_TICKS,
    ) -> DispatchOutcome:
        """Send ``technician`` to a zone, holding the zone lease for them, once.

        Raises UnknownTicket (missing or closed) or UnknownZone, and IdempotencyConflict when the
        ticket is already dispatched to another zone or technician. A zone held elsewhere, an
        occupied or unknown zone, or a zone already leased for another ticket is a result with
        ``dispatched`` False and the ticket left open.
        """
        _id(ticket_id, "ticket id")
        _id(zone_id, "zone id")
        _id(dispatcher, "dispatcher")
        _id(technician, "technician")
        _tick(now_tick)
        if type(lease_ticks) is not int or lease_ticks < 1:
            raise ValueError("invalid lease ticks")
        request = CorridorRequest(technician, (zone_id,), Direction.FORWARD)
        with self._database.transaction() as connection:
            ticket = connection.execute(
                "SELECT status, zone_id, technician, zone_token FROM maintenance_tickets "
                "WHERE ticket_id=%s FOR UPDATE",
                (ticket_id,),
            ).fetchone()
            if ticket is None or ticket[0] == "closed":
                raise UnknownTicket(ticket_id)
            if ticket[0] == "dispatched":
                if (ticket[1], ticket[2]) != (zone_id, technician):
                    raise IdempotencyConflict("ticket was dispatched to another zone or technician")
                return DispatchOutcome(True, False, "already_dispatched", cast(int, ticket[3]))
            if (
                connection.execute("SELECT 1 FROM zones WHERE zone_id=%s", (zone_id,)).fetchone()
                is None
            ):
                raise UnknownZone(zone_id)
            state = lock_zones(connection, technician)
            zone = next(z for z in state.zones if z.lease.resource_id == zone_id)
            # One lease belongs to one ticket. A dispatched ticket whose lease already ended is
            # stale: it does not block, and the sweeper reopens it.
            others = connection.execute(
                "SELECT technician, zone_token FROM maintenance_tickets "
                "WHERE zone_id=%s AND status='dispatched' AND technician IS NOT NULL "
                "AND ticket_id<>%s",
                (zone_id, ticket_id),
            ).fetchall()
            if any(
                check_token(zone.lease, cast(str, who), cast(int, held), now_tick)
                for who, held in others
            ):
                return DispatchOutcome(False, False, "zone_in_use", None)
            result = request_corridor(state, request, now_tick, observations, lease_ticks)
            write_zones(connection, result.state)
            if not result.granted:
                return DispatchOutcome(False, False, result.reason.value, None)
            if result.reason is CorridorReason.ALREADY_HELD:
                # The technician holds a lease this ticket did not take, so it is not this
                # ticket's to fence with. The write above only retained expiries.
                return DispatchOutcome(False, False, "zone_in_use", None)
            token = result.tokens[0].token
            connection.execute(
                "UPDATE maintenance_tickets SET status='dispatched', zone_id=%s, "
                "dispatched_by=%s, technician=%s, zone_token=%s WHERE ticket_id=%s",
                (zone_id, dispatcher, technician, token, ticket_id),
            )
        return DispatchOutcome(True, True, result.reason.value, token)

    def close(
        self,
        ticket_id: str,
        closer: str,
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
    ) -> CloseOutcome:
        """Close a dispatched ticket: release its lease and settle its reservations, together.

        The lease is released with the token stored at dispatch, so a technician whose lease
        expired cannot close. The release needs clear trusted occupancy, so an occupied or unknown
        zone denies the close. A denial changes no ticket and no stock. A repeat of a close
        reports ``created`` False. Raises UnknownTicket for a missing, open or lease-less ticket.
        """
        _id(ticket_id, "ticket id")
        _id(closer, "closer")
        _tick(now_tick)
        with self._database.transaction() as connection:
            ticket = connection.execute(
                "SELECT status, zone_id, technician, zone_token FROM maintenance_tickets "
                "WHERE ticket_id=%s FOR UPDATE",
                (ticket_id,),
            ).fetchone()
            if ticket is None or ticket[0] == "open":
                raise UnknownTicket(ticket_id)
            if ticket[0] == "closed":
                return CloseOutcome(True, False, "already_closed")
            if ticket[2] is None or ticket[3] is None:
                raise UnknownTicket(ticket_id)
            zone_id, technician, token = cast(str, ticket[1]), cast(str, ticket[2]), ticket[3]
            state = lock_zones(connection, technician)
            result = release_corridor(
                state, technician, (ZoneToken(zone_id, cast(int, token)),), now_tick, observations
            )
            write_zones(connection, result.state)
            if not result.granted:
                return CloseOutcome(False, False, result.reason.value)
            settle_ticket_reservations(connection, ticket_id)
            connection.execute(
                "UPDATE maintenance_tickets SET status='closed', closed_at=clock_timestamp() "
                "WHERE ticket_id=%s",
                (ticket_id,),
            )
        return CloseOutcome(True, True, result.reason.value)

    def zone_of(self, ticket_id: str) -> str | None:
        """The zone a ticket was dispatched to, or None for a missing or undispatched ticket.

        Read only, to choose which zone to observe before a close. The close itself locks the
        ticket and trusts the stored zone, so a stale answer here only makes the close deny.
        """
        _id(ticket_id, "ticket id")
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT zone_id FROM maintenance_tickets "
                "WHERE ticket_id=%s AND status='dispatched'",
                (ticket_id,),
            ).fetchone()
        return None if row is None else cast(str | None, row[0])

    def reopen_expired(
        self, now_tick: int, observations: tuple[ZoneObservation, ...]
    ) -> tuple[str, ...]:
        """Reopen dispatched tickets whose lease ended, freeing their zones. Returns the ids.

        A zone whose lease expired while occupied or unobserved stays faulted and its ticket stays
        dispatched, so the zone is never reported free without evidence. Rows locked by another
        sweeper are skipped. Reservations are not touched: the ticket is still the same failure.
        """
        _tick(now_tick)
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT ticket_id, zone_id, technician, zone_token FROM maintenance_tickets "
                "WHERE status='dispatched' AND technician IS NOT NULL "
                "ORDER BY ticket_id FOR UPDATE SKIP LOCKED"
            ).fetchall()
            if not rows:
                return ()
            state = expire_corridors(lock_zones(connection, "sweeper"), now_tick, observations)
            write_zones(connection, state)
            zones = {zone.lease.resource_id: zone for zone in state.zones}
            reopened: list[str] = []
            for ticket_id, zone_id, technician, token in rows:
                zone = zones[cast(str, zone_id)]
                if zone.fault_occupied or check_token(
                    zone.lease, cast(str, technician), cast(int, token), now_tick
                ):
                    continue
                connection.execute(
                    "UPDATE maintenance_tickets SET status='open', zone_id=NULL, "
                    "dispatched_by=NULL, technician=NULL, zone_token=NULL WHERE ticket_id=%s",
                    (ticket_id,),
                )
                reopened.append(cast(str, ticket_id))
        return tuple(reopened)
