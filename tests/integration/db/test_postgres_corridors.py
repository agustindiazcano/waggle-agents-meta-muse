"""Cloud-only PostgreSQL migration, concurrency, persistence and fencing tests."""

import time
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from postgres_support import isolated_database

from waggle.coordination.corridors import (
    CorridorRequest,
    CorridorState,
    CorridorZone,
    Direction,
    ZoneObservation,
    ZoneToken,
    expire_corridors,
    release_corridor,
    request_corridor,
)
from waggle.coordination.leases import LeaseState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository, IdempotencyConflict
from waggle.db.schema import LATEST_REVISION, SchemaVersionError, current_revision, migrate

pytestmark = pytest.mark.heavy


def _empty(tick: int) -> tuple[ZoneObservation, ...]:
    return (ZoneObservation("a", tick, ()), ZoneObservation("b", tick, ()))


def test_migration_checks_revision_and_never_silently_adopts_an_unknown_version() -> None:
    with isolated_database() as db:
        assert current_revision(db) == 0
        assert migrate(db, expected_revision=0) == LATEST_REVISION
        assert current_revision(db) == LATEST_REVISION
        assert migrate(db, expected_revision=LATEST_REVISION) == LATEST_REVISION
        with pytest.raises(SchemaVersionError):
            migrate(db, expected_revision=0)
        with db.transaction() as connection:
            connection.execute("UPDATE waggle_schema SET revision = 99")
        with pytest.raises(SchemaVersionError):
            migrate(db, expected_revision=99)


def test_failed_migration_leaves_no_partial_schema_or_revision() -> None:
    with isolated_database() as db:
        with db.transaction() as connection:
            connection.execute("CREATE TABLE zones (existing integer)")
        with pytest.raises(psycopg.errors.DuplicateTable):
            migrate(db, expected_revision=0)
        assert current_revision(db) == 0
        with db.transaction() as connection:
            assert connection.execute("SELECT existing FROM zones").fetchall() == []
            assert connection.execute("SELECT to_regclass('fenced_events')").fetchone() == (None,)


@settings(max_examples=8, deadline=None)
@given(
    st.lists(st.tuples(st.integers(0, 3), st.integers(0, 1), st.booleans()), min_size=1, max_size=8)
)
def test_persistent_transitions_match_the_pure_model(
    operations: list[tuple[int, int, bool]],
) -> None:
    with isolated_database() as db:
        migrate(db, expected_revision=0)
        repo = CorridorRepository(db)
        repo.register(("a", "b"))
        model = CorridorState((CorridorZone(LeaseState("a")), CorridorZone(LeaseState("b"))))
        for tick, (action, number, unknown) in enumerate(operations):
            holder = f"robot-{number}"
            observations = tuple(
                ZoneObservation(name, tick, None if unknown else ()) for name in ("a", "b")
            )
            if action < 2:
                request = CorridorRequest(
                    holder, ("a",) if action == 0 else ("a", "b"), Direction.FORWARD
                )
                expected = request_corridor(model, request, tick, observations, 2)
                actual = repo.reserve(request, tick, observations, lease_ticks=2)
                assert actual == expected
                model = expected.state
            elif action == 2:
                tokens = tuple(
                    ZoneToken(zone.lease.resource_id, zone.lease.token)
                    for zone in model.zones
                    if zone.lease.holder == holder
                ) or (ZoneToken("a", 1),)
                expected = release_corridor(model, holder, tokens, tick, observations)
                assert repo.release(holder, tokens, tick, observations) == expected
                model = expected.state
            else:
                model = expire_corridors(model, tick, observations)
                assert repo.expire(tick, observations) == model
            assert repo.snapshot() == model


def test_concurrent_holders_cannot_both_acquire_the_same_zone(database: Database) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))

    def reserve(number: int) -> bool:
        request = CorridorRequest(f"robot-{number}", ("a",), Direction.FORWARD)
        return CorridorRepository(database).reserve(request, 0, _empty(0)).granted

    with ThreadPoolExecutor(max_workers=4) as pool:
        grants = list(pool.map(reserve, range(4), timeout=20))
    assert sum(grants) == 1
    assert repo.snapshot().zones[0].lease.token == 1


def test_same_holder_cannot_concurrently_expand_into_disjoint_bundles(database: Database) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))

    def reserve(resource: str) -> bool:
        request = CorridorRequest("robot-0", (resource,), Direction.FORWARD)
        return CorridorRepository(database).reserve(request, 0, _empty(0)).granted

    with ThreadPoolExecutor(max_workers=2) as pool:
        grants = list(pool.map(reserve, ("a", "b"), timeout=20))
    assert sum(grants) == 1
    assert sum(zone.lease.holder == "robot-0" for zone in repo.snapshot().zones) == 1


