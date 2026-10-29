"""PostToolUse lint check for edited Python files (standard library only).

Runs ruff on every edited .py file and mypy --strict on edited files under src/.
Silent when clean. Real errors go to stderr with exit code 2, which Claude Code shows
to Claude. A tool that cannot run exits 1 (non-blocking notice).
"""

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

import guard_common as gc

Runner = Callable[[list[str]], tuple[int, str]]
NOISE = ("All checks passed!", "Success:")
TIMEOUT_SECONDS = 120


def subprocess_runner(root: Path) -> Runner:
    """Runner that executes a command in the project root and returns (code, output)."""

    def run(command: list[str]) -> tuple[int, str]:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        return result.returncode, result.stdout + result.stderr

    return run


def _edited_python_file(raw: str) -> str | None:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        return None
    path = event["tool_input"].get("file_path")
    return path if isinstance(path, str) and path.endswith(".py") else None


def _errors(output: str) -> str:
    kept = [line for line in output.splitlines() if not line.startswith(NOISE)]
    return "\n".join(kept).strip()


def main(
    stdin: TextIO,
    stderr: TextIO,
    *,
    runner: Runner | None = None,
    root: Path | None = None,
) -> int:
    """Check the edited file. Returns 0 when clean, 2 on lint errors, 1 if a tool failed."""
    project = root or Path.cwd()
    path = _edited_python_file(stdin.read().lstrip(chr(0xFEFF)))
    if path is None:
        return 0
    run = runner or subprocess_runner(project)
    commands = [["uv", "run", "ruff", "check", path]]
    if gc.normalize_path(path, project).startswith("src/"):
        commands.append(["uv", "run", "mypy", "--strict", path])
    reports: list[str] = []
    for command in commands:
        try:
            code, output = run(command)
        except (OSError, subprocess.SubprocessError) as err:
            stderr.write(f"lint_check could not run {' '.join(command[:3])}: {err}\n")
            return 1
        if code != 0:
            reports.append(_errors(output) or f"{' '.join(command[:3])} failed")
    if reports:
        stderr.write("\n".join(reports) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin, sys.stderr))
