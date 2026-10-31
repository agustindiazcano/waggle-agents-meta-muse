"""Transactional task queue, event history and bounded expired-attempt recovery."""

import json
from dataclasses import dataclass
from typing import LiteralString, cast

import psycopg

from waggle.coordination.corridors import ZoneObservation, ZoneToken
from waggle.coordination.handoff import authorize_handoff
from waggle.coordination.task_model import (
    TaskCredential,
    TaskDefinition,
    TaskRecord,
    TaskState,
    advance_task,
    claim_task,
    counter,
    identifier,
    recover_task,
    worker_transition,
)
from waggle.db.connection import Database, Row
from waggle.db.corridors import _lock

_COLUMNS: LiteralString = (
    "task_id,state,attempt,token,worker_id,expires_tick,observed_tick,max_attempts,priority"
)
_REQUEST_SEED = 19730404
_WORKER_SEED = 19730405
_CREATE_SEED = 19730406


class TaskConflictError(ValueError):
    """A task or successful request id was reused with different immutable content."""


class TaskNotFoundError(LookupError):
    """The requested task does not exist; this is not an empty-queue result."""


@dataclass(frozen=True)
class TaskResult:
    """Transition result; replayed success is historical and causes no new effect."""

    accepted: bool
    task: TaskRecord | None = None
    replayed: bool = False


def _decode(row: Row) -> TaskRecord:
    # PostgreSQL column types establish these types; TaskRecord validates the state.
    return TaskRecord(
        task_id=cast(str, row[0]),
        state=TaskState(cast(str, row[1])),
        attempt=cast(int, row[2]),
        token=cast(int, row[3]),
        worker_id=cast(str | None, row[4]),
        expires_tick=cast(int | None, row[5]),
        observed_tick=cast(int, row[6]),
        max_attempts=cast(int, row[7]),
        priority=cast(int, row[8]),
    )


def _values(task: TaskRecord) -> Row:
    return (
        task.task_id,
        task.state.value,
        task.attempt,
        task.token,
        task.worker_id,
        task.expires_tick,
        task.observed_tick,
        task.max_attempts,
        task.priority,
    )


def _signature(*values: object) -> str:
    return json.dumps(values, separators=(",", ":"))


def _lock_name(connection: psycopg.Connection[Row], name: str, seed: int) -> None:
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,%s))", (name, seed))


def _task(connection: psycopg.Connection[Row], task_id: str) -> TaskRecord:
    row = connection.execute(
        "SELECT " + _COLUMNS + " FROM tasks WHERE task_id=%s FOR UPDATE", (task_id,)
    ).fetchone()
    if row is None:
        raise TaskNotFoundError("task not found")
    return _decode(row)


def _cached(
    connection: psycopg.Connection[Row], event_id: str, signature: str
) -> TaskResult | None:
    _lock_name(connection, event_id, _REQUEST_SEED)
    row = connection.execute(
        "SELECT signature," + _COLUMNS + " FROM task_events WHERE event_id=%s", (event_id,)
    ).fetchone()
    if row is None:
        return None
    if row[0] != signature:
        raise TaskConflictError("request id has different content")
    return TaskResult(True, _decode(row[1:]), replayed=True)


def _event(
    connection: psycopg.Connection[Row],
    event_id: str,
    signature: str,
    kind: str,
    previous: TaskState | None,
    task: TaskRecord,
) -> None:
    connection.execute(
        "INSERT INTO task_events (event_id,signature,event_kind,from_state," + _COLUMNS + ") "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            event_id,
            signature,
            kind,
            previous.value if previous is not None else None,
            *_values(task),
        ),
    )


def _store(connection: psycopg.Connection[Row], task: TaskRecord) -> None:
    connection.execute(
        "UPDATE tasks SET state=%s,attempt=%s,token=%s,worker_id=%s,expires_tick=%s,"
        "observed_tick=%s "
        "WHERE task_id=%s",
        (
            task.state.value,
            task.attempt,
            task.token,
            task.worker_id,
            task.expires_tick,
            task.observed_tick,
            task.task_id,
        ),
    )


