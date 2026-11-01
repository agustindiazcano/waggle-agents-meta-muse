"""E2 no-fencing baseline: the decision it makes, and proof that production cannot import it."""

import ast
from dataclasses import replace
from pathlib import Path

from waggle.coordination.task_model import (
    TaskCredential,
    TaskRecord,
    TaskState,
    claim_task,
    worker_transition,
)
from waggle.experiments.e2_baseline import baseline_transition

SRC = Path(__file__).resolve().parents[3] / "src" / "waggle"


def _assigned(worker: str = "w1", token_before: int = 0, lease: int = 10) -> TaskRecord:
    approved = TaskRecord("t1", state=TaskState.APPROVED, token=token_before)
    return claim_task(approved, worker, 0, lease)


def _stale(task: TaskRecord) -> TaskCredential:
    """A credential of the same worker from an earlier attempt of the same task."""
    return TaskCredential(task.task_id, task.worker_id or "w1", task.token - 1)


def test_real_transition_denies_a_stale_token_of_the_same_worker() -> None:
    task = _assigned(token_before=1)
    assert worker_transition(task, _stale(task), TaskState.EXECUTING, 1) is None


def test_baseline_accepts_a_stale_token_of_the_same_worker() -> None:
    task = _assigned(token_before=1)
    result = baseline_transition(task, _stale(task), TaskState.EXECUTING, 1)
    assert result is not None
    assert result.state is TaskState.EXECUTING
    assert result.token == task.token


def test_baseline_matches_the_real_transition_for_the_current_token() -> None:
    task = _assigned()
    credential = task.credential()
    assert baseline_transition(task, credential, TaskState.EXECUTING, 1) == worker_transition(
        task, credential, TaskState.EXECUTING, 1
    )


def test_baseline_still_checks_the_worker() -> None:
    task = _assigned()
    other = TaskCredential(task.task_id, "w2", task.token)
    assert baseline_transition(task, other, TaskState.EXECUTING, 1) is None


def test_baseline_still_checks_expiry_with_the_clock_it_is_given() -> None:
    task = _assigned(lease=10)
    credential = task.credential()
    assert baseline_transition(task, credential, TaskState.EXECUTING, 10) is None
    assert baseline_transition(task, credential, TaskState.EXECUTING, 9) is not None


def test_baseline_still_checks_the_state_machine() -> None:
    task = _assigned()
    assert baseline_transition(task, task.credential(), TaskState.DONE, 1) is None


def test_baseline_rejects_an_inactive_task() -> None:
    task = replace(_assigned(), state=TaskState.APPROVED, worker_id=None, expires_tick=None)
    credential = TaskCredential("t1", "w1", 1)
    assert baseline_transition(task, credential, TaskState.EXECUTING, 1) is None


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_production_module_imports_the_baseline() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if "experiments" not in path.relative_to(SRC).parts
        and any(name.startswith("waggle.experiments") for name in _imports(path))
    ]
    assert offenders == []


def test_only_experiments_modules_import_the_baseline() -> None:
    allowed = {"e2_baseline.py", "e2_chaos.py"}
    offenders = [
        path.name
        for path in (SRC / "experiments").glob("*.py")
        if path.name not in allowed and any(name.endswith("e2_baseline") for name in _imports(path))
    ]
    assert offenders == []
