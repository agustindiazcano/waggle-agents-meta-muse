"""Revision 12 adds the package id registry (ADR-075). It holds ids, never locations."""

from collections.abc import Callable
from typing import Any

import pytest
from db_fakes import FakeDatabase

from waggle.db import schema
from waggle.db.packages import PackageRegistry


def _statements() -> tuple[str, ...]:
    return tuple(" ".join(s.split()) for s in schema._MIGRATIONS[12])


def test_revision_twelve_is_in_the_chain() -> None:
    assert schema.LATEST_REVISION >= 12
    assert sorted(schema._MIGRATIONS) == list(range(1, schema.LATEST_REVISION + 1))


def test_the_registry_table_has_an_id_key_a_source_and_no_location() -> None:
    table = _statements()[0]
    assert table.startswith("CREATE TABLE packages")
    assert "package_id text PRIMARY KEY CHECK (package_id ~ '^[A-Za-z0-9_.-]{1,64}$')" in table
    assert "source text NOT NULL" in table
    for location in (" x ", " y ", "zone_id", "holder", "robot_id"):
        assert location not in table


def test_the_migration_inserts_no_data_and_drops_nothing() -> None:
    upper = " ".join(_statements()).upper()
    for forbidden in ("INSERT", "DROP", "DELETE", "UPDATE", "TRUNCATE"):
        assert forbidden not in upper


def _registry(row: tuple[object, ...] | None) -> tuple[PackageRegistry, FakeDatabase]:
    db = FakeDatabase(lambda sql, params: row)
    return PackageRegistry(db), db  # type: ignore[arg-type]


def test_has_is_true_only_when_the_row_exists() -> None:
    assert _registry((1,))[0].has("pk-1") is True
    assert _registry(None)[0].has("pk-1") is False


CALLS: list[Callable[[PackageRegistry], Any]] = [
    lambda r: r.has(""),
    lambda r: r.has("pk 1"),
    lambda r: r.has("x" * 65),
    lambda r: r.has(7),  # type: ignore[arg-type]
    lambda r: r.add("pk;1"),
    lambda r: r.add("pk-1", source=""),
    lambda r: r.add("pk-1", source="s" * 65),
]


@pytest.mark.parametrize("call", CALLS)
def test_a_malformed_id_or_source_is_refused_before_any_query(
    call: Callable[[PackageRegistry], Any],
) -> None:
    registry, db = _registry(None)
    with pytest.raises(ValueError):
        call(registry)
    assert db.log == []


def test_ids_returns_every_registered_id_in_order() -> None:
    db = FakeDatabase(lambda sql, params: ("pk-1",))
    registry = PackageRegistry(db)  # type: ignore[arg-type]
    assert registry.ids() == ("pk-1",)
    assert "ORDER BY package_id" in db.log[-1]
