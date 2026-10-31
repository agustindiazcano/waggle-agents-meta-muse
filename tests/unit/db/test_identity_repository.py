"""Identity store rejects malformed digests and records before any database transaction."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.identities import PostgresIdentityStore

_HASH = "c" * 64


@pytest.mark.parametrize("digest", ["", "abc", "C" * 64, "g" * 64, "c" * 65, "c" * 63])
def test_malformed_digest_lookup_misses_without_connecting(digest: str) -> None:
    database = MagicMock(spec=Database)
    assert PostgresIdentityStore(database).lookup(digest) is None
    database.transaction.assert_not_called()


@pytest.mark.parametrize(
    ("digest", "chassis", "robot_id"),
    [
        ("abc", "carrier", "robot-0"),
        (_HASH, "unknown_chassis", "robot-0"),
        (_HASH, "carrier", ""),
        (_HASH, "carrier", "bad id"),
        (_HASH, "carrier", "r" * 65),
    ],
)
def test_invalid_registration_does_not_connect(digest: str, chassis: str, robot_id: str) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        PostgresIdentityStore(database).register(digest, chassis, robot_id)
    database.transaction.assert_not_called()


def test_malformed_digest_revoke_does_not_connect() -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        PostgresIdentityStore(database).revoke("nope")
    database.transaction.assert_not_called()
