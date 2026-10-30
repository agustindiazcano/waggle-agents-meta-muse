import json
import subprocess
from pathlib import Path

import pytest

from waggle import tasks


class Recorder:
    """Stand-in for subprocess.run that records commands and returns a chosen exit code."""

    def __init__(self, codes: list[int] | None = None) -> None:
        self.commands: list[list[str]] = []
        self._codes = codes or []

    def __call__(self, cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        code = self._codes.pop(0) if self._codes else 0
        return subprocess.CompletedProcess(cmd, code)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr("waggle.tasks.subprocess.run", rec)
    return rec


def test_lint_runs_ruff_check_and_format_check(recorder: Recorder) -> None:
    assert tasks.lint() == 0
    assert [c[3] for c in recorder.commands] == ["check", "format"]


def test_typecheck_runs_mypy(recorder: Recorder) -> None:
    assert tasks.typecheck() == 0
    assert recorder.commands[0][2] == "mypy"


def test_test_target_excludes_heavy_and_llm(recorder: Recorder) -> None:
    assert tasks.test() == 0
    assert recorder.commands[0][-2:] == ["-m", "not heavy and not llm"]


def test_ci_runs_everything_in_order(recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("waggle.tasks._write_ci_stamp", lambda: None)
    assert tasks.ci() == 0
    names = [c[2] if len(c) > 2 else Path(c[0]).stem for c in recorder.commands]
    assert names == ["ruff", "ruff", "mypy", "pytest", "lint-imports"]


def test_ci_stops_at_first_failure(recorder: Recorder) -> None:
    recorder._codes = [0, 3]
    assert tasks.ci() == 3
    assert len(recorder.commands) == 2


def test_venv_tool_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        tasks.venv_tool("definitely-not-installed-tool")


@pytest.mark.parametrize("target", ["experiments-dev", "report"])
def test_placeholder_targets_succeed(target: str) -> None:
    assert tasks.PLACEHOLDER_TARGETS[target]() == 0


def _result(results_dir: Path, configuration: str = "placeholder") -> Path:
    return results_dir / "placeholder" / "heldout" / f"{configuration}.json"


def test_experiments_test_writes_heldout_result(tmp_path: Path) -> None:
    assert tasks.experiments_test(["--results-dir", str(tmp_path)]) == 0
    data = json.loads(_result(tmp_path).read_text(encoding="utf-8"))
    assert data["seed_set"] == "heldout"
    assert data["forced"] is False
    assert data["configuration"] == "placeholder"
    assert data["commit"]
    assert data["date"]


def test_experiments_test_refuses_to_overwrite(tmp_path: Path) -> None:
    assert tasks.experiments_test(["--results-dir", str(tmp_path)]) == 0
    before = _result(tmp_path).read_text(encoding="utf-8")
    assert tasks.experiments_test(["--results-dir", str(tmp_path)]) != 0
    assert _result(tmp_path).read_text(encoding="utf-8") == before


def test_experiments_test_force_overwrites_and_records_it(tmp_path: Path) -> None:
    assert tasks.experiments_test(["--results-dir", str(tmp_path)]) == 0
    assert tasks.experiments_test(["--results-dir", str(tmp_path), "--force"]) == 0
    data = json.loads(_result(tmp_path).read_text(encoding="utf-8"))
    assert data["forced"] is True


def test_experiments_test_other_configuration_is_independent(tmp_path: Path) -> None:
    assert tasks.experiments_test(["--results-dir", str(tmp_path)]) == 0
    other = ["--results-dir", str(tmp_path), "--configuration", "ablation-a"]
    assert tasks.experiments_test(other) == 0
    assert _result(tmp_path, "ablation-a").exists()


def test_ci_writes_the_stamp_only_after_a_green_run(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[int] = []
    monkeypatch.setattr("waggle.tasks._write_ci_stamp", lambda: written.append(1))
    assert tasks.ci() == 0
    assert written == [1]


def test_ci_writes_no_stamp_when_a_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = Recorder(codes=[0, 0, 1])
    monkeypatch.setattr("waggle.tasks.subprocess.run", rec)
    written: list[int] = []
    monkeypatch.setattr("waggle.tasks._write_ci_stamp", lambda: written.append(1))
    assert tasks.ci() == 1
    assert written == []


def test_stamp_holds_the_head_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        out = "abc123\n" if "HEAD" in cmd else str(git_dir) + "\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    monkeypatch.setattr("waggle.tasks.subprocess.run", fake_run)
    tasks._write_ci_stamp()
    assert (git_dir / "waggle_ci_stamp").read_text(encoding="utf-8").strip() == "abc123"
