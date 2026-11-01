"""Cloud-only: the oracle counts a stale write in the no-fencing baseline and none in production."""

import pytest

from waggle.coordination.task_model import TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.tasks import TaskRepository
from waggle.experiments.e2_baseline import NoFencingTaskRepository
from waggle.experiments.e2_log import load_oracle_inputs
from waggle.experiments.e2_oracle import TaskReport, judge_tasks

pytestmark = pytest.mark.heavy


def _approved(repo: TaskRepository, name: str) -> None:
    repo.create(TaskDefinition(name, (), 3, 0))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        repo.advance(name, state, f"{name}-{state.value}", 0)


def _stale_completion(repo: TaskRepository) -> bool:
    """Attempt 1 expires, the same worker claims attempt 2, then attempt 1 completes late."""
    _approved(repo, "t1")
    first = repo.claim("w1", "claim-1", 0, lease_ticks=10)
    assert first.task is not None
    old = first.task.credential()
    assert repo.recover(20)
    second = repo.claim("w1", "claim-2", 21, lease_ticks=10)
    assert second.task is not None
    assert repo.start(second.task.credential(), "start-2", 22).accepted
    return repo.complete(old, "complete-old", 23).accepted


def _report(database: Database) -> TaskReport:
    events, states = load_oracle_inputs(database)
    return judge_tasks(events, states)


def test_production_denies_the_late_completion_and_the_oracle_counts_none(
    database: Database,
) -> None:
    assert _stale_completion(TaskRepository(database)) is False
    report = _report(database)
    assert report.stale_writes_accepted == 0
    assert report.double_assignments == 0


def test_baseline_accepts_the_late_completion_and_the_oracle_counts_it(
    database: Database,
) -> None:
    assert _stale_completion(NoFencingTaskRepository(database)) is True
    report = _report(database)
    assert report.stale_writes_accepted == 1
    assert report.tasks_done == 1


def test_baseline_replay_of_the_same_request_writes_one_event(database: Database) -> None:
    repo = NoFencingTaskRepository(database)
    _approved(repo, "t1")
    claimed = repo.claim("w1", "claim-1", 0, lease_ticks=10)
    assert claimed.task is not None
    credential = claimed.task.credential()
    first = repo.start(credential, "start-1", 1)
    again = repo.start(credential, "start-1", 1)
    assert first.accepted and again.accepted and again.replayed
    events, _ = load_oracle_inputs(database)
    assert sum(1 for event in events if event.kind == "executing") == 1
