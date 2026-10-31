"""Cloud-only trusted tick and occupancy checks against PostgreSQL."""

import psycopg
import pytest

from waggle.coordination.corridors import CorridorRequest, Direction, ZoneObservation
from waggle.coordination.task_model import TaskRecord
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.occupancy import TickRegression, TrustedStateRepository, UnknownTick
from waggle.mcp_server.forwarder import FencedForwarder
from waggle.mcp_server.identity import Identity

pytestmark = pytest.mark.heavy


class NoTasks:
    def get(self, task_id: str) -> TaskRecord | None:
        return None


def test_tick_is_missing_until_a_trusted_writer_sets_it(database: Database) -> None:
    with pytest.raises(UnknownTick):
        TrustedStateRepository(database).now_tick()


def test_tick_only_moves_forward(database: Database) -> None:
    state = TrustedStateRepository(database)
    state.advance_tick(5)
    state.advance_tick(5)
    state.advance_tick(9)
    assert state.now_tick() == 9
    with pytest.raises(TickRegression):
        state.advance_tick(8)
    assert state.now_tick() == 9


def test_recorded_occupancy_round_trips_clear_occupied_and_unknown(database: Database) -> None:
    CorridorRepository(database).register(("a", "b", "c", "d"))
    state = TrustedStateRepository(database)
    state.advance_tick(10)
    assert state.record("a", 10, ())
    assert state.record("b", 10, ("robot-1", "robot-0"))
    assert state.record("c", 10, None)
    seen = state.observe(("a", "b", "c", "d"), 10)
    assert seen == (
        ZoneObservation("a", 10, ()),
        ZoneObservation("b", 10, ("robot-0", "robot-1")),
        ZoneObservation("c", 10, None),
        ZoneObservation("d", 0, None),
    )


def test_an_older_observation_never_replaces_a_newer_one(database: Database) -> None:
    CorridorRepository(database).register(("a",))
    state = TrustedStateRepository(database)
    state.advance_tick(10)
    assert state.record("a", 9, ("robot-0",))
    assert state.record("a", 10, ())
    assert not state.record("a", 9, ("robot-0",))
    assert state.observe(("a",), 10) == (ZoneObservation("a", 10, ()),)


def test_an_observation_from_the_future_is_rejected(database: Database) -> None:
    CorridorRepository(database).register(("a",))
    state = TrustedStateRepository(database)
    state.advance_tick(10)
    with pytest.raises(ValueError, match="future"):
        state.record("a", 11, ())
    assert state.observe(("a",), 10) == (ZoneObservation("a", 0, None),)


def test_an_observation_before_any_tick_is_rejected(database: Database) -> None:
    CorridorRepository(database).register(("a",))
    with pytest.raises(UnknownTick):
        TrustedStateRepository(database).record("a", 0, ())


def test_an_unregistered_zone_cannot_be_observed(database: Database) -> None:
    state = TrustedStateRepository(database)
    state.advance_tick(1)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        state.record("ghost", 1, ())


def _forwarder(database: Database) -> FencedForwarder:
    state = TrustedStateRepository(database)
    return FencedForwarder(CorridorRepository(database), NoTasks(), state, state)


def _grant(database: Database) -> int:
    corridors = CorridorRepository(database)
    corridors.register(("dock",))
    state = TrustedStateRepository(database)
    state.advance_tick(1)
    state.record("dock", 1, ())
    granted = corridors.reserve(
        CorridorRequest("robot-0", ("dock",), Direction.FORWARD),
        1,
        state.observe(("dock",), 1),
    )
    assert granted.granted
    return granted.tokens[0].token


def test_release_zone_through_real_trusted_sources_releases_a_clear_zone(
    database: Database,
) -> None:
    token = _grant(database)
    result = _forwarder(database).forward(
        Identity("carrier", "robot-0"), "release_zone", {"zone_id": "dock", "token": token}, 1.0
    )
    assert result == {"released": True, "reason": "released"}


def test_release_zone_is_refused_while_the_trusted_record_says_occupied(
    database: Database,
) -> None:
    token = _grant(database)
    TrustedStateRepository(database).record("dock", 1, ("robot-0",))
    result = _forwarder(database).forward(
        Identity("carrier", "robot-0"), "release_zone", {"zone_id": "dock", "token": token}, 1.0
    )
    assert result["released"] is False


def test_release_zone_is_refused_when_occupancy_is_unknown(database: Database) -> None:
    token = _grant(database)
    TrustedStateRepository(database).record("dock", 1, None)
    result = _forwarder(database).forward(
        Identity("carrier", "robot-0"), "release_zone", {"zone_id": "dock", "token": token}, 1.0
    )
    assert result["released"] is False
