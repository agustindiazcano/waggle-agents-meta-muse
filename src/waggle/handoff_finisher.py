"""Completion for workers: ordinary tasks complete normally, handoff tasks only when fenced.

``HandoffFinisher.complete`` is passed to ``run_once`` as its ``complete`` argument. For a task
with a handoff requirement it takes the zone token the worker itself holds from the corridor
table and the occupancy evidence from the trusted store, then calls the atomic
``complete_handoff``. The worker supplies neither the token nor the evidence, and the
repository repeats every check inside its locked transaction. A worker that does not hold the
zone is refused without a call. A replay after the lease was released is refused here;
``run_once`` does not call completion again for a replayed claim.
"""

from typing import Protocol

from waggle.coordination.corridors import CorridorState, ZoneObservation, ZoneToken
from waggle.coordination.task_model import TaskCredential
from waggle.db.tasks import TaskRepository, TaskResult


class CorridorView(Protocol):
    """The read side of ``CorridorRepository``."""

    def snapshot(self) -> CorridorState:
        """The current zone table."""
        ...


class OccupancySource(Protocol):
    """Trusted occupancy evidence."""

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        """One observation per zone."""
        ...


class HandoffFinisher:
    """Completes a task, with a fenced handoff when the task requires one."""

    def __init__(
        self, tasks: TaskRepository, corridors: CorridorView, occupancy: OccupancySource
    ) -> None:
        self._tasks = tasks
        self._corridors = corridors
        self._occupancy = occupancy

    def complete(self, credential: TaskCredential, request_id: str, now_tick: int) -> TaskResult:
        """Complete ``credential``'s task; a refused handoff leaves the task unchanged."""
        zone_id = self._tasks.handoff_zone(credential.task_id)
        if zone_id is None:
            return self._tasks.complete(credential, request_id, now_tick)
        held = next(
            (
                zone.lease
                for zone in self._corridors.snapshot().zones
                if zone.lease.resource_id == zone_id and zone.lease.holder == credential.worker_id
            ),
            None,
        )
        if held is None:
            return TaskResult(False, self._tasks.get(credential.task_id))
        observation = self._occupancy.observe((zone_id,), now_tick)[0]
        return self._tasks.complete_handoff(
            credential, ZoneToken(zone_id, held.token), observation, request_id, now_tick
        )
