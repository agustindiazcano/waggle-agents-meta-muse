"""Cloud-only task claims, recovery, event atomicity and worker lifecycle tests."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from postgres_support import isolated_database

from waggle.coordination.corridors import CorridorRequest, Direction, ZoneObservation
from waggle.coordination.task_model import TaskCredential, TaskDefinition, TaskRecord, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.schema import SchemaVersionError, current_revision, migrate
from waggle.db.tasks import TaskConflictError, TaskNotFoundError, TaskRepository
from waggle.worker import HandlerOutcome, WorkerStatus, run_once

pytestmark = pytest.mark.heavy


def _ready(
    repo: TaskRepository,
    name: str,
    *,
    dependencies: tuple[str, ...] = (),
    max_attempts: int = 3,
    priority: int = 0,
) -> TaskRecord:
    task = repo.create(TaskDefinition(name, dependencies, max_attempts, priority))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        result = repo.advance(name, state, f"{name}-{state.value}", 0)
        assert result.task is not None
        task = result.task
    return task


def _credential(
    repo: TaskRepository, worker: str, request: str, *, lease_ticks: int = 10, now: int = 0
) -> TaskCredential:
    claimed = repo.claim(worker, request, now, lease_ticks=lease_ticks)
    assert claimed.accepted and claimed.task is not None
    return claimed.task.credential()


def test_revision_two_upgrade_preserves_zone_tokens_and_rejects_downgrade() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=1) == 1
        assert current_revision(db) == 1
        corridors = CorridorRepository(db)
        corridors.register(("lane",))
        corridors.reserve(
            CorridorRequest("robot-0", ("lane",), Direction.FORWARD),
            0,
            (ZoneObservation("lane", 0, ()),),
        )
        before = corridors.snapshot()
        assert migrate(db, expected_revision=1, target_revision=2) == 2
        assert corridors.snapshot() == before
        with pytest.raises(SchemaVersionError):
            migrate(db, expected_revision=2, target_revision=1)
        with db.transaction() as connection:
            assert connection.execute("SELECT count(*) FROM tasks").fetchone() == (0,)


def test_failed_revision_two_upgrade_rolls_back_all_new_tables() -> None:
    with isolated_database() as db:
        migrate(db, expected_revision=0, target_revision=1)
        corridors = CorridorRepository(db)
        corridors.register(("lane",))
        before = corridors.snapshot()
        with db.transaction() as connection:
            connection.execute("CREATE TABLE task_events (existing integer)")
        with pytest.raises(psycopg.errors.DuplicateTable):
            migrate(db, expected_revision=1)
        assert current_revision(db) == 1
        assert corridors.snapshot() == before
        with db.transaction() as connection:
            assert connection.execute("SELECT to_regclass('tasks')").fetchone() == (None,)
            assert connection.execute("SELECT existing FROM task_events").fetchall() == []


def test_parallel_workers_claim_distinct_tasks(database: Database) -> None:
    repo = TaskRepository(database)
    for number in range(4):
        _ready(repo, f"task-{number}")

    def claim(number: int) -> str:
        result = TaskRepository(database).claim(f"worker-{number}", f"claim-{number}", 0)
        assert result.accepted and result.task is not None
        return result.task.task_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        names = list(pool.map(claim, range(4), timeout=20))
    assert len(set(names)) == 4
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM tasks WHERE state='ASSIGNED'"
        ).fetchone() == (4,)


def test_claim_skips_a_locked_high_priority_task(database: Database) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a", priority=9)
    _ready(repo, "b")
    with ThreadPoolExecutor(max_workers=1) as pool, database.transaction() as connection:
        connection.execute("SELECT task_id FROM tasks WHERE task_id='a' FOR UPDATE")
        result = pool.submit(repo.claim, "worker-0", "claim-b", 0).result(timeout=5)
        assert result.task is not None and result.task.task_id == "b"


def test_same_worker_cannot_hold_two_concurrent_attempts(database: Database) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    _ready(repo, "b")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda n: repo.claim("worker-0", f"claim-{n}", 0), range(2), timeout=20)
        )
    assert sum(result.accepted for result in results) == 1


def test_old_completion_is_denied_after_crash_recovery_even_for_same_worker(
    database: Database,
) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    old = _credential(repo, "worker-0", "old", lease_ticks=1)
    assert repo.start(old, "old-start", 0).accepted
    assert repo.recover(1)[0].state == TaskState.APPROVED
    new = _credential(repo, "worker-0", "new", now=1)
    assert new.token == old.token + 1
    assert repo.start(new, "new-start", 1).accepted
    assert not repo.complete(old, "late", 2).accepted
    assert repo.complete(new, "complete", 2).accepted
    assert repo.complete(new, "complete", 3).replayed
    assert repo.claim("worker-0", "old", 3, lease_ticks=1).replayed
    assert repo.get("a").state == TaskState.DONE  # type: ignore[union-attr]
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM task_events WHERE state='DONE'"
        ).fetchone() == (1,)


def test_recovery_skips_locked_tasks_and_never_clears_occupied_zones(database: Database) -> None:
    repo = TaskRepository(database)
    for name in ("a", "b"):
        _ready(repo, name)
        _credential(repo, "worker-" + name, "claim-" + name, lease_ticks=1)
    corridors = CorridorRepository(database)
    corridors.register(("lane",))
    corridors.reserve(
        CorridorRequest("robot-0", ("lane",), Direction.FORWARD),
        0,
        (ZoneObservation("lane", 0, ()),),
        1,
    )
    corridors.expire(1, (ZoneObservation("lane", 1, ("robot-0",)),))
    before = corridors.snapshot()
    with ThreadPoolExecutor(max_workers=1) as pool, database.transaction() as connection:
        connection.execute("SELECT task_id FROM tasks WHERE task_id='a' FOR UPDATE")
        recovered = pool.submit(repo.recover, 1).result(timeout=5)
        assert tuple(task.task_id for task in recovered) == ("b",)
    assert tuple(task.task_id for task in repo.recover(1)) == ("a",)
    assert corridors.snapshot() == before and before.zones[0].fault_occupied


def test_attempt_exhaustion_fails_instead_of_requeueing_forever(database: Database) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a", max_attempts=1)
    old = _credential(repo, "worker-0", "claim", lease_ticks=1)
    failed = repo.recover(1)
    assert len(failed) == 1 and failed[0].state == TaskState.FAILED
    assert failed[0].token == old.token and failed[0].worker_id is None
    assert not repo.claim("worker-1", "new", 2).accepted
    assert repo.recover(2) == ()


def test_dependencies_unlock_only_after_done_and_definitions_are_immutable(
    database: Database,
) -> None:
    repo = TaskRepository(database)
    parent = _ready(repo, "parent", priority=1)
    _ready(repo, "child", dependencies=("parent",), priority=9)
    assert repo.create(TaskDefinition("parent", priority=1)) == parent
    with pytest.raises(TaskConflictError):
        repo.create(TaskDefinition("parent", priority=2))
    with pytest.raises(ValueError, match="dependencies"):
        repo.create(TaskDefinition("missing-parent", dependencies=("absent",)))
    assert repo.get("missing-parent") is None
    credential = _credential(repo, "worker-0", "parent-claim")
    assert credential.task_id == "parent"
    assert not repo.claim("worker-1", "blocked", 0).accepted
    assert repo.start(credential, "start", 0).accepted
    assert repo.complete(credential, "done", 1).accepted
    assert _credential(repo, "worker-1", "child-claim", now=1).task_id == "child"


def test_event_failure_rolls_back_assignment_and_retry_is_not_poisoned(database: Database) -> None:
    repo = TaskRepository(database)
    before = _ready(repo, "a")
    with database.transaction() as connection:
        connection.execute(
            "ALTER TABLE task_events ADD CONSTRAINT test_refuse_claim "
            "CHECK (event_kind <> 'claimed')"
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        repo.claim("worker-0", "claim", 0)
    assert repo.get("a") == before
    with database.transaction() as connection:
        connection.execute("ALTER TABLE task_events DROP CONSTRAINT test_refuse_claim")
    assert repo.claim("worker-0", "claim", 0).accepted


def test_request_id_reuse_with_different_content_is_rejected(database: Database) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    first = repo.claim("worker-0", "request-1", 0)
    assert repo.claim("worker-0", "request-1", 1).replayed
    with pytest.raises(TaskConflictError):
        repo.claim("worker-1", "request-1", 1)
    assert first.task is not None
    assert repo.get("absent") is None
    with pytest.raises(TaskNotFoundError):
        repo.start(TaskCredential("absent", "worker-0", 1), "unknown", 1)


def test_worker_closes_transactions_before_handler_and_does_not_repeat_it(
    database: Database,
) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    handled: list[str] = []

    def handler(task: TaskRecord) -> HandlerOutcome:
        with database.transaction() as connection:
            row = connection.execute(
                "SELECT state FROM tasks WHERE task_id=%s FOR UPDATE", (task.task_id,)
            ).fetchone()
            assert row == ("EXECUTING",)
        handled.append(task.task_id)
        return HandlerOutcome.DONE

    assert run_once(repo, "worker-0", "request-1", lambda: 0, handler).status == WorkerStatus.DONE
    assert (
        run_once(repo, "worker-0", "request-1", lambda: 1, handler).status == WorkerStatus.REPLAYED
    )
    assert handled == ["a"]


def test_old_worker_finishing_after_reassignment_is_stale(database: Database) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    ticks = [0]

    def delayed_handler(task: TaskRecord) -> HandlerOutcome:
        ticks[0] = 1
        assert repo.recover(1)[0].task_id == task.task_id
        replacement = _credential(repo, "worker-1", "replacement", now=1)
        assert repo.start(replacement, "replacement-start", 1).accepted
        return HandlerOutcome.DONE

    result = run_once(repo, "worker-0", "old", lambda: ticks[0], delayed_handler, lease_ticks=1)
    assert result.status == WorkerStatus.STALE
    task = repo.get("a")
    assert task is not None and task.worker_id == "worker-1" and task.token == 2


def test_concurrent_sweepers_do_not_recover_a_task_twice(database: Database) -> None:
    repo = TaskRepository(database)
    for number in range(4):
        _ready(repo, f"task-{number}")
        _credential(repo, f"worker-{number}", f"claim-{number}", lease_ticks=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda _: repo.recover(1, limit=2), range(2), timeout=20))
    recovered = [task.task_id for batch in batches for task in batch]
    assert len(recovered) == len(set(recovered)) == 4


def test_handler_failure_does_not_stop_processing_other_tasks(database: Database) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    _ready(repo, "b")

    def broken_handler(task: TaskRecord) -> HandlerOutcome:
        raise RuntimeError("synthetic handler failure")

    failed = run_once(repo, "worker-0", "bad", lambda: 0, broken_handler)
    assert failed.status == WorkerStatus.FAILED and failed.task_id == "a"
    healthy = run_once(repo, "worker-0", "good", lambda: 1, lambda task: HandlerOutcome.DONE)
    assert healthy.status == WorkerStatus.DONE and healthy.task_id == "b"


def test_abrupt_worker_process_exit_leaves_a_recoverable_durable_attempt(
    database: Database,
) -> None:
    repo = TaskRepository(database)
    _ready(repo, "a")
    probe = """
import os
import sys
from waggle.db.connection import Database
from waggle.db.tasks import TaskRepository
root = Database.from_environ(os.environ)
repo = TaskRepository(Database(root.dsn, schema=sys.argv[1]))
assert repo.claim('worker-dead', 'crashed', 0, lease_ticks=1).accepted
os._exit(23)
"""
    child = subprocess.run(
        [sys.executable, "-c", probe, database.schema],
        env={"DATABASE_URL": database.dsn},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert child.returncode == 23, child.stderr
    abandoned = repo.get("a")
    assert abandoned is not None and abandoned.worker_id == "worker-dead"
    old = abandoned.credential()
    assert repo.recover(1)[0].state == TaskState.APPROVED
    new = _credential(repo, "worker-new", "reassigned", now=1)
    assert new.token == old.token + 1
    assert not repo.complete(old, "stale-process", 1).accepted
