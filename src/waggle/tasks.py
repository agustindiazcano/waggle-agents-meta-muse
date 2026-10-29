"""Developer task runner, exposed as console scripts in ``[project.scripts]``.

Run with ``uv run <target>``, for example ``uv run ci``. The checks here are the
same commands the CI workflow runs.
"""

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

Command = list[str]


def venv_tool(name: str) -> str:
    """Absolute path of a console script installed next to the running interpreter."""
    found = shutil.which(name, path=str(Path(sys.executable).parent))
    if found is None:
        raise FileNotFoundError(f"{name} is not installed in this environment")
    return found


def _module(name: str, *args: str) -> Command:
    return [sys.executable, "-m", name, *args]


LINT: list[Command] = [
    _module("ruff", "check", "."),
    _module("ruff", "format", "--check", "."),
]
TYPE: list[Command] = [_module("mypy")]
MARKER_EXPR = "not heavy and not llm"
TEST: list[Command] = [
    _module("pytest", "--cov", "--cov-report=term-missing", "--cov-report=xml", "-m", MARKER_EXPR),
]


def _import_contracts() -> Command:
    return [venv_tool("lint-imports")]


def _run(commands: list[Command]) -> int:
    for cmd in commands:
        print(f"$ {' '.join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))}", flush=True)
        code = subprocess.run(cmd, check=False).returncode
        if code != 0:
            return code
    return 0


def lint() -> int:
    return _run(LINT)


def typecheck() -> int:
    return _run(TYPE)


def test() -> int:
    return _run(TEST)


def contracts() -> int:
    return _run([_import_contracts()])


def ci() -> int:
    return _run([*LINT, *TYPE, *TEST, _import_contracts()])


def _placeholder(name: str) -> Callable[[], int]:
    def run() -> int:
        print(f"{name}: placeholder, no experiments exist before Phase 1")
        return 0

    return run


experiments_dev = _placeholder("experiments-dev")
experiments_test = _placeholder("experiments-test")
report = _placeholder("report")

PLACEHOLDER_TARGETS: dict[str, Callable[[], int]] = {
    "experiments-dev": experiments_dev,
    "experiments-test": experiments_test,
    "report": report,
}
