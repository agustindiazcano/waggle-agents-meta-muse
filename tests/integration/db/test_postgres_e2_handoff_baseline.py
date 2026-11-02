"""Cloud-only: the oracle counts a stale handoff in the baseline and none in production."""

import pytest

from waggle.coordination.corridors import CorridorRequest, Direction, ZoneObservation, ZoneToken
from waggle.coordination.task_model import TaskCredential, TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.tasks import TaskRepository
from waggle.experiments.e2_handoff_baseline import NoFencingHandoffRepository
from waggle.experiments.e2_handoff_oracle import HandoffReport, judge_handoffs
from waggle.experiments.e2_log import load_oracle_inputs

pytestmark = pytest.mark.heavy

LEASE = 10


def _stale_handoff(
    repo: TaskRepository, corridors: CorridorRepository
) -> tuple[bool, TaskCredential, ZoneToken]:
    """Attempt 1 expires, the same worker claims attempt 2 and enters, then attempt 1 delivers."""
    corridors.register(("dock",))
    repo.create(TaskDefinition("d", handoff_zone="dock"))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        repo.advance("d", state, f"d-{state.value}", 0)
    first = repo.claim("w1", "claim-1", 0, lease_ticks=LEASE)
    assert first.task is not None
    old = first.task.credential()
    old_zone = corridors.reserve(
        CorridorRequest("w1", ("dock",), Direction.FORWARD),
        0,
        (ZoneObservation("dock", 0, ()),),
        LEASE,
    ).tokens[0]
    assert repo.start(old, "start-1", 1).accepted
    assert repo.recover(20)
    corridors.expire(20, (ZoneObservation("dock", 20, ()),))
    second = repo.claim("w1", "claim-2", 21, lease_ticks=LEASE)
    assert second.task is not None
    new_zone = corridors.reserve(
        CorridorRequest("w1", ("dock",), Direction.FORWARD),
        21,
        (ZoneObservation("dock", 21, ()),),
        LEASE,
    ).tokens[0]
    assert new_zone.token > old_zone.token
    assert repo.start(second.task.credential(), "start-2", 22).accepted
    inside = ZoneObservation("dock", 23, ("w1",))
    return repo.complete_handoff(old, old_zone, inside, "late", 23).accepted, old, old_zone


def _report(database: Database) -> HandoffReport:
    events, _ = load_oracle_inputs(database)
    return judge_handoffs(events, {})


def test_production_denies_the_stale_handoff_and_the_oracle_counts_none(
    database: Database,
) -> None:
    accepted, _, _ = _stale_handoff(TaskRepository(database), CorridorRepository(database))
    assert accepted is False
    assert _report(database) == HandoffReport(0, 0, 0, 0)


def test_baseline_accepts_the_stale_handoff_and_the_oracle_counts_it(
    database: Database,
) -> None:
    accepted, _, _ = _stale_handoff(
        NoFencingHandoffRepository(database), CorridorRepository(database)
    )
    assert accepted is True
    assert _report(database) == HandoffReport(1, 1, 0, 1)


def test_baseline_replay_of_the_same_request_writes_one_event(database: Database) -> None:
    repo = NoFencingHandoffRepository(database)
    accepted, old, old_zone = _stale_handoff(repo, CorridorRepository(database))
    assert accepted
    inside = ZoneObservation("dock", 23, ("w1",))
    assert repo.complete_handoff(old, old_zone, inside, "late", 23).replayed
    assert _report(database).handoffs_accepted == 1
