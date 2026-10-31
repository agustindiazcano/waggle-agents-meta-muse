"""Cloud-only transactional handoff checks against PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from waggle.coordination.corridors import CorridorRequest, Direction, ZoneObservation, ZoneToken
from waggle.coordination.task_model import TaskCredential, TaskDefinition, TaskState
from waggle.db.connection import Database
from waggle.db.corridors import CorridorRepository
from waggle.db.tasks import TaskConflictError, TaskRepository

pytestmark = pytest.mark.heavy


def _ready(
    repo: TaskRepository, task_id: str, *, zone: str | None = None, deps: tuple[str, ...] = ()
) -> None:
    repo.create(TaskDefinition(task_id, dependencies=deps, handoff_zone=zone))
    for state in (TaskState.SCREENED, TaskState.REVIEWED, TaskState.APPROVED):
        repo.advance(task_id, state, f"{task_id}-{state.value}", 0)


def _setup(db: Database) -> tuple[TaskRepository, TaskCredential, ZoneToken]:
    corridors = CorridorRepository(db)
    corridors.register(("dock",))
    granted = corridors.reserve(
        CorridorRequest("robot", ("dock",), Direction.FORWARD),
        0,
        (ZoneObservation("dock", 0, ()),),
    )
    assert granted.granted
    repo = TaskRepository(db)
    _ready(repo, "delivery", zone="dock")
    _ready(repo, "next", deps=("delivery",))
    result = repo.claim("robot", "claim", 0, lease_ticks=10)
    assert result.task is not None
    credential = result.task.credential()
    assert repo.start(credential, "start", 0).accepted
    return repo, credential, granted.tokens[0]


def test_handoff_is_required_and_replay_does_not_duplicate(database: Database) -> None:
    repo, credential, token = _setup(database)
    assert not repo.complete(credential, "ordinary", 1).accepted
    assert not repo.claim("other", "before", 1).accepted
    observation = ZoneObservation("dock", 1, ("robot",))
    result = repo.complete_handoff(credential, token, observation, "h1", 1)
    assert result.accepted and not result.replayed
    assert repo.complete_handoff(credential, token, observation, "h1", 1).replayed
    assert repo.claim("other", "after", 1).accepted
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM task_events WHERE event_kind='handoff'"
        ).fetchone() == (1,)
    with pytest.raises(TaskConflictError):
        repo.complete_handoff(credential, ZoneToken("dock", token.token + 1), observation, "h1", 1)


@pytest.mark.parametrize("case", ["task", "zone", "missing", "stale", "intruder", "expired"])
def test_invalid_evidence_never_finishes_or_unblocks(database: Database, case: str) -> None:
    repo, credential, token = _setup(database)
    if case == "task":
        credential = TaskCredential("delivery", "robot", credential.token + 1)
    if case == "zone":
        token = ZoneToken("dock", token.token + 1)
    now = 10 if case == "expired" else 1
    occupancy = None if case == "missing" else (("other",) if case == "intruder" else ("robot",))
    observed = 0 if case == "stale" else now
    result = repo.complete_handoff(
        credential, token, ZoneObservation("dock", observed, occupancy), "bad", now
    )
    assert not result.accepted
    delivery = repo.get("delivery")
    assert delivery is not None and delivery.state == TaskState.EXECUTING
    assert not repo.claim("other", "blocked", 1).accepted


def test_concurrent_duplicate_handoff_inserts_once(database: Database) -> None:
    repo, credential, token = _setup(database)

    def deliver() -> bool:
        return repo.complete_handoff(
            credential, token, ZoneObservation("dock", 1, ("robot",)), "same", 1
        ).replayed

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: deliver(), range(2), timeout=20)) == [False, True]
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) FROM task_events WHERE event_kind='handoff'"
        ).fetchone() == (1,)


def test_missing_zone_and_definition_reuse_fail_closed(database: Database) -> None:
    repo = TaskRepository(database)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        repo.create(TaskDefinition("bad", handoff_zone="missing"))
    assert repo.get("bad") is None
    CorridorRepository(database).register(("dock",))
    repo.create(TaskDefinition("delivery", handoff_zone="dock"))
    with pytest.raises(TaskConflictError):
        repo.create(TaskDefinition("delivery"))


def test_event_failure_rolls_back_completion(database: Database) -> None:
    repo, credential, token = _setup(database)
    with database.transaction() as connection:
        connection.execute("""CREATE FUNCTION reject_handoff() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN IF NEW.event_kind = 'handoff' THEN
            RAISE EXCEPTION 'test rejection'; END IF; RETURN NEW; END $$""")
        connection.execute("""CREATE TRIGGER reject_handoff BEFORE INSERT ON task_events
            FOR EACH ROW EXECUTE FUNCTION reject_handoff()""")
    with pytest.raises(psycopg.errors.RaiseException):
        repo.complete_handoff(credential, token, ZoneObservation("dock", 1, ("robot",)), "fail", 1)
    delivery = repo.get("delivery")
    assert delivery is not None and delivery.state == TaskState.EXECUTING
    assert not repo.claim("other", "blocked", 1).accepted
