"""E2 baseline without fencing: the lease is checked in the worker process and no token is compared.

This is the comparison arm of the chaos harness (``docs/E2_CHAOS_DESIGN.md``). It exists only so the
oracle has something that must fail: a worker reads the task, decides in its own process from the
clock it was given, and writes in a second transaction. Between the two the attempt can expire, be
recovered and be claimed again, and the old credential still passes because only the worker name
and the expiry are looked at.

It is never imported by production code: ``tests/unit/experiments/test_e2_baseline.py`` and the
``e2-baseline-isolated`` import contract in ``pyproject.toml`` enforce that. It changes none of the
production repositories. The event it writes carries the token of the credential that was sent, so
the oracle can see which attempt the caller believed it held; the task row keeps the live token.
Handoff tasks keep their own baseline in a later branch, so this class does not guard them.
"""

from dataclasses import replace

from waggle.coordination.task_model import (
    TaskCredential,
    TaskRecord,
    TaskState,
    counter,
    identifier,
    worker_transition,
)
from waggle.db.tasks import (
    _COLUMNS,
    TaskNotFoundError,
    TaskRepository,
    TaskResult,
    _cached,
    _decode,
    _event,
    _signature,
    _store,
)


def baseline_transition(
    task: TaskRecord, credential: TaskCredential, target: TaskState, now_tick: int
) -> TaskRecord | None:
    """The production transition with the token check removed: worker, expiry and state only.

    It reuses ``worker_transition`` with the token of the stored task substituted into the
    credential, so every other rule stays the same and cannot drift from production.
    """
    return worker_transition(task, replace(credential, token=task.token), target, now_tick)


class NoFencingTaskRepository(TaskRepository):
    """Task repository that checks the lease outside the write and carries no token."""

    def _work(
        self, credential: TaskCredential, target: TaskState, request_id: str, now_tick: int
    ) -> TaskResult:
        identifier(request_id)
        counter(now_tick)
        event_id = "request:" + request_id
        signature = _signature(
            "work", credential.task_id, credential.worker_id, credential.token, target.value
        )
        with self.database.transaction() as connection:
            cached = _cached(connection, event_id, signature)
            if cached is not None:
                return cached
            row = connection.execute(
                "SELECT " + _COLUMNS + " FROM tasks WHERE task_id=%s", (credential.task_id,)
            ).fetchone()
            if row is None:
                raise TaskNotFoundError("task not found")
            seen = _decode(row)
        task = baseline_transition(seen, credential, target, now_tick)
        if task is None:
            return TaskResult(False, seen)
        with self.database.transaction() as connection:
            cached = _cached(connection, event_id, signature)
            if cached is not None:
                return cached
            _store(connection, task)
            recorded = replace(task, token=credential.token)
            _event(connection, event_id, signature, target.value.lower(), seen.state, recorded)
            return TaskResult(True, task)
