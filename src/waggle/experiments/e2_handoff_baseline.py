"""E2 handoff baseline: the handoff is authorized outside the write and no token is compared.

This is the comparison arm of the handoff chaos scenes (``docs/E2_CHAOS_DESIGN.md``, branch 6).
It covers only the handoff completion path. ``complete_handoff`` reads the task and the zone in
one transaction without a lock, replaces the task token and the zone token the caller sent with
the live ones, runs the production pure check on that, and writes in a second transaction. The
worker name, the expiry, the task state and the trusted occupancy are still checked, so the only
protection removed is the fencing token. A runner of an expired attempt that shares the worker
name with the live attempt is therefore accepted. Starts and ordinary completions keep the
production behavior, so the oracle isolates the handoff path.

It is never imported by production code: ``tests/unit/experiments/test_e2_handoff_baseline.py``
enforces that with an AST check, and a matching import contract is proposed in the report because
``pyproject.toml`` is outside this task. It changes none of the production repositories. The
event it writes carries the token that was sent, so the oracle sees which attempt the caller
believed it held; the task row keeps the live token.
"""

from dataclasses import replace

from waggle.coordination.corridors import CorridorZone, ZoneObservation, ZoneToken
from waggle.coordination.handoff import authorize_handoff
from waggle.coordination.task_model import (
    TaskCredential,
    TaskRecord,
    TaskState,
    counter,
    identifier,
    worker_transition,
)
from waggle.db.corridors import _read
from waggle.db.tasks import (
    TaskRepository,
    TaskResult,
    _cached,
    _event,
    _signature,
    _store,
    _task,
)


def live_credentials(
    task: TaskRecord, credential: TaskCredential, zone: CorridorZone, token: ZoneToken
) -> tuple[TaskCredential, ZoneToken]:
    """The credential and zone token of the live attempt, keeping the caller's worker and zone."""
    return replace(credential, token=task.token), ZoneToken(token.resource_id, zone.lease.token)


class NoFencingHandoffRepository(TaskRepository):
    """Task repository whose handoff completion checks the lease outside the write."""

    def complete_handoff(
        self,
        credential: TaskCredential,
        token: ZoneToken,
        observation: ZoneObservation,
        request_id: str,
        now_tick: int,
    ) -> TaskResult:
        """Complete a handoff with the live tokens substituted for the ones sent."""
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
            zone = next(
                (z for z in _read(connection).zones if z.lease.resource_id == token.resource_id),
                None,
            )
        if zone is None:
            return TaskResult(False, previous)
        live, live_token = live_credentials(previous, credential, zone, token)
        if not authorize_handoff(previous, live, zone, live_token, observation, now_tick):
            return TaskResult(False, previous)
        task = worker_transition(previous, live, TaskState.DONE, now_tick)
        if task is None:
            return TaskResult(False, previous)
        with self.database.transaction() as connection:
            cached = _cached(connection, event_id, signature)
            if cached is not None:
                return cached
            _store(connection, task)
            recorded = replace(task, token=credential.token)
            _event(connection, event_id, signature, "handoff", previous.state, recorded)
            return TaskResult(True, task)
