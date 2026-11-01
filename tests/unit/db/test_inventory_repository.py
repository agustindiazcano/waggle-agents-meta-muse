"""Inventory repository rejects malformed input before any database transaction."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.inventory import InventoryRepository


@pytest.mark.parametrize("part", ["", "a b", "x" * 65, "p;DROP", "café"])
def test_malformed_part_number_never_connects(part: str) -> None:
    database = MagicMock(spec=Database)
    repo = InventoryRepository(database)
    with pytest.raises(ValueError):
        repo.get(part)
    with pytest.raises(ValueError):
        repo.reserve("key-1", part, 1, "robot-0")
    database.transaction.assert_not_called()


@pytest.mark.parametrize("quantity", [0, -1, 1001, True, 1.0, "2"])
def test_invalid_quantity_never_connects(quantity: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        InventoryRepository(database).reserve("key-1", "P-100", quantity, "robot-0")  # type: ignore[arg-type]
    database.transaction.assert_not_called()


@pytest.mark.parametrize("key", ["", "has space", "k" * 129])
def test_invalid_idempotency_key_never_connects(key: str) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        InventoryRepository(database).reserve(key, "P-100", 1, "robot-0")
    database.transaction.assert_not_called()


@pytest.mark.parametrize("on_hand", [-1, True, 1_000_001])
def test_invalid_catalog_stock_never_connects(on_hand: object) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        InventoryRepository(database).add_part("P-100", on_hand)  # type: ignore[arg-type]
    database.transaction.assert_not_called()
