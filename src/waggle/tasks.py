"""Developer task runner, exposed as console scripts in ``[project.scripts]``.

Run with ``uv run <target>``, for example ``uv run ci``. The checks here are the
same commands the CI workflow runs.
"""

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
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
    """Run ruff check and ruff format --check."""
    return _run(LINT)


def typecheck() -> int:
    """Run mypy --strict (configured in pyproject.toml)."""
    return _run(TYPE)


def test() -> int:
    """Run the light test suite with coverage, excluding heavy and llm tests."""
    return _run(TEST)


def contracts() -> int:
    """Run the import-linter contracts."""
    return _run([_import_contracts()])


def ci() -> int:
    """Run every CI check in the same order as the workflow."""
    return _run([*LINT, *TYPE, *TEST, _import_contracts()])


def _placeholder(name: str) -> Callable[[], int]:
    def run() -> int:
        print(f"{name}: placeholder, no experiments exist before Phase 1")
        return 0

    return run


experiments_dev = _placeholder("experiments-dev")
report = _placeholder("report")


def _git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        out = subprocess.run(
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=10
        )
    except subprocess.TimeoutExpired:
        return "unknown"
    return out.stdout.strip() or "unknown"


def experiments_test(argv: Sequence[str] | None = None) -> int:
    """Placeholder held-out run. Refuses to overwrite a result unless --force is given."""
    parser = argparse.ArgumentParser(prog="experiments-test")
    parser.add_argument("--force", action="store_true", help="overwrite an existing result")
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--experiment", default="placeholder")
    parser.add_argument("--configuration", default="placeholder")
    args = parser.parse_args(argv)

    path = args.results_dir / args.experiment / "heldout" / f"{args.configuration}.json"
    if path.exists() and not args.force:
        print(
            f"experiments-test: held-out result exists for {args.experiment}/{args.configuration}; "
            "pass --force to overwrite it",
            file=sys.stderr,
        )
        return 1
    record = {
        "experiment": args.experiment,
        "configuration": args.configuration,
        "seed_set": "heldout",
        "placeholder": True,
        "forced": bool(args.force),
        "commit": _git_commit(),
        "date": datetime.now(UTC).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"experiments-test: wrote {path}")
    return 0


PLACEHOLDER_TARGETS: dict[str, Callable[[], int]] = {
    "experiments-dev": experiments_dev,
    "report": report,
}
