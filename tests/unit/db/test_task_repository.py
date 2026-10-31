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


def test_ordinary_completion_denies_a_handoff_required_task() -> None:
    from unittest.mock import patch

    from waggle.coordination.task_model import TaskCredential, TaskRecord, TaskState

    database = MagicMock(spec=Database)
    connection = database.transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = ("dock",)
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    with (
        patch("waggle.db.tasks._cached", return_value=None),
        patch("waggle.db.tasks._task", return_value=task),
        patch("waggle.db.tasks._store") as store,
    ):
        result = TaskRepository(database).complete(TaskCredential("delivery", "robot", 1), "r1", 1)
    assert not result.accepted
    store.assert_not_called()


def test_handoff_transaction_records_only_current_matching_evidence() -> None:
    from unittest.mock import patch

    from waggle.coordination.corridors import (
        CorridorState,
        CorridorZone,
        Direction,
        ZoneObservation,
        ZoneToken,
    )
    from waggle.coordination.leases import LeaseState
    from waggle.coordination.task_model import TaskCredential, TaskRecord, TaskState

    database = MagicMock(spec=Database)
    connection = database.transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = ("dock",)
    task = TaskRecord("delivery", TaskState.EXECUTING, 1, 1, "robot", 10, 0)
    zone = CorridorZone(LeaseState("dock", 2, "robot", 10, 0), Direction.FORWARD)
    credential = TaskCredential("delivery", "robot", 1)
    with (
        patch("waggle.db.tasks._cached", return_value=None),
        patch("waggle.db.tasks._task", return_value=task),
        patch("waggle.db.tasks._lock", return_value=CorridorState((zone,))),
        patch("waggle.db.tasks._store") as store,
        patch("waggle.db.tasks._event") as event,
    ):
        repo = TaskRepository(database)
        assert not repo.complete_handoff(
            credential, ZoneToken("dock", 2), ZoneObservation("dock", 0, ("robot",)), "r1", 1
        ).accepted
        store.assert_not_called()
        event.assert_not_called()
        assert repo.complete_handoff(
            credential, ZoneToken("dock", 2), ZoneObservation("dock", 1, ("robot",)), "r2", 1
        ).accepted
        store.assert_called_once()
        event.assert_called_once()