def test_mixed_directions_survive_reconstruction_and_unknown_occupancy_denies(
    database: Database,
) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))
    request = CorridorRequest(
        "robot-0",
        ("a", "b"),
        Direction.FORWARD,
        (("a", Direction.FORWARD), ("b", Direction.REVERSE)),
    )
    assert not repo.reserve(request, 0, ()).granted
    first = repo.reserve(request, 1, _empty(1))
    retry = CorridorRepository(database).reserve(request, 2, _empty(2))
    assert first.granted and retry.granted and retry.tokens == first.tokens
    assert tuple(zone.direction for zone in repo.snapshot().zones) == (
        Direction.FORWARD,
        Direction.REVERSE,
    )


def test_restart_keeps_tokens_and_expired_occupied_faults(database: Database) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))
    granted = repo.reserve(CorridorRequest("old", ("a",), Direction.FORWARD), 0, _empty(0), 2)
    occupied = (ZoneObservation("a", 2, ("old",)), ZoneObservation("b", 2, ()))
    repo.expire(2, occupied)
    restarted = CorridorRepository(database)
    restarted.register(("a", "b"))
    assert restarted.snapshot().zones[0].fault_occupied
    assert not restarted.reserve(
        CorridorRequest("new", ("a",), Direction.REVERSE), 2, occupied
    ).granted
    replacement = restarted.reserve(CorridorRequest("new", ("a",), Direction.REVERSE), 3, _empty(3))
    assert replacement.granted
    assert replacement.tokens[0].token == granted.tokens[0].token + 1
    assert not restarted.record_event("stale", "old", granted.tokens, 3, "move").accepted


def test_fenced_effect_is_idempotent_and_rejects_different_content(database: Database) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))
    grant = repo.reserve(CorridorRequest("robot-0", ("a", "b"), Direction.FORWARD), 0, _empty(0))
    assert not repo.record_event("partial", "robot-0", grant.tokens[:1], 1, "move").accepted

    def record(_: int) -> bool:
        return (
            CorridorRepository(database)
            .record_event("event-1", "robot-0", grant.tokens, 1, "move")
            .replayed
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        replays = list(pool.map(record, range(4), timeout=20))
    assert sum(replays) == 3
    with pytest.raises(IdempotencyConflict):
        repo.record_event("event-1", "robot-0", grant.tokens, 1, "pick")
    assert repo.release("robot-0", grant.tokens, 2, _empty(2)).granted
    assert repo.record_event("event-1", "robot-0", grant.tokens, 3, "move").replayed
    assert not repo.record_event("event-2", "robot-0", grant.tokens, 3, "move").accepted
    with database.transaction() as connection:
        row = connection.execute("SELECT count(*) FROM fenced_events").fetchone()
        assert row == (1,)


def test_token_overflow_rolls_back_the_entire_multi_zone_grant(database: Database) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))
    with database.transaction() as connection:
        connection.execute("UPDATE zones SET token = 9223372036854775807 WHERE zone_id = 'b'")
    before = repo.snapshot()
    with pytest.raises(psycopg.errors.NumericValueOutOfRange):
        repo.reserve(CorridorRequest("robot-0", ("a", "b"), Direction.FORWARD), 0, _empty(0))
    assert repo.snapshot() == before


def test_fenced_effect_waits_for_row_lock_and_rechecks_replaced_token(database: Database) -> None:
    repo = CorridorRepository(database)
    repo.register(("a", "b"))
    grant = repo.reserve(CorridorRequest("old", ("a",), Direction.FORWARD), 0, _empty(0))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with database.transaction() as connection:
            connection.execute("SELECT zone_id FROM zones WHERE zone_id='a' FOR UPDATE")
            future = pool.submit(repo.record_event, "raced", "old", grant.tokens, 1, "move")
            deadline = time.monotonic() + 1.5
            waiting = False
            while time.monotonic() < deadline:
                connection.execute("SELECT pg_stat_clear_snapshot()")
                row = connection.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE pid <> pg_backend_pid() AND wait_event_type='Lock' "
                    "AND query LIKE 'SELECT zone_id, holder,%')"
                ).fetchone()
                if row == (True,):
                    waiting = True
                    break
                time.sleep(0.01)
            assert waiting, "effect must block on the same locked zone row"
            connection.execute(
                "UPDATE zones SET holder='new', token=token+1, observed_tick=1 WHERE zone_id='a'"
            )
        assert not future.result(timeout=10).accepted
    with database.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM fenced_events").fetchone() == (0,)
