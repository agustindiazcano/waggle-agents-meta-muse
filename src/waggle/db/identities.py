"""PostgreSQL store for chassis token digests (ADR-032).

Only ``sha256(token)`` is stored, never the token. This module authenticates nobody:
``waggle.mcp_server.identity.authenticate`` compares digests and checks the revoked flag. A
lookup failure raises, so authentication denies.
"""

import re
from typing import cast

from waggle.db.connection import Database
from waggle.mcp_server.allowlist import ALLOWLIST
from waggle.mcp_server.identity import IdentityRecord

_DIGEST = re.compile(r"[0-9a-f]{64}")
_ROBOT_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def _digest(value: object) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("token digest must be 64 lowercase hex digits")
    return value


class PostgresIdentityStore:
    """Implements ``IdentityStore`` over ``robot_identities``."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def lookup(self, token_hash: str) -> IdentityRecord | None:
        """Return the record for a digest, revoked ones included, or None on a miss."""
        if not isinstance(token_hash, str) or _DIGEST.fullmatch(token_hash) is None:
            return None
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT token_hash, chassis, robot_id, revoked FROM robot_identities "
                "WHERE token_hash=%s",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        # Column types and constraints fix the row types.
        return IdentityRecord(
            cast(str, row[0]), cast(str, row[1]), cast(str, row[2]), cast(bool, row[3])
        )

    def register(self, token_hash: str, chassis: str, robot_id: str) -> None:
        """Store a new active identity. The token itself is generated and kept outside.

        Raises UniqueViolation for a repeated digest or a second active token for the same
        robot; revoke the old one first to rotate.
        """
        _digest(token_hash)
        if chassis not in ALLOWLIST:
            raise ValueError("unknown chassis")
        if not isinstance(robot_id, str) or _ROBOT_ID.fullmatch(robot_id) is None:
            raise ValueError("invalid robot id")
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO robot_identities (token_hash, chassis, robot_id) VALUES (%s, %s, %s)",
                (token_hash, chassis, robot_id),
            )

    def revoke(self, token_hash: str) -> bool:
        """Revoke a digest. False when it is unknown or already revoked."""
        _digest(token_hash)
        with self._database.transaction() as connection:
            row = connection.execute(
                "UPDATE robot_identities SET revoked=true, revoked_at=clock_timestamp() "
                "WHERE token_hash=%s AND NOT revoked RETURNING token_hash",
                (token_hash,),
            ).fetchone()
        return row is not None
