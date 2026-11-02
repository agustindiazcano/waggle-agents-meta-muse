"""E2 handoff baseline: the decision it makes, and proof that production cannot import it."""

import ast
from pathlib import Path

from waggle.coordination.corridors import CorridorZone, Direction, ZoneObservation, ZoneToken
from waggle.coordination.handoff import authorize_handoff
from waggle.coordination.leases import LeaseState
from waggle.coordination.task_model import TaskCredential, TaskRecord, TaskState, claim_task
from waggle.experiments.e2_handoff_baseline import live_credentials

SRC = Path(__file__).resolve().parents[3] / "src" / "waggle"


def _executing(token_before: int = 1) -> TaskRecord:
    approved = TaskRecord("t1", state=TaskState.APPROVED, token=token_before)
    assigned = claim_task(approved, "w1", 0, 10)
    return TaskRecord(
        assigned.task_id,
        state=TaskState.EXECUTING,
        attempt=assigned.attempt,
        token=assigned.token,
        worker_id="w1",
        expires_tick=assigned.expires_tick,
        observed_tick=assigned.observed_tick,
    )


def _zone(token: int = 5) -> CorridorZone:
    return CorridorZone(
        LeaseState("dock", token=token, holder="w1", expires_tick=10), Direction.FORWARD
    )


def _inside(tick: int = 1) -> ZoneObservation:
    return ZoneObservation("dock", tick, ("w1",))


def test_real_check_denies_a_stale_task_token_and_a_stale_zone_token() -> None:
    task, zone = _executing(), _zone()
    stale = TaskCredential("t1", "w1", task.token - 1)
    assert not authorize_handoff(task, stale, zone, ZoneToken("dock", 5), _inside(), 1)
    assert not authorize_handoff(task, task.credential(), zone, ZoneToken("dock", 4), _inside(), 1)


def test_baseline_replaces_both_tokens_with_the_live_ones() -> None:
    task, zone = _executing(), _zone()
    stale = TaskCredential("t1", "w1", task.token - 1)
    credential, token = live_credentials(task, stale, zone, ZoneToken("dock", 4))
    assert credential == task.credential()
    assert token == ZoneToken("dock", 5)
    assert authorize_handoff(task, credential, zone, token, _inside(), 1)


def test_baseline_still_checks_the_worker_and_the_occupancy() -> None:
    task, zone = _executing(), _zone()
    other = TaskCredential("t1", "w2", task.token)
    credential, token = live_credentials(task, other, zone, ZoneToken("dock", 5))
    assert not authorize_handoff(task, credential, zone, token, _inside(), 1)
    own, own_token = live_credentials(task, task.credential(), zone, ZoneToken("dock", 5))
    assert not authorize_handoff(task, own, zone, own_token, ZoneObservation("dock", 1, None), 1)
    assert not authorize_handoff(task, own, zone, own_token, ZoneObservation("dock", 1, ()), 1)


def test_baseline_still_checks_expiry_with_the_clock_it_is_given() -> None:
    task, zone = _executing(), _zone()
    credential, token = live_credentials(task, task.credential(), zone, ZoneToken("dock", 5))
    assert authorize_handoff(task, credential, zone, token, _inside(9), 9)
    assert not authorize_handoff(task, credential, zone, token, _inside(10), 10)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_production_module_imports_experiments() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "experiments" not in path.relative_to(SRC).parts
        and any(name.startswith("waggle.experiments") for name in _imports(path))
    ]
    assert offenders == []


def test_only_the_handoff_runner_imports_the_handoff_baseline() -> None:
    allowed = {"e2_handoff_baseline.py", "e2_handoff.py", "e2_handoff_scenes.py"}
    offenders = [
        path.name
        for path in (SRC / "experiments").glob("*.py")
        if path.name not in allowed
        and any(name.endswith("e2_handoff_baseline") for name in _imports(path))
    ]
    assert offenders == []
