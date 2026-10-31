"""Cloud-only identity store checks against PostgreSQL."""

import psycopg
import pytest

from waggle.db.connection import Database
from waggle.db.identities import PostgresIdentityStore
from waggle.mcp_server.identity import IdentityRecord, authenticate, generate_token, hash_token

pytestmark = pytest.mark.heavy


def test_registered_token_authenticates_with_the_stored_identity(database: Database) -> None:
    store = PostgresIdentityStore(database)
    token = generate_token()
    store.register(hash_token(token), "carrier", "carrier-0")
    identity = authenticate(token, store)
    assert (identity.chassis, identity.robot_id) == ("carrier", "carrier-0")


def test_unknown_digest_misses(database: Database) -> None:
    assert PostgresIdentityStore(database).lookup(hash_token("x" * 43)) is None


def test_lookup_returns_the_full_record(database: Database) -> None:
    store = PostgresIdentityStore(database)
    digest = hash_token("a" * 43)
    store.register(digest, "forklift", "fork-1")
    assert store.lookup(digest) == IdentityRecord(digest, "forklift", "fork-1", False)


def test_revoked_token_is_found_and_flagged(database: Database) -> None:
    store = PostgresIdentityStore(database)
    digest = hash_token("b" * 43)
    store.register(digest, "carrier", "carrier-0")
    assert store.revoke(digest)
    found = store.lookup(digest)
    assert found is not None and found.revoked
    assert not store.revoke(digest)


def test_revoking_an_unknown_digest_returns_false(database: Database) -> None:
    assert not PostgresIdentityStore(database).revoke(hash_token("z" * 43))


def test_duplicate_digest_is_rejected(database: Database) -> None:
    store = PostgresIdentityStore(database)
    digest = hash_token("d" * 43)
    store.register(digest, "carrier", "carrier-0")
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.register(digest, "forklift", "fork-1")


def test_only_one_active_token_per_robot(database: Database) -> None:
    store = PostgresIdentityStore(database)
    first, second = hash_token("e" * 43), hash_token("f" * 43)
    store.register(first, "carrier", "carrier-0")
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.register(second, "carrier", "carrier-0")
    store.revoke(first)
    store.register(second, "carrier", "carrier-0")
    found = store.lookup(second)
    assert found is not None and not found.revoked


def test_table_rejects_a_non_digest_value(database: Database) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
        connection.execute(
            "INSERT INTO robot_identities (token_hash, chassis, robot_id) "
            "VALUES ('plain-token', 'carrier', 'carrier-0')"
        )
