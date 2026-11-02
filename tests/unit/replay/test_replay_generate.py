"""Replay generator: deterministic files that replay-verify accepts, and clean refusals."""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from waggle.replay import generate, replay_format, verify


def _run(*args: str) -> tuple[int, str]:
    stderr = io.StringIO()
    code = generate.main(list(args), stderr)
    return code, stderr.getvalue()


def _make(path: Path, *extra: str, scenario: str = "S01", seed: str = "7", ticks: str = "6") -> int:
    code, _ = _run(
        "--scenario", scenario, "--seed", seed, "--ticks", ticks, "--out", str(path), *extra
    )
    return code


def test_it_writes_a_file_with_the_requested_frames_and_run_metadata(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    assert _make(path, "--commit", "abc1234") == 0
    replay = replay_format.read_replay(path)
    header = replay.header
    assert (header["commit"], header["seed"], header["scenario_id"]) == ("abc1234", 7, "S01")
    assert header["frame_count"] == 6 and header["resimulable"] is True
    assert [f["tick"] for f in replay.frames] == [1, 2, 3, 4, 5, 6]
    assert {f["run"]["source"] for f in replay.frames} == {"replay"}


def test_replay_verify_accepts_the_output_with_the_full_re_run(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    assert _make(path) == 0
    problems, note = verify.verify_file(str(path), digest_only=False)
    assert problems == []
    assert note == "re-run from the seed"
    stderr = io.StringIO()
    assert verify.main([str(path)], stderr) == 0


def test_the_same_arguments_give_the_same_bytes(tmp_path: Path) -> None:
    assert _make(tmp_path / "a.jsonl") == 0
    assert _make(tmp_path / "b.jsonl") == 0
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()


def test_a_different_seed_or_commit_gives_a_different_file(tmp_path: Path) -> None:
    assert _make(tmp_path / "a.jsonl") == 0
    assert _make(tmp_path / "b.jsonl", seed="8") == 0
    assert _make(tmp_path / "c.jsonl", "--commit", "other") == 0
    contents = {(tmp_path / n).read_bytes() for n in ("a.jsonl", "b.jsonl", "c.jsonl")}
    assert len(contents) == 3


def test_the_commit_defaults_to_the_environment_and_then_to_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WAGGLE_COMMIT", raising=False)
    assert _make(tmp_path / "a.jsonl") == 0
    assert replay_format.read_replay(tmp_path / "a.jsonl").header["commit"] == "unknown"
    monkeypatch.setenv("WAGGLE_COMMIT", "fromenv")
    assert _make(tmp_path / "b.jsonl") == 0
    assert replay_format.read_replay(tmp_path / "b.jsonl").header["commit"] == "fromenv"


def test_an_existing_file_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text("keep me\n", encoding="utf-8")
    code, message = _run("--scenario", "S01", "--seed", "7", "--ticks", "3", "--out", str(path))
    assert code == 1
    assert "exists" in message
    assert path.read_text(encoding="utf-8") == "keep me\n"


@pytest.mark.parametrize(
    "args",
    [
        ["--scenario", "S99", "--seed", "1", "--ticks", "3"],
        ["--scenario", "S01", "--seed", "1", "--ticks", "0"],
        ["--scenario", "S01", "--seed", "1", "--ticks", "-4"],
        ["--scenario", "S01", "--seed", "1", "--ticks", "99999999"],
        ["--scenario", "S01", "--seed", "x", "--ticks", "3"],
        ["--scenario", "S01", "--seed", "1"],
        [],
    ],
)
def test_bad_arguments_exit_2_and_leave_no_file(tmp_path: Path, args: list[str]) -> None:
    path = tmp_path / "run.jsonl"
    code, message = _run(*args, "--out", str(path))
    assert code == 2
    assert message
    assert not path.exists()


def test_a_missing_output_directory_is_a_clean_failure(tmp_path: Path) -> None:
    path = tmp_path / "nope" / "run.jsonl"
    code, message = _run("--scenario", "S01", "--seed", "1", "--ticks", "2", "--out", str(path))
    assert code == 1
    assert "cannot write" in message


def test_the_summary_goes_to_stderr_and_nothing_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stderr = io.StringIO()
    path = tmp_path / "run.jsonl"
    code = generate.main(
        ["--scenario", "S01", "--seed", "7", "--ticks", "4", "--out", str(path)], stderr
    )
    assert code == 0
    assert "wrote 4 frames" in stderr.getvalue()
    assert capsys.readouterr().out == ""


def test_the_module_runs_as_a_command(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    done = subprocess.run(
        [sys.executable, "-m", "waggle.replay.generate", "--scenario", "S01", "--seed", "7",
         "--ticks", "3", "--out", str(path)],
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["frame_count"] == 3
