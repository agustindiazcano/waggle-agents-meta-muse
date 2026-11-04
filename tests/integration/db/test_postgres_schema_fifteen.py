"""Cloud-only checks of the motion_orders package foreign key (revision 15)."""

import psycopg.errors
import pytest
from postgres_support import isolated_database

from waggle.db.schema import current_revision, migrate

pytestmark = pytest.mark.heavy


def test_revision_fifteen_upgrade_adds_the_package_foreign_key() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=14) == 14
        assert migrate(db, expected_revision=14, target_revision=15) == 15
        assert current_revision(db) == 15
        with db.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM pg_constraint WHERE conname='motion_orders_package_id_fkey'"
            ).fetchone()
        assert row is not None


def test_a_direct_insert_with_an_unknown_package_fails() -> None:
    with isolated_database() as db:
        migrate(db, expected_revision=0)
        with db.transaction() as connection:
            connection.execute(
                "INSERT INTO tasks (task_id, state, max_attempts, priority,"
                " definition_signature) VALUES ('job', 'PENDING', 3, 5, 'sig')"
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction() as connection:
            connection.execute(
                "INSERT INTO motion_orders (robot_id, task_id, tool, package_id, signature,"
                " created_tick) VALUES ('robot', 'job', 'pick_package', 'pk-unknown',"
                " 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 0)"
            )
