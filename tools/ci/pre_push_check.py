"""Pre-push check (standard library only).

The safety guard runs this script before it lets a ``git push`` or ``gh pr create`` through.
Exit 0 means every check passed. Exit 1 prints one problem per line on stderr.

Checks:
1. ``uv run ci`` passed on the current HEAD (stamp under ``.git/``) and the tree is clean.
2. gitleaks finds nothing in the commits that would be pushed. If gitleaks is missing, the
   check fails closed.
3. Those commits contain no ``.env`` file and no held-out result file.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

STAMP_NAME = "waggle_ci_stamp"
GIT_TIMEOUT = 30
GITLEAKS_TIMEOUT = 120
UNPUSHED = "HEAD --not --remotes=origin"
HELDOUT = re.compile(r"(^|/)results/(?:[^/]+/)*heldout/")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git is not installed")
    return subprocess.run(
        [git, *args], cwd=root, capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False
    )


def _git_out(root: Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode != 0:
        raise OSError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def find_gitleaks() -> str | None:
    """Path of the gitleaks executable, or None. Looks on PATH, then in the WinGet packages."""
    found = shutil.which("gitleaks")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        packages = os.path.join(local, "Microsoft", "WinGet", "Packages")
        matches = sorted(glob.glob(os.path.join(packages, "Gitleaks*", "gitleaks.exe")))
        if matches:
            return matches[0]
    return None


def _stamp_problems(root: Path) -> list[str]:
    git_dir = Path(_git_out(root, "rev-parse", "--git-dir").strip())
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    head = _git_out(root, "rev-parse", "HEAD").strip()
    stamp = git_dir / STAMP_NAME
    problems: list[str] = []
    if not stamp.is_file():
        problems.append("no CI stamp: run `uv run ci` until it is green, then push")
    elif stamp.read_text(encoding="utf-8").strip() != head:
        problems.append("the CI stamp is not for the current HEAD: run `uv run ci` again")
    if _git_out(root, "status", "--porcelain").strip():
        problems.append("the working tree is not clean: commit or remove the changes first")
    return problems


def _unpushed_files(root: Path) -> list[str]:
    out = _git_out(root, "log", "--name-only", "--format=", *UNPUSHED.split())
    return sorted({line for line in out.splitlines() if line})


def _forbidden_files(files: list[str]) -> list[str]:
    problems: list[str] = []
    for name in files:
        base = name.rsplit("/", 1)[-1]
        if base != ".env.example" and (base == ".env" or base.startswith(".env.")):
            problems.append(f"{name} is an .env file in a commit to be pushed")
        if HELDOUT.search(name):
            problems.append(f"{name} is a heldout result: only the maintainer commits it")
    return problems


def _gitleaks_problems(root: Path, gitleaks: Sequence[str] | None) -> list[str]:
    command = list(gitleaks) if gitleaks is not None else None
    if command is None:
        exe = find_gitleaks()
        if exe is None:
            return ["gitleaks is not installed, so the commits cannot be scanned (fail closed)"]
        command = [exe]
    full = [*command, "git", "--no-banner", f"--log-opts={UNPUSHED}", str(root)]
    try:
        result = subprocess.run(
            full, capture_output=True, text=True, timeout=GITLEAKS_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return [f"gitleaks could not run: {err}"]
    if result.returncode != 0:
        return [f"gitleaks found leaks or failed (exit {result.returncode}): do not push"]
    return []


def check(root: Path, gitleaks: Sequence[str] | None = None) -> list[str]:
    """Return the list of problems. Empty means the push may go ahead."""
    problems = _stamp_problems(root)
    files = _unpushed_files(root)
    problems += _forbidden_files(files)
    if files:
        problems += _gitleaks_problems(root, gitleaks)
    return problems


def main(argv: Sequence[str] | None = None, gitleaks: Sequence[str] | None = None) -> int:
    """Command line entry. ``gitleaks`` replaces the executable in tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args(argv)
    try:
        problems = check(Path(args.root).resolve(), gitleaks)
    except (OSError, subprocess.SubprocessError) as err:
        problems = [f"the pre-push check could not run: {err}"]
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