class TaskRepository:
    """Persist validated transitions; callers must supply trusted ticks and identities."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, definition: TaskDefinition, now_tick: int = 0) -> TaskRecord:
        """Insert once with existing dependencies; immutable definitions cannot form cycles."""
        counter(now_tick)
        signature = _signature(
            definition.dependencies, definition.max_attempts, definition.priority
        )
        if definition.handoff_zone is not None:
            signature = _signature(
                definition.dependencies,
                definition.max_attempts,
                definition.priority,
                definition.handoff_zone,
            )
        with self.database.transaction() as connection:
            _lock_name(connection, definition.task_id, _CREATE_SEED)
            row = connection.execute(
                "SELECT "
                + _COLUMNS
                + ",definition_signature FROM tasks WHERE task_id=%s FOR UPDATE",
                (definition.task_id,),
            ).fetchone()
            if row is not None:
                if row[-1] != signature:
                    raise TaskConflictError("task id has different definition")
                return _decode(row[:9])
            if definition.dependencies:
                parents = connection.execute(
                    "SELECT task_id FROM tasks WHERE task_id=ANY(%s)",
                    (list(definition.dependencies),),
                ).fetchall()
                if len(parents) != len(definition.dependencies):
                    raise ValueError("task dependencies must already exist")
            task = TaskRecord(
                definition.task_id,
                max_attempts=definition.max_attempts,
                priority=definition.priority,
                observed_tick=now_tick,
            )
            connection.execute(
                "INSERT INTO tasks (" + _COLUMNS + ",definition_signature) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (*_values(task), signature),
            )
            if definition.handoff_zone is not None:
                connection.execute(
                    "INSERT INTO task_handoffs (task_id,zone_id) VALUES (%s,%s)",
                    (task.task_id, definition.handoff_zone),
                )
            for dependency in definition.dependencies:
                connection.execute(
                    "INSERT INTO task_dependencies (task_id,depends_on) VALUES (%s,%s)",
                    (task.task_id, dependency),
                )
            _event(connection, f"created:{task.task_id}", signature, "created", None, task)
            return task

    def get(self, task_id: str) -> TaskRecord | None:
        """Return one committed snapshot; snapshots never authorize a later effect."""
        identifier(task_id)
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT " + _COLUMNS + " FROM tasks WHERE task_id=%s", (task_id,)
            ).fetchone()
            return _decode(row) if row is not None else None

    def advance(
        self, task_id: str, target: TaskState, request_id: str, now_tick: int
    ) -> TaskResult:
        """Record a review transition; assignment and execution use fenced operations."""
        identifier(task_id)
        identifier(request_id)
        counter(now_tick)
        if not isinstance(target, TaskState):
            raise ValueError("invalid task state")
        event_id, signature = "request:" + request_id, _signature("advance", task_id, target.value)
        with self.database.transaction() as connection:
            cached = _cached(connection, event_id, signature)
            if cached is not None:
                return cached
            previous = _task(connection, task_id)
            task = advance_task(previous, target, now_tick)
            _store(connection, task)
            _event(connection, event_id, signature, "advanced", previous.state, task)
            return TaskResult(True, task)

    def claim(
        self, worker_id: str, request_id: str, now_tick: int, lease_ticks: int = 400
    ) -> TaskResult:
        """Claim one eligible task with SKIP LOCKED; a worker holds at most one attempt."""
        identifier(worker_id)
        identifier(request_id)
        counter(now_tick)
        counter(lease_ticks, 1)
        event_id, signature = "request:" + request_id, _signature("claim", worker_id, lease_ticks)
        with self.database.transaction() as connection:
            cached = _cached(connection, event_id, signature)
            if cached is not None:
                return cached
            _lock_name(connection, worker_id, _WORKER_SEED)
            active = connection.execute(
                "SELECT task_id FROM tasks WHERE worker_id=%s "
                "AND state IN ('ASSIGNED','EXECUTING')",
                (worker_id,),
            ).fetchone()
            if active is not None:
                return TaskResult(False)
            row = connection.execute(
                "SELECT " + _COLUMNS + " FROM tasks t WHERE state='APPROVED' "
                "AND attempt < max_attempts AND NOT EXISTS ("
                "SELECT 1 FROM task_dependencies d JOIN tasks p ON p.task_id=d.depends_on "
                "WHERE d.task_id=t.task_id AND p.state <> 'DONE') "
                "ORDER BY priority DESC,task_id LIMIT 1 FOR UPDATE OF t SKIP LOCKED"
            ).fetchone()
            if row is None:
                return TaskResult(False)
            previous = _decode(row)
            task = claim_task(previous, worker_id, now_tick, lease_ticks)
            _store(connection, task)
            _event(connection, event_id, signature, "claimed", previous.state, task)
            return TaskResult(True, task)

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
            previous = _task(connection, credential.task_id)
            if (
                target == TaskState.DONE
                and connection.execute(
                    "SELECT zone_id FROM task_handoffs WHERE task_id=%s", (credential.task_id,)
                ).fetchone()
                is not None
            ):
                return TaskResult(False, previous)
            task = worker_transition(previous, credential, target, now_tick)
            if task is None:
                return TaskResult(False, previous)
            _store(connection, task)
            _event(connection, event_id, signature, target.value.lower(), previous.state, task)
            return TaskResult(True, task)

    def start(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        """Start only the exact live assigned attempt."""
        return self._work(credential, TaskState.EXECUTING, request_id, now_tick)

    def complete(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        """Complete only the exact live executing attempt, atomically with its event."""
        return self._work(credential, TaskState.DONE, request_id, now_tick)

    def complete_handoff(
        self,
        credential: TaskCredential,
        token: ZoneToken,
        observation: ZoneObservation,
        request_id: str,
        now_tick: int,
    ) -> TaskResult:
        """Record a handoff with task and zone credentials in one transaction.

        Identity, current occupancy and tick must come from trusted adapters. A
        replay is historical and does not reauthorize a physical effect.
        """
        identifier(request_id)
        counter(now_tick)
        event_id = "request:" + request_id
        signature = _signature(
            "handoff",
            credential.task_id,
            credential.worker_id,
            credential.token,
            token.resource_id,
            token.token,
        )
        with self.database.transaction() as connection:
            cached = _cached(connection, event_id, signature)
            if cached is not None:
                return cached
            previous = _task(connection, credential.task_id)
            requirement = connection.execute(
                "SELECT zone_id FROM task_handoffs WHERE task_id=%s", (credential.task_id,)
            ).fetchone()
            if requirement is None or requirement[0] != token.resource_id:
                return TaskResult(False, previous)
            state = _lock(connection, credential.worker_id)
            zone = next(
                (item for item in state.zones if item.lease.resource_id == token.resource_id), None
            )
            if zone is None or not authorize_handoff(
                previous, credential, zone, token, observation, now_tick
            ):
                return TaskResult(False, previous)
            task = worker_transition(previous, credential, TaskState.DONE, now_tick)
            if task is None:
                return TaskResult(False, previous)
            _store(connection, task)
            _event(connection, event_id, signature, "handoff", previous.state, task)
            return TaskResult(True, task)

    def fail(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        """Fail a live assigned or executing attempt without releasing physical zones."""
        return self._work(credential, TaskState.FAILED, request_id, now_tick)

    def recover(self, now_tick: int, *, limit: int = 100) -> tuple[TaskRecord, ...]:
        """Requeue or exhaust expired attempts, skipping rows locked by another worker."""
        counter(now_tick)
        counter(limit, 1, 1000)
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT " + _COLUMNS + " FROM tasks WHERE state IN ('ASSIGNED','EXECUTING') "
                "AND expires_tick<=%s ORDER BY task_id LIMIT %s FOR UPDATE SKIP LOCKED",
                (now_tick, limit),
            ).fetchall()
            recovered: list[TaskRecord] = []
            for row in rows:
                previous = _decode(row)
                task = recover_task(previous, now_tick)
                if task is None:
                    raise RuntimeError("locked task is not eligible for recovery")
                _store(connection, task)
                _event(
                    connection,
                    f"recovery:{task.task_id}:{task.token}",
                    _signature("recover", task.task_id, task.token),
                    "recovered",
                    previous.state,
                    task,
                )
                recovered.append(task)
            return tuple(recovered)
