"""Explicit initial coordination migration, without sample data or destructive DDL."""

import argparse
import logging
import os
from collections.abc import Sequence
from typing import LiteralString

import psycopg

from waggle.db.connection import Database, Row

LATEST_REVISION = 3
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

_TASK_DDL: tuple[LiteralString, ...] = (
    """CREATE TABLE tasks (
        task_id text PRIMARY KEY,
        state text NOT NULL CHECK (state IN (
            'PENDING','SCREENED','REVIEWED','APPROVED','ASSIGNED','EXECUTING',
            'DONE','ESCALATED','REJECTED','FAILED','ABORTED')),
        attempt integer NOT NULL DEFAULT 0,
        token bigint NOT NULL DEFAULT 0 CHECK (token >= attempt),
        worker_id text,
        expires_tick bigint,
        observed_tick bigint NOT NULL DEFAULT 0 CHECK (observed_tick >= 0),
        max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
        priority integer NOT NULL CHECK (priority BETWEEN 0 AND 9),
        definition_signature text NOT NULL,
        CHECK (attempt BETWEEN 0 AND max_attempts),
        CHECK ((state IN ('ASSIGNED','EXECUTING') AND worker_id IS NOT NULL
                AND length(worker_id) > 0 AND expires_tick IS NOT NULL
                AND expires_tick > observed_tick AND token > 0 AND attempt > 0)
            OR (state NOT IN ('ASSIGNED','EXECUTING') AND worker_id IS NULL
                AND expires_tick IS NULL))
    )""",
    """CREATE UNIQUE INDEX tasks_active_worker ON tasks (worker_id)
        WHERE state IN ('ASSIGNED','EXECUTING')""",
    """CREATE INDEX tasks_eligible ON tasks (priority DESC, task_id)
        WHERE state='APPROVED'""",
    """CREATE INDEX tasks_expiring ON tasks (expires_tick, task_id)
        WHERE state IN ('ASSIGNED','EXECUTING')""",
    """CREATE TABLE task_dependencies (
        task_id text NOT NULL REFERENCES tasks(task_id),
        depends_on text NOT NULL REFERENCES tasks(task_id),
        PRIMARY KEY (task_id, depends_on), CHECK (task_id <> depends_on)
    )""",
    """CREATE TABLE task_events (
        event_no bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
        event_id text PRIMARY KEY,
        signature text NOT NULL,
        event_kind text NOT NULL,
        from_state text,
        task_id text NOT NULL REFERENCES tasks(task_id),
        state text NOT NULL,
        attempt integer NOT NULL,
        token bigint NOT NULL,
        worker_id text,
        expires_tick bigint,
        observed_tick bigint NOT NULL,
        max_attempts integer NOT NULL,
        priority integer NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )""",
)

_HANDOFF_DDL: tuple[LiteralString, ...] = (
    """CREATE TABLE task_handoffs (
        task_id text PRIMARY KEY REFERENCES tasks(task_id),
        zone_id text NOT NULL REFERENCES zones(zone_id)
    )""",
)

_MIGRATIONS = {1: _DDL, 2: _TASK_DDL, 3: _HANDOFF_DDL}


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


def migrate(
    database: Database, *, expected_revision: int, target_revision: int = LATEST_REVISION
) -> int:
    """Apply forward-only migrations after checking revision under a transaction lock."""
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError("expected revision must be a nonnegative integer")
    if type(target_revision) is not int or not 1 <= target_revision <= LATEST_REVISION:
        raise ValueError("invalid target revision")
    with database.transaction() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        actual = _revision(connection)
        if actual != expected_revision or not 0 <= actual <= target_revision:
            raise SchemaVersionError("unexpected or unsupported schema revision")
        for revision in range(actual + 1, target_revision + 1):
            for statement in _MIGRATIONS[revision]:
                connection.execute(statement)
            if revision == 1:
                connection.execute("INSERT INTO waggle_schema (revision) VALUES (%s)", (revision,))
            else:
                connection.execute(
                    "UPDATE waggle_schema SET revision=%s, installed_at=clock_timestamp()",
                    (revision,),
                )
    return target_revision


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect revision, or explicitly migrate from an expected revision."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--target-revision", type=int)
    args = parser.parse_args(argv)
    if args.expected_revision is None and args.target_revision is not None:
        parser.error("--target-revision requires --expected-revision")
    database = Database.from_environ(os.environ)
    if args.expected_revision is None:
        revision = current_revision(database)
    else:
        revision = migrate(
            database,
            expected_revision=args.expected_revision,
            target_revision=args.target_revision
            if args.target_revision is not None
            else LATEST_REVISION,
        )
    logging.basicConfig(
        level=logging.INFO, format='{"event":"schema_revision","revision":%(message)s}'
    )
    logging.getLogger(__name__).info("%d", revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
