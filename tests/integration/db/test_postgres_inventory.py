"""Cloud-only inventory checks against PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from waggle.db.connection import Database
from waggle.db.corridors import IdempotencyConflict
from waggle.db.inventory import InventoryRepository, PartStock, UnknownPart

pytestmark = pytest.mark.heavy


def _repo(database: Database, on_hand: int = 5) -> InventoryRepository:
    repo = InventoryRepository(database)
    repo.add_part("P-100", on_hand)
    return repo


def test_unknown_part_reads_as_none_and_cannot_be_reserved(database: Database) -> None:
    repo = _repo(database)
    assert repo.get("P-999") is None
    with pytest.raises(UnknownPart):
        repo.reserve("k-1", "P-999", 1, "maint-0")


def test_reservation_reduces_available_stock(database: Database) -> None:
    repo = _repo(database)
    result = repo.reserve("k-1", "P-100", 2, "maint-0")
    assert (result.granted, result.reason) == (True, "reserved")
    assert repo.get("P-100") == PartStock("P-100", 5, 2)


def test_same_key_and_values_replays_without_a_second_reservation(database: Database) -> None:
    repo = _repo(database)
    repo.reserve("k-1", "P-100", 2, "maint-0")
    again = repo.reserve("k-1", "P-100", 2, "maint-0")
    assert (again.granted, again.reason) == (True, "replayed")
    assert repo.get("P-100") == PartStock("P-100", 5, 2)


def test_same_key_with_other_values_conflicts(database: Database) -> None:
    repo = _repo(database)
    repo.reserve("k-1", "P-100", 2, "maint-0")
    with pytest.raises(IdempotencyConflict):
        repo.reserve("k-1", "P-100", 3, "maint-0")
    with pytest.raises(IdempotencyConflict):
        repo.reserve("k-1", "P-100", 2, "maint-1")


def test_shortage_is_denied_and_changes_nothing(database: Database) -> None:
    repo = _repo(database, on_hand=1)
    result = repo.reserve("k-1", "P-100", 2, "maint-0")
    assert (result.granted, result.reason) == (False, "insufficient_stock")
    assert repo.get("P-100") == PartStock("P-100", 1, 0)


def test_concurrent_reservations_never_oversell(database: Database) -> None:
    repo = _repo(database, on_hand=3)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: repo.reserve(f"k-{i}", "P-100", 1, "maint-0"), range(8)))
    assert sum(r.granted for r in results) == 3
    assert repo.get("P-100") == PartStock("P-100", 3, 3)


def test_concurrent_calls_with_one_key_reserve_once(database: Database) -> None:
    repo = _repo(database)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _i: repo.reserve("k-1", "P-100", 2, "maint-0"), range(6)))
    assert all(r.granted for r in results)
    assert repo.get("P-100") == PartStock("P-100", 5, 2)


def test_database_rejects_reserved_above_on_hand(database: Database) -> None:
    _repo(database)
    with pytest.raises(Exception, match="check"), database.transaction() as connection:
        connection.execute("UPDATE spare_parts SET reserved = on_hand + 1")
