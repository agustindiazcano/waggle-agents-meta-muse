"""Trusted shared tick and zone occupancy evidence in PostgreSQL (ADR-041).

Only a trusted writer (the simulator bridge, later odometry) calls ``advance_tick`` and
``record``. Neither is reachable from an MCP tool or a request. The reads implement the
``TickSource`` and ``OccupancySource`` protocols of the forwarder. A missing tick raises and a
zone with no record reads as unknown, so a release or a handoff fails closed.
"""

import re
from typing import cast

from waggle.coordination.corridors import ZoneObservation
from waggle.db.connection import Database

_TICK_MAX = 2**63 - 1
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class UnknownTick(RuntimeError):
    """No trusted tick has been written yet."""


class TickRegression(ValueError):
    """A write tried to move the shared tick backwards."""


def _tick(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _TICK_MAX:
        raise ValueError("tick must be a nonnegative bounded integer")
    return value


class TrustedStateRepository:
    """The shared tick and the latest occupancy record per zone."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def advance_tick(self, tick: int) -> None:
        """Set the shared tick. Equal is a no-op; a lower value raises TickRegression."""
        _tick(tick)
        with self._database.transaction() as connection:
            row = connection.execute(
                "INSERT INTO trusted_tick (singleton, tick) VALUES (true, %s) "
                "ON CONFLICT (singleton) DO UPDATE SET tick=EXCLUDED.tick, "
                "updated_at=clock_timestamp() WHERE trusted_tick.tick <= EXCLUDED.tick "
                "RETURNING tick",
                (tick,),
            ).fetchone()
        if row is None:
            raise TickRegression("tick cannot move backwards")

    def now_tick(self) -> int:
        """The shared tick, or UnknownTick."""
        with self._database.transaction() as connection:
            row = connection.execute("SELECT tick FROM trusted_tick WHERE singleton").fetchone()
        if row is None:
            raise UnknownTick("no trusted tick has been written")
        return cast(int, row[0])

    def record(self, zone_id: str, observed_tick: int, occupants: tuple[str, ...] | None) -> bool:
        """Store the occupancy seen at ``observed_tick``; None means unknown, () means clear.

        Returns False when a newer observation is already stored. An observation later than the
        shared tick is rejected.
        """
        if occupants is not None and not isinstance(occupants, tuple):
            raise ValueError("occupants must be a tuple or None")
        if occupants is not None and not all(
            isinstance(o, str) and _NAME.fullmatch(o) for o in occupants
        ):
            raise ValueError("occupants must be robot ids")
        if not isinstance(zone_id, str) or _NAME.fullmatch(zone_id) is None:
            raise ValueError("invalid zone id")
        _tick(observed_tick)
        checked = ZoneObservation(zone_id, observed_tick, occupants)
        with self._database.transaction() as connection:
            row = connection.execute("SELECT tick FROM trusted_tick WHERE singleton").fetchone()
            if row is None:
                raise UnknownTick("no trusted tick has been written")
            if observed_tick > cast(int, row[0]):
                raise ValueError("observation from the future")
            stored = None if checked.occupants is None else list(checked.occupants)
            written = connection.execute(
                "INSERT INTO zone_occupancy (zone_id, observed_tick, occupants) "
                "VALUES (%s, %s, %s) ON CONFLICT (zone_id) DO UPDATE SET "
                "observed_tick=EXCLUDED.observed_tick, occupants=EXCLUDED.occupants, "
                "recorded_at=clock_timestamp() "
                "WHERE zone_occupancy.observed_tick <= EXCLUDED.observed_tick RETURNING zone_id",
                (zone_id, observed_tick, stored),
            ).fetchone()
        return written is not None

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        """One observation per requested zone, in order. A zone never recorded is unknown."""
        if not zone_ids or len(set(zone_ids)) != len(zone_ids):
            raise ValueError("zone ids must be unique and not empty")
        _tick(now_tick)
        for zone_id in zone_ids:
            ZoneObservation(zone_id, 0, None)
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT zone_id, observed_tick, occupants FROM zone_occupancy "
                "WHERE zone_id = ANY(%s)",
                (list(zone_ids),),
            ).fetchall()
        known = {cast(str, r[0]): (cast(int, r[1]), cast("list[str] | None", r[2])) for r in rows}
        result: list[ZoneObservation] = []
        for zone_id in zone_ids:
            seen = known.get(zone_id)
            if seen is None:
                result.append(ZoneObservation(zone_id, 0, None))
            else:
                result.append(
                    ZoneObservation(zone_id, seen[0], None if seen[1] is None else tuple(seen[1]))
                )
        return tuple(result)
