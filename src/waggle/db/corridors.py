"""Persistent corridor transitions and a transactionally fenced event effect.

All zone rows are locked in canonical order to preserve the pure model's whole
state transition. This deliberately coarse first implementation makes no fleet
throughput claim. It does not authenticate identities or dispatch robot tools.
"""

import json
from dataclasses import dataclass
from typing import cast

import psycopg

from waggle.coordination.corridors import (
    CorridorRequest,
    CorridorResult,
    CorridorState,
    CorridorZone,
    Direction,
    ZoneObservation,
    ZoneToken,
    expire_corridors,
    release_corridor,
    request_corridor,
)
from waggle.coordination.leases import DEFAULT_LEASE_TICKS, LeaseState, check_token
from waggle.db.connection import Database, Row

_REGISTRY_LOCK = 19730402
_HOLDER_SEED = 19730403


class IdempotencyConflict(ValueError):
    """An event id was reused with a different holder, credential or event kind."""


@dataclass(frozen=True)
class FencedEventResult:
    """An inserted effect or historical replay; a denial creates no event."""

    accepted: bool
    replayed: bool = False


def _read(connection: psycopg.Connection[Row], *, lock: bool = False) -> CorridorState:
    if lock:
        rows = connection.execute(
            "SELECT zone_id, holder, token, expires_tick, observed_tick, direction, fault_occupied "
            "FROM zones ORDER BY zone_id FOR UPDATE"
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT zone_id, holder, token, expires_tick, observed_tick, direction, fault_occupied "
            "FROM zones ORDER BY zone_id"
        ).fetchall()
    # PostgreSQL column types and constraints establish the row types below.
    return CorridorState(
        tuple(
            CorridorZone(
                LeaseState(
                    resource_id=cast(str, row[0]),
                    holder=cast(str | None, row[1]),
                    token=cast(int, row[2]),
                    expires_tick=cast(int | None, row[3]),
                    observed_tick=cast(int, row[4]),
                ),
                Direction(cast(str, row[5])) if row[5] is not None else None,
                cast(bool, row[6]),
            )
            for row in rows
        )
    )


def _write(connection: psycopg.Connection[Row], state: CorridorState) -> None:
    for zone in state.zones:
        lease = zone.lease
        connection.execute(
            "UPDATE zones SET holder=%s, token=%s, expires_tick=%s, observed_tick=%s, "
            "direction=%s, fault_occupied=%s WHERE zone_id=%s",
            (
                lease.holder,
                lease.token,
                lease.expires_tick,
                lease.observed_tick,
                zone.direction.value if zone.direction is not None else None,
                zone.fault_occupied,
                lease.resource_id,
            ),
        )


def _lock(connection: psycopg.Connection[Row], holder: str | None = None) -> CorridorState:
    # Shared topology lock prevents resource insertion during a complete transition.
    connection.execute("SELECT pg_advisory_xact_lock_shared(%s)", (_REGISTRY_LOCK,))
    if holder is not None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, %s))", (holder, _HOLDER_SEED)
        )
    return _read(connection, lock=True)


def _event_name(value: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or not value.isascii()
        or any(not (char.isalnum() or char in "_-.:/") for char in value)
    ):
        raise ValueError("invalid event identifier")


class CorridorRepository:
    """Apply the pure corridor model under PostgreSQL locks and durable counters."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def register(self, resources: tuple[str, ...]) -> None:
        """Provision named resources separately from migrations without resetting tokens."""
        if not resources:
            raise ValueError("resources must not be empty")
        initial = CorridorState(tuple(CorridorZone(LeaseState(name)) for name in resources))
        with self.database.transaction() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (_REGISTRY_LOCK,))
            for zone in initial.zones:
                connection.execute(
                    "INSERT INTO zones (zone_id) VALUES (%s) ON CONFLICT (zone_id) DO NOTHING",
                    (zone.lease.resource_id,),
                )

    def snapshot(self) -> CorridorState:
        """Read one committed resource snapshot without treating it as authorization."""
        with self.database.transaction() as connection:
            return _read(connection)

    def reserve(
        self,
        request: CorridorRequest,
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
        lease_ticks: int = DEFAULT_LEASE_TICKS,
    ) -> CorridorResult:
        """Reserve the complete bundle atomically, retaining transitions on a denial."""
        with self.database.transaction() as connection:
            state = _lock(connection, request.holder)
            result = request_corridor(state, request, now_tick, observations, lease_ticks)
            _write(connection, result.state)
            return result

    def release(
        self,
        holder: str,
        tokens: tuple[ZoneToken, ...],
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
    ) -> CorridorResult:
        """Release only a complete live bundle with current empty occupancy evidence."""
        with self.database.transaction() as connection:
            state = _lock(connection, holder)
            result = release_corridor(state, holder, tokens, now_tick, observations)
            _write(connection, result.state)
            return result

    def expire(self, now_tick: int, observations: tuple[ZoneObservation, ...]) -> CorridorState:
        """Persist occupied expiry faults rather than assume timer expiry means clearance."""
        with self.database.transaction() as connection:
            state = expire_corridors(_lock(connection), now_tick, observations)
            _write(connection, state)
            return state

    def record_event(
        self,
        event_id: str,
        holder: str,
        tokens: tuple[ZoneToken, ...],
        now_tick: int,
        event_kind: str,
    ) -> FencedEventResult:
        """Check live tokens and insert one event inside the same locked transaction.

        A matching repeat returns its historical result without inserting another
        event, even after expiry. This event insert is the only protected effect;
        a future robot tool must perform its own effect within its locked check.
        """
        for name in (event_id, holder, event_kind):
            _event_name(name)
        if type(now_tick) is not int or now_tick < 0:
            raise ValueError("now_tick must be a nonnegative integer")
        if not tokens:
            return FencedEventResult(False)
        supplied = {token.resource_id: token.token for token in tokens}
        if len(supplied) != len(tokens):
            return FencedEventResult(False)
        credentials = json.dumps(sorted(supplied.items()), separators=(",", ":"))
        with self.database.transaction() as connection:
            state = _lock(connection, holder)
            row = connection.execute(
                "SELECT holder, credentials, event_kind FROM fenced_events WHERE event_id=%s",
                (event_id,),
            ).fetchone()
            if row is not None:
                if row != (holder, credentials, event_kind):
                    raise IdempotencyConflict("event id has different content")
                return FencedEventResult(True, replayed=True)
            owned = {zone.lease.resource_id for zone in state.zones if zone.lease.holder == holder}
            if owned != set(supplied):
                return FencedEventResult(False)
            if any(
                zone.fault_occupied
                or now_tick < zone.lease.observed_tick
                or not check_token(zone.lease, holder, supplied[zone.lease.resource_id], now_tick)
                for zone in state.zones
                if zone.lease.resource_id in supplied
            ):
                return FencedEventResult(False)
            connection.execute(
                "INSERT INTO fenced_events "
                "(event_id, holder, credentials, event_kind, executed_tick) "
                "VALUES (%s,%s,%s,%s,%s)",
                (event_id, holder, credentials, event_kind, now_tick),
            )
            return FencedEventResult(True)
