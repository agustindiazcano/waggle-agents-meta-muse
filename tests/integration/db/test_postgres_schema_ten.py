"""Cloud-only check of the revision 10 upgrade from revision 9 against PostgreSQL."""

import psycopg.errors
import pytest
from postgres_support import isolated_database

from waggle.db.schema import current_revision, migrate

pytestmark = pytest.mark.heavy


def test_revision_ten_upgrade_keeps_existing_rows_and_adds_nullable_links() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=9) == 9
        with db.transaction() as connection:
            connection.execute("INSERT INTO spare_parts (part_number, on_hand) VALUES ('P-1', 5)")
            connection.execute(
                "INSERT INTO part_reservations (idempotency_key, part_number, quantity, holder) "
                "VALUES ('k-1', 'P-1', 1, 'maint-0')"
            )
            connection.execute(
                "INSERT INTO purchase_orders (idempotency_key, part_number, quantity, requester) "
                "VALUES ('o-1', 'P-1', 1, 'maint-0')"
            )
        assert migrate(db, expected_revision=9, target_revision=10) == 10
        assert current_revision(db) == 10
        with db.transaction() as connection:
            for row in (
                connection.execute("SELECT ticket_id FROM part_reservations").fetchone(),
                connection.execute("SELECT ticket_id FROM purchase_orders").fetchone(),
            ):
                assert row is not None and row[0] is None
            count = connection.execute("SELECT count(*) FROM part_compatibility").fetchone()
            assert count is not None and count[0] == 0


def test_compatibility_rows_need_a_real_machine_and_part_and_are_unique() -> None:
    with isolated_database() as db:
        migrate(db, expected_revision=0)
        with db.transaction() as connection:
            connection.execute("INSERT INTO spare_parts (part_number, on_hand) VALUES ('P-1', 1)")
            connection.execute("INSERT INTO machines (machine_id) VALUES ('M-1')")
            connection.execute(
                "INSERT INTO part_compatibility (machine_id, part_number) VALUES ('M-1', 'P-1')"
            )
        with pytest.raises(psycopg.errors.UniqueViolation), db.transaction() as connection:
            connection.execute(
                "INSERT INTO part_compatibility (machine_id, part_number) VALUES ('M-1', 'P-1')"
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction() as connection:
            connection.execute(
                "INSERT INTO part_compatibility (machine_id, part_number) VALUES ('M-9', 'P-1')"
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction() as connection:
            connection.execute(
                "INSERT INTO part_compatibility (machine_id, part_number) VALUES ('M-1', 'P-9')"
            )


def test_ticket_links_are_foreign_keys() -> None:
    with isolated_database() as db:
        migrate(db, expected_revision=0)
        with db.transaction() as connection:
            connection.execute("INSERT INTO spare_parts (part_number, on_hand) VALUES ('P-1', 1)")
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction() as connection:
            connection.execute(
                "INSERT INTO part_reservations "
                "(idempotency_key, part_number, quantity, holder, ticket_id) "
                "VALUES ('k-1', 'P-1', 1, 'maint-0', 'tkt-0000000000000000')"
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction() as connection:
            connection.execute(
                "INSERT INTO purchase_orders "
                "(idempotency_key, part_number, quantity, requester, ticket_id) "
                "VALUES ('o-1', 'P-1', 1, 'maint-0', 'tkt-0000000000000000')"
            )
