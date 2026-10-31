"""Explicit initial coordination migration, without sample data or destructive DDL."""

import argparse
import logging
import os
from collections.abc import Sequence
from typing import LiteralString

import psycopg

from waggle.db.connection import Database, Row

LATEST_REVISION = 1
_MIGRATION_LOCK = 19730401
_DDL: tuple[LiteralString, ...] = (
    """CREATE TABLE waggle_schema (
        singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
        revision integer NOT NULL CHECK (revision > 0),
        installed_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )""",
    """CREATE TABLE zones (
        zone_id text PRIMARY KEY CHECK (length(zone_id) > 0),
        holder text,
        token bigint NOT NULL DEFAULT 0 CHECK (token >= 0),
        expires_tick bigint CHECK (expires_tick >= 0),
        observed_tick bigint NOT NULL DEFAULT 0 CHECK (observed_tick >= 0),
        direction text CHECK (direction IN ('forward', 'reverse')),
        fault_occupied boolean NOT NULL DEFAULT false,
        CHECK ((holder IS NULL AND expires_tick IS NULL AND direction IS NULL
                AND NOT fault_occupied)
            OR (holder IS NOT NULL AND length(holder) > 0 AND expires_tick IS NOT NULL
                AND direction IS NOT NULL AND token > 0))
    )""",
    """CREATE TABLE fenced_events (
        event_id text PRIMARY KEY,
        holder text NOT NULL,
        credentials text NOT NULL,
        event_kind text NOT NULL,
        executed_tick bigint NOT NULL CHECK (executed_tick >= 0),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )""",
)


class SchemaVersionError(RuntimeError):
    """The actual schema revision differs from the explicit migration expectation."""


def _revision(connection: psycopg.Connection[Row]) -> int:
    row = connection.execute("SELECT to_regclass('waggle_schema')").fetchone()
    if row is None:
        raise SchemaVersionError("schema lookup returned no row")
    if row[0] is None:
        return 0
    row = connection.execute("SELECT revision FROM waggle_schema WHERE singleton").fetchone()
    if row is None or type(row[0]) is not int:
        raise SchemaVersionError("missing or invalid schema revision")
    return row[0]


def current_revision(database: Database) -> int:
    """Read the installed revision without applying a migration."""
    with database.transaction() as connection:
        return _revision(connection)


def migrate(database: Database, *, expected_revision: int) -> int:
    """Apply the initial schema only after checking revision under a transaction lock."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("expected revision must be a nonnegative integer")
    with database.transaction() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        actual = _revision(connection)
        if actual != expected_revision or actual not in (0, LATEST_REVISION):
            raise SchemaVersionError("unexpected or unsupported schema revision")
        if actual == LATEST_REVISION:
            return actual
        for statement in _DDL:
            connection.execute(statement)
        connection.execute("INSERT INTO waggle_schema (revision) VALUES (%s)", (LATEST_REVISION,))
    return LATEST_REVISION


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect revision, or explicitly migrate from an expected revision."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision", type=int)
    args = parser.parse_args(argv)
    database = Database.from_environ(os.environ)
    if args.expected_revision is None:
        revision = current_revision(database)
    else:
        revision = migrate(database, expected_revision=args.expected_revision)
    logging.basicConfig(
        level=logging.INFO, format='{"event":"schema_revision","revision":%(message)s}'
    )
    logging.getLogger(__name__).info("%d", revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
