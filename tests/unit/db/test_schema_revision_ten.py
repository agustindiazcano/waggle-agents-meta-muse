"""Revision 10 adds the part compatibility table and ticket links, with no data and no drops."""

from waggle.db import schema


def _statements() -> tuple[str, ...]:
    return tuple(" ".join(s.split()) for s in schema._MIGRATIONS[10])


def test_latest_revision_is_ten() -> None:
    assert schema.LATEST_REVISION == 10
    assert sorted(schema._MIGRATIONS) == list(range(1, 11))


def test_compatibility_table_has_a_composite_key_and_both_foreign_keys() -> None:
    table = _statements()[0]
    assert table.startswith("CREATE TABLE part_compatibility")
    assert "machine_id text NOT NULL REFERENCES machines(machine_id)" in table
    assert "part_number text NOT NULL REFERENCES spare_parts(part_number)" in table
    assert "PRIMARY KEY (machine_id, part_number)" in table
    assert "created_at timestamptz NOT NULL DEFAULT clock_timestamp()" in table


def test_reservations_and_orders_gain_a_nullable_ticket_link() -> None:
    joined = " ".join(_statements())
    for table in ("part_reservations", "purchase_orders"):
        assert (
            f"ALTER TABLE {table} ADD COLUMN ticket_id text "
            "REFERENCES maintenance_tickets(ticket_id)"
        ) in joined
    assert "ticket_id text NOT NULL" not in joined


def test_the_migration_inserts_no_data_and_drops_nothing() -> None:
    upper = " ".join(_statements()).upper()
    for forbidden in ("INSERT", "DROP", "DELETE", "UPDATE", "TRUNCATE"):
        assert forbidden not in upper
