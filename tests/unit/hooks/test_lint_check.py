import io
import json
import subprocess
import sys
from pathlib import Path

import lint_check
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "hooks" / "lint_check.py"


class Runner:
    """Records commands and returns scripted (exit code, output) pairs."""

    def __init__(self, results: list[tuple[int, str]] | None = None) -> None:
        self.commands: list[list[str]] = []
        self._results = results or []

    def __call__(self, command: list[str]) -> tuple[int, str]:
        self.commands.append(command)
        return self._results.pop(0) if self._results else (0, "")


def event(path: str, tool: str = "Edit") -> str:
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": tool,
            "tool_input": {"file_path": path},
            "tool_response": {},
        }
    )


def run(raw: str, runner: Runner) -> tuple[int, str]:
    err = io.StringIO()
    code = lint_check.main(io.StringIO(raw), err, runner=runner, root=ROOT)
    return code, err.getvalue()


def test_non_python_file_is_ignored() -> None:
    runner = Runner()
    assert run(event(str(ROOT / "README.md")), runner) == (0, "")
    assert runner.commands == []


def test_python_file_outside_src_runs_ruff_only() -> None:
    runner = Runner()
    code, err = run(event(str(ROOT / "tests" / "unit" / "test_x.py")), runner)
    assert (code, err) == (0, "")
    assert [c[:3] for c in runner.commands] == [["uv", "run", "ruff"]]
    assert runner.commands[0][3] == "check"


def test_python_file_under_src_runs_ruff_and_mypy_strict() -> None:
    runner = Runner()
    target = str(ROOT / "src" / "waggle" / "tasks.py")
    code, err = run(event(target), runner)
    assert (code, err) == (0, "")
    assert [c[2] for c in runner.commands] == ["ruff", "mypy"]
    assert "--strict" in runner.commands[1]
    assert runner.commands[1][-1] == target


def test_clean_run_is_silent() -> None:
    runner = Runner(
        [(0, "All checks passed!\n"), (0, "Success: no issues found in 1 source file\n")]
    )
    assert run(event(str(ROOT / "src" / "waggle" / "tasks.py")), runner) == (0, "")


def test_errors_exit_2_and_print_only_the_errors() -> None:
    runner = Runner([(1, "E501 Line too long\n  --> src/waggle/a.py:3:1\nFound 1 error.\n")])
    code, err = run(event(str(ROOT / "src" / "waggle" / "a.py")), runner)
    assert code == 2
    assert "E501 Line too long" in err
    assert "All checks passed" not in err


def test_mypy_errors_are_reported_even_when_ruff_is_clean() -> None:
    runner = Runner([(0, "All checks passed!\n"), (1, "a.py:3: error: bad type\n")])
    code, err = run(event(str(ROOT / "src" / "waggle" / "a.py")), runner)
    assert code == 2
    assert "bad type" in err


def test_write_tool_is_also_checked() -> None:
    runner = Runner()
    run(event(str(ROOT / "tests" / "unit" / "test_x.py"), tool="Write"), runner)
    assert len(runner.commands) == 1


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_input": {}}', '{"tool_input": 5}'])
def test_malformed_event_never_blocks(raw: str) -> None:
    runner = Runner()
    assert run(raw, runner) == (0, "")
    assert runner.commands == []


def test_tool_failure_is_a_non_blocking_error() -> None:
    def broken(_: list[str]) -> tuple[int, str]:
        raise OSError("uv not found")

    err = io.StringIO()
    code = lint_check.main(
        io.StringIO(event(str(ROOT / "tests" / "unit" / "test_x.py"))),
        err,
        runner=broken,
        root=ROOT,
    )
    assert code == 1
    assert "uv not found" in err.getvalue()


def test_cli_ignores_non_python_files() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=event(str(ROOT / "README.md")),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
        check=False,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
