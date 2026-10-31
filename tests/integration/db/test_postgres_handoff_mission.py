"""Cloud-only: a worker finishes handoff tasks only through the fenced path."""

import pytest

from waggle.coordination.corridors import CorridorRequest, Direction
from waggle.coordination.task_model import TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.occupancy import TrustedStateRepository
from waggle.db.tasks import TaskRepository
from waggle.handoff_finisher import HandoffFinisher
from waggle.worker import HandlerOutcome, WorkerResult, WorkerStatus, run_once

pytestmark = pytest.mark.heavy


def _approved(repo: TaskRepository, task_id: str, zone: str | None) -> None:
    repo.create(TaskDefinition(task_id, handoff_zone=zone))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        repo.advance(task_id, state, f"{task_id}-{state.value}", 0)


def _world(
    db: Database, *, holder: str = "robot-0", occupants: tuple[str, ...] | None = ("robot-0",)
) -> tuple[TaskRepository, TrustedStateRepository, HandoffFinisher]:
    corridors = CorridorRepository(db)
    corridors.register(("dock",))
    trusted = TrustedStateRepository(db)
    trusted.advance_tick(1)
    trusted.record("dock", 1, ())
    granted = corridors.reserve(
        CorridorRequest(holder, ("dock",), Direction.FORWARD), 1, trusted.observe(("dock",), 1)
    )
    assert granted.granted
    trusted.record("dock", 1, occupants)
    repo = TaskRepository(db)
    return repo, trusted, HandoffFinisher(repo, corridors, trusted)


def _run(
    repo: TaskRepository,
    trusted: TrustedStateRepository,
    finisher: HandoffFinisher,
    worker: str = "robot-0",
) -> WorkerResult:
    return run_once(
        repo,
        worker,
        "claim-" + worker,
        trusted.now_tick,
        lambda task: HandlerOutcome.DONE,
        complete=finisher.complete,
    )


def test_a_handoff_task_completes_when_the_holder_is_alone_in_the_zone(database: Database) -> None:
    repo, trusted, finisher = _world(database)
    _approved(repo, "delivery", "dock")
    result = _run(repo, trusted, finisher)
    assert result == WorkerResult(WorkerStatus.DONE, "delivery")
    task = repo.get("delivery")
    assert task is not None and task.state == TaskState.DONE


def test_a_second_occupant_in_the_trusted_record_blocks_completion(database: Database) -> None:
    repo, trusted, finisher = _world(database, occupants=("robot-0", "robot-1"))
    _approved(repo, "delivery", "dock")
    assert _run(repo, trusted, finisher).status == WorkerStatus.STALE
    task = repo.get("delivery")
    assert task is not None and task.state == TaskState.EXECUTING


def test_unknown_occupancy_blocks_completion(database: Database) -> None:
    repo, trusted, finisher = _world(database, occupants=None)
    _approved(repo, "delivery", "dock")
    assert _run(repo, trusted, finisher).status == WorkerStatus.STALE


def test_a_worker_that_does_not_hold_the_zone_cannot_finish(database: Database) -> None:
    repo, trusted, finisher = _world(database, holder="robot-1", occupants=("robot-1",))
    _approved(repo, "delivery", "dock")
    assert _run(repo, trusted, finisher, "robot-0").status == WorkerStatus.STALE
    task = repo.get("delivery")
    assert task is not None and task.state == TaskState.EXECUTING


def test_an_ordinary_task_still_completes_through_the_same_finisher(database: Database) -> None:
    repo, trusted, finisher = _world(database)
    _approved(repo, "plain", None)
    assert _run(repo, trusted, finisher).status == WorkerStatus.DONE


def test_default_completion_still_denies_a_handoff_task(database: Database) -> None:
    repo, trusted, _ = _world(database)
    _approved(repo, "delivery", "dock")
    result = run_once(
        repo, "robot-0", "claim-default", trusted.now_tick, lambda task: HandlerOutcome.DONE
    )
    assert result.status == WorkerStatus.STALE
