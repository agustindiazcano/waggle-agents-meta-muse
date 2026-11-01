"""Cloud-only end to end: simulator, bridge, trusted store, worker and fenced handoff.

A handoff task can finish only when the simulated robot is alone in the zone. The handler is a
trusted driver that steps the simulator; it never states occupancy itself.
"""

import pytest

from waggle.coordination.corridors import CorridorRequest, Direction
from waggle.coordination.task_model import TaskDefinition, TaskRecord, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.occupancy import TrustedStateRepository
from waggle.db.tasks import TaskRepository
from waggle.experiments.corridor_admission import build_s03_admission
from waggle.experiments.sim_bridge import SimTrustedBridge
from waggle.handoff_finisher import HandoffFinisher
from waggle.worker import HandlerOutcome, WorkerResult, WorkerStatus, run_once

pytestmark = pytest.mark.heavy

_MAX_STEPS = 400


def _scenario(db: Database):  # type: ignore[no-untyped-def]  # test helper returning a tuple
    sim, admission, _ = build_s03_admission(7)
    zone = admission.zones[0].id
    corridors = CorridorRepository(db)
    corridors.register(tuple(z.id for z in admission.zones))
    trusted = TrustedStateRepository(db)
    bridge = SimTrustedBridge(trusted, admission)
    sim.step()
    bridge.publish(sim.state)
    granted = corridors.reserve(
        CorridorRequest("robot-0", (zone,), Direction.FORWARD),
        sim.state.tick,
        trusted.observe((zone,), sim.state.tick),
        lease_ticks=1000,
    )
    assert granted.granted
    tasks = TaskRepository(db)
    tasks.create(TaskDefinition("delivery", handoff_zone=zone))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        tasks.advance("delivery", state, f"delivery-{state.value}", 0)
    finisher = HandoffFinisher(tasks, corridors, trusted)
    return sim, admission, bridge, trusted, tasks, finisher, zone


def _run(tasks, trusted, finisher, handler) -> WorkerResult:  # type: ignore[no-untyped-def]
    return run_once(
        tasks, "robot-0", "claim-1", trusted.now_tick, handler, complete=finisher.complete
    )


def test_the_handoff_finishes_only_after_the_simulated_robot_arrives(database: Database) -> None:
    sim, admission, bridge, trusted, tasks, finisher, zone = _scenario(database)
    start_tick = sim.state.tick

    def drive(task: TaskRecord) -> HandlerOutcome:
        for _ in range(_MAX_STEPS):
            sim.step()
            bridge.publish(sim.state)
            if admission.occupancy(sim.state)[0].occupants == ("robot-0",):
                return HandlerOutcome.DONE
        return HandlerOutcome.FAILED

    result = _run(tasks, trusted, finisher, drive)
    assert result == WorkerResult(WorkerStatus.DONE, "delivery")
    done = tasks.get("delivery")
    assert done is not None and done.state == TaskState.DONE
    assert trusted.now_tick() > start_tick
    assert trusted.observe((zone,), trusted.now_tick())[0].occupants == ("robot-0",)


def test_a_handler_that_claims_done_before_arrival_cannot_finish_the_handoff(
    database: Database,
) -> None:
    sim, admission, _bridge, trusted, tasks, finisher, _zone = _scenario(database)
    assert admission.occupancy(sim.state)[0].occupants == ()

    result = _run(tasks, trusted, finisher, lambda task: HandlerOutcome.DONE)

    assert result.status == WorkerStatus.STALE
    task = tasks.get("delivery")
    assert task is not None and task.state == TaskState.EXECUTING
