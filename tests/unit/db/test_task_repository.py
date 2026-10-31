"""Task repository rejects malformed names, requests and recovery limits before I/O."""

from unittest.mock import MagicMock

import pytest

from waggle.db.connection import Database
from waggle.db.tasks import TaskRepository


@pytest.mark.parametrize("limit", [0, -1, True, 1001])
def test_invalid_recovery_limit_does_not_connect(limit: int) -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        TaskRepository(database).recover(0, limit=limit)
    database.transaction.assert_not_called()


def test_invalid_claim_cannot_open_a_transaction() -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError):
        TaskRepository(database).claim("bad worker", "request-1", 0)
    with pytest.raises(ValueError):
        TaskRepository(database).claim("worker-0", "request-1", 0, lease_ticks=0)
    database.transaction.assert_not_called()
