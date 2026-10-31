"""A migrated cloud-only database schema for PostgreSQL correctness tests."""

from collections.abc import Iterator

import pytest
from postgres_support import isolated_database

from waggle.db.connection import Database
from waggle.db.schema import migrate


@pytest.fixture
def database() -> Iterator[Database]:
    """A migrated isolated schema, without sample rows."""
    with isolated_database() as db:
        migrate(db, expected_revision=0)
        yield db
