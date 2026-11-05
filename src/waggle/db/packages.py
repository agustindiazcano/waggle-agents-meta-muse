"""PostgreSQL registry of valid package ids (ADR-075).

The registry declares which ids exist and says nothing about where a package is: the simulator
owns ground truth. Only load scripts write it. The server reads it before it queues a package
order, so an id found in no registry row never reaches the queue.
"""

import re
from typing import cast

from waggle.db.connection import Database

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_SOURCE_MAX = 64


def _id(value: object) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("invalid package id")
    return value


def _source(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= _SOURCE_MAX or not value.isprintable():
        raise ValueError("invalid source")
    return value


class PackageRegistry:
    """Read access for the server and write access for load scripts and tests."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, package_id: str, source: str = "scenario") -> None:
        """Register one id. A repeat raises psycopg UniqueViolation."""
        _id(package_id)
        _source(source)
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO packages (package_id, source) VALUES (%s, %s)", (package_id, source)
            )

    def has(self, package_id: str) -> bool:
        """Whether the id is registered. A malformed id raises ValueError."""
        _id(package_id)
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM packages WHERE package_id=%s", (package_id,)
            ).fetchone()
        return row is not None

    def ids(self) -> tuple[str, ...]:
        """Every registered id, in package_id order."""
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT package_id FROM packages ORDER BY package_id"
            ).fetchall()
        return tuple(cast(str, row[0]) for row in rows)

    def count(self) -> int:
        """The number of registered ids."""
        with self._database.transaction() as connection:
            row = connection.execute("SELECT count(*) FROM packages").fetchone()
        # count(*) always returns one integer row.
        return cast(int, row[0]) if row is not None else 0
