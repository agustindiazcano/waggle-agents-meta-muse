"""Isolated cloud PostgreSQL schemas shared by the heavy correctness tests."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from psycopg import sql

from waggle.db.connection import Database


@contextmanager
def isolated_database() -> Iterator[Database]:
    """Create and remove only a uniquely named schema on the configured cloud service."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("PostgreSQL integration tests are cloud-only")
    root = Database.from_environ(os.environ)
    name = "waggle_test_" + uuid4().hex
    with root.transaction() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        yield Database(root.dsn, schema=name)
    finally:
        with root.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
