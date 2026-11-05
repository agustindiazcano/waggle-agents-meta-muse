"""Revision 15 adds the motion_orders package foreign key. Additive only, nothing dropped."""

from waggle.db import schema


def _statements() -> tuple[str, ...]:
    return tuple(" ".join(s.split()) for s in schema._MIGRATIONS[15])


def test_revision_fifteen_is_latest_and_in_the_chain() -> None:
    assert schema.LATEST_REVISION == 15
    assert sorted(schema._MIGRATIONS) == list(range(1, schema.LATEST_REVISION + 1))


def test_motion_orders_package_id_references_the_registry() -> None:
    statement = _statements()[0]
    assert statement.startswith("ALTER TABLE motion_orders")
    assert "FOREIGN KEY (package_id) REFERENCES packages(package_id)" in statement


def test_the_migration_is_additive_only() -> None:
    upper = " ".join(_statements()).upper()
    for forbidden in ("DROP", "DELETE", "UPDATE", "TRUNCATE", "INSERT INTO"):
        assert forbidden not in upper
