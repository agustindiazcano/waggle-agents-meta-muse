"""Revision 11 adds the technician lease columns and reservation settlement, with no data."""

from waggle.db import schema


def _statements() -> tuple[str, ...]:
    return tuple(" ".join(s.split()) for s in schema._MIGRATIONS[11])


def test_latest_revision_is_eleven() -> None:
    assert schema.LATEST_REVISION == 11
    assert sorted(schema._MIGRATIONS) == list(range(1, 12))


def test_tickets_gain_technician_token_and_closed_columns() -> None:
    joined = " ".join(_statements())
    assert "ALTER TABLE maintenance_tickets ADD COLUMN technician text" in joined
    assert "ALTER TABLE maintenance_tickets ADD COLUMN zone_token bigint" in joined
    assert "ALTER TABLE maintenance_tickets ADD COLUMN closed_at timestamptz" in joined


def test_ticket_status_is_widened_and_the_state_check_is_rebuilt() -> None:
    joined = " ".join(_statements())
    assert "CHECK (status IN ('open', 'dispatched', 'closed'))" in joined
    assert "ADD CONSTRAINT maintenance_tickets_state_check" in joined
    # A dispatched ticket has both a technician and a token, or neither (rows from revision 8).
    assert "(technician IS NULL) = (zone_token IS NULL)" in joined


def test_reservations_gain_a_status_and_a_settlement_time() -> None:
    joined = " ".join(_statements())
    assert (
        "ALTER TABLE part_reservations ADD COLUMN status text NOT NULL DEFAULT 'reserved' "
        "CHECK (status IN ('reserved', 'consumed', 'released'))"
    ) in joined
    assert "ALTER TABLE part_reservations ADD COLUMN settled_at timestamptz" in joined
    assert "CHECK ((status = 'reserved') = (settled_at IS NULL))" in joined


def test_the_migration_inserts_no_data_and_drops_no_table_or_column() -> None:
    upper = " ".join(_statements()).upper()
    for forbidden in ("INSERT", "DELETE", "TRUNCATE", "DROP TABLE", "DROP COLUMN"):
        assert forbidden not in upper
    # The only drop is the replacement of the two ticket status constraints.
    assert upper.count("DROP CONSTRAINT") == 1
