"""Cloud mutation campaign contract and failure reporting."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from waggle.experiments.e9_mutation import prepare_campaign, summarize


def test_prepare_isolates_sources_and_selects_only_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src/waggle/control").mkdir(parents=True)
    (root / "src/waggle/validation").mkdir()
    (root / "tests/unit/control").mkdir(parents=True)
    (root / "tests/support").mkdir()
    (root / "src/waggle/control/rule.py").write_text("VALUE = 1\n")
    (root / "src/waggle/validation/rule.py").write_text("VALUE = 2\n")
    (root / "pyproject.toml").write_text("[project]\nname = 'toy'\n")
    dest = tmp_path / "copy"
    prepare_campaign(root, dest, "control")
    config = (dest / "setup.cfg").read_text()
    assert "src/waggle/validation/rule.py" in config
    assert "tests/unit/control" in config
    assert "paths_to_mutate=src/waggle" in config
    (dest / "src/waggle/control/rule.py").write_text("VALUE = 9\n")
    assert (root / "src/waggle/control/rule.py").read_text() == "VALUE = 1\n"


def test_prepare_rejects_unsupported_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="target"):
        prepare_campaign(tmp_path, tmp_path / "copy", "mcp_server")


def test_summary_keeps_all_statuses_and_never_counts_errors_as_kills(tmp_path: Path) -> None:
    meta = tmp_path / "rule.py.meta"
    meta.write_text(
        json.dumps(
            {
                "exit_code_by_key": {
                    "a": 1,
                    "b": 0,
                    "c": 3,
                    "d": 255,
                    "e": None,
                    "f": 33,
                }
            }
        )
    )
    report = summarize(tmp_path, target="control", commit="abc", date="2026-11-04")
    assert report["generated"] == 6
    assert report["killed"] == 1
    assert report["survived"] == ["b"]
    assert report["kill_ratio"] == 1 / 6
    assert len(report["outcomes"]) == 6
    assert report["complete"] is False
    assert report["model_ids"] == []


def test_empty_or_invalid_metadata_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no mutants"):
        summarize(tmp_path, target="control", commit="abc", date="2026-11-04")
    (tmp_path / "x.py.meta").write_text('{"exit_code_by_key": {"x": 99}}')
    with pytest.raises(ValueError, match="exit code"):
        summarize(tmp_path, target="control", commit="abc", date="2026-11-04")


def test_execution_refuses_local_campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import waggle.experiments.e9_mutation as module

    monkeypatch.setattr("waggle.experiments.e9_mutation.sys.platform", "win32")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(RuntimeError, match="Linux GitHub Actions"):
        module.main(["--target", "control", "--out", str(tmp_path / "out")])


def test_missing_mutation_tool_raises_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from importlib.metadata import PackageNotFoundError

    import waggle.experiments.e9_mutation as module

    monkeypatch.setattr("waggle.experiments.e9_mutation.sys.platform", "linux")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    def missing(_name: str) -> str:
        raise PackageNotFoundError("mutmut")

    monkeypatch.setattr(module, "version", missing)
    with pytest.raises(RuntimeError, match="mutation tool must be"):
        module.main(["--target", "control", "--out", str(tmp_path / "out")])


def test_campaign_runs_baseline_first_and_cleans_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    import waggle.experiments.e9_mutation as module

    monkeypatch.setattr("waggle.experiments.e9_mutation.sys.platform", "linux")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(module, "version", lambda _: module.TOOL_VERSION)
    copies: list[Path] = []
    calls: list[list[str]] = []

    def prepare(_root: Path, dest: Path, _target: str) -> None:
        dest.mkdir()
        copies.append(dest)

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "mutmut" in command:
            raw = copies[0] / "mutants"
            raw.mkdir()
            (raw / "rule.py.meta").write_text('{"exit_code_by_key": {"mutant": 0}}')
        return subprocess.CompletedProcess(command, 0, stdout="abc\n")

    monkeypatch.setattr(module, "prepare_campaign", prepare)
    monkeypatch.setattr("waggle.experiments.e9_mutation.subprocess.run", run)
    out = tmp_path / "out"
    assert module.main(["--target", "control", "--out", str(out)]) == 0
    assert "pytest" in calls[1]
    assert "mutmut" in calls[2]
    assert not copies[0].exists()
    report = json.loads((out / "result.json").read_text())
    assert report["survived"] == ["mutant"]
    assert report["generated"] == 1
    assert (out / "raw/rule.py.meta").exists()


def test_broken_baseline_stops_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    import waggle.experiments.e9_mutation as module

    monkeypatch.setattr("waggle.experiments.e9_mutation.sys.platform", "linux")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(module, "version", lambda _: module.TOOL_VERSION)
    copies: list[Path] = []

    def prepare(_root: Path, dest: Path, _target: str) -> None:
        dest.mkdir()
        copies.append(dest)

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "mutmut" not in command
        if "pytest" in command:
            raise subprocess.CalledProcessError(5, command)
        return subprocess.CompletedProcess(command, 0, stdout="abc\n")

    monkeypatch.setattr(module, "prepare_campaign", prepare)
    monkeypatch.setattr("waggle.experiments.e9_mutation.subprocess.run", run)
    out = tmp_path / "out"
    with pytest.raises(subprocess.CalledProcessError):
        module.main(["--target", "control", "--out", str(out)])
    assert not copies[0].exists()
    assert not (out / "result.json").exists()
    assert (out / "baseline.log").exists()


def test_workflow_is_manual_and_installs_only_cloud_tool() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/e9_mutation.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "target: [control, validation]" in workflow
    assert "mutmut==3.3.1" in workflow
    assert "uv run --no-sync" in workflow
    assert "if: always()" in workflow
    assert "secrets." not in workflow


def test_copy_inside_repository_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside repository"):
        prepare_campaign(tmp_path, tmp_path / "copy", "control")


def test_prepare_campaign_writes_robust_fork_shim(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src/waggle/control").mkdir(parents=True)
    (root / "src/waggle/validation").mkdir()
    (root / "tests/unit/control").mkdir(parents=True)
    (root / "tests/support").mkdir()
    (root / "src/waggle/control/rule.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src/waggle/validation/rule.py").write_text("VALUE = 2\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'toy'\n", encoding="utf-8")
    dest = tmp_path / "copy"
    prepare_campaign(root, dest, "control")

    shim = dest / "sitecustomize.py"
    assert shim.is_file()

    code = (
        "import sitecustomize\n"
        "import multiprocessing as mp\n"
        "mp.set_start_method('fork')\n"
        "mp.set_start_method('fork')\n"
        "mp.set_start_method('fork', force=True)\n"
        "mp.set_start_method('fork')\n"
        "assert mp.get_start_method() == 'fork'\n"
        "try:\n"
        "    mp.set_start_method('spawn')\n"
        "except RuntimeError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('expected RuntimeError on start method change')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=dest,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "RuntimeError" not in res.stderr
    assert res.returncode == 0, f"stdout: {res.stdout}\nstderr: {res.stderr}"
