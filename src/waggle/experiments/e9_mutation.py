"""E9 cloud-only mutmut campaign on disposable source copies.

The pinned adapter follows boxed/mutmut tag 3.3.1, __main__.py (Config and
SourceFileMutationData). Unlike mutmut, pytest internal errors are not kills.
Run: uv run python -m waggle.experiments.e9_mutation --target control --out DIR.
The workflow installs mutmut==3.3.1 as a cloud development tool only. No runtime
or project dependency changes are needed. Results require manual survivor and
equivalence review; no mutant is silently removed from the denominator.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TypedDict

from waggle.experiments.e1_stats import wilson

TOOL_VERSION = "3.3.1"
TARGETS = ("control", "validation")
STATUS = {
    0: "survived",
    1: "killed",
    2: "interrupted",
    3: "internal_error",
    5: "no_tests",
    33: "no_tests",
    34: "skipped",
    35: "suspicious",
    36: "timeout",
    -24: "timeout",
    24: "timeout",
    152: "timeout",
    255: "timeout",
    -11: "segfault",
    None: "not_checked",
}


class Outcome(TypedDict):
    """Raw tool outcome with a conservative interpretation."""

    id: str
    status: str
    exit_code: int | None


class Report(TypedDict):
    """Mutation metrics and reproducibility metadata."""

    experiment: str
    kind: str
    tool: str
    tool_version: str
    target: str
    commit: str
    date: str
    seed_set: str
    model_ids: list[str]
    prompt_versions: list[str]
    generated: int
    killed: int
    kill_ratio: float
    kill_ratio_wilson95: tuple[float, float]
    survived: list[str]
    outcomes: list[Outcome]
    complete: bool


def prepare_campaign(root: Path, dest: Path, target: str) -> None:
    """Copy code and tests; mutate only the declared target in the copy."""
    if target not in TARGETS:
        raise ValueError("unsupported mutation target")
    if dest.resolve().is_relative_to(root.resolve()):
        raise ValueError("campaign copy must be outside repository")
    dest.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc")
    for name in ("src", "tests"):
        shutil.copytree(root / name, dest / name, ignore=ignore)
    shutil.copy2(root / "pyproject.toml", dest / "pyproject.toml")
    excluded = sorted(
        p.relative_to(dest).as_posix()
        for p in (dest / "src/waggle").rglob("*.py")
        if not p.is_relative_to(dest / "src/waggle" / target)
    )
    config = (
        "[mutmut]\npaths_to_mutate=src/waggle\n"
        f"tests_dir=tests/unit/{target}\n"
        "do_not_mutate=\n" + "".join(f"    {p}\n" for p in excluded)
    )
    (dest / "setup.cfg").write_text(config, encoding="utf-8")


def summarize(raw: Path, *, target: str, commit: str, date: str) -> Report:
    """Read every generated mutant, retaining survivors and incomplete outcomes."""
    outcomes: list[Outcome] = []
    seen: set[str] = set()
    for path in sorted(raw.rglob("*.py.meta")):
        data = json.loads(path.read_text(encoding="utf-8"))
        codes = data["exit_code_by_key"]
        if not isinstance(codes, dict):
            raise ValueError("invalid mutant metadata")
        for name, code in sorted(codes.items()):
            if (code is not None and type(code) is not int) or code not in STATUS:
                raise ValueError(f"unsupported mutant exit code: {code}")
            if name in seen:
                raise ValueError(f"duplicate mutant id: {name}")
            seen.add(name)
            outcomes.append(Outcome(id=name, status=STATUS[code], exit_code=code))
    if not outcomes:
        raise ValueError("no mutants generated; campaign is not a pass")
    killed = sum(o["status"] == "killed" for o in outcomes)
    return Report(
        experiment="E9",
        kind="mutation_tool",
        tool="mutmut",
        tool_version=TOOL_VERSION,
        target=target,
        commit=commit,
        date=date,
        seed_set="dev",
        model_ids=[],
        prompt_versions=[],
        generated=len(outcomes),
        killed=killed,
        kill_ratio=killed / len(outcomes),
        kill_ratio_wilson95=wilson(killed, len(outcomes)),
        survived=[o["id"] for o in outcomes if o["status"] == "survived"],
        outcomes=outcomes,
        complete=all(o["status"] in {"killed", "survived"} for o in outcomes),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run only on Linux GitHub Actions, retaining logs and raw metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if sys.platform != "linux" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("mutation execution requires Linux GitHub Actions")
    try:
        installed = version("mutmut")
    except PackageNotFoundError:
        installed = ""
    if installed != TOOL_VERSION:
        raise RuntimeError(f"mutation tool must be mutmut=={TOOL_VERSION}")
    root = Path.cwd()
    commit = subprocess.run(
        ["git", "-c", "safe.directory=*", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="waggle-e9-") as temp:
        dest = Path(temp) / "tree"
        prepare_campaign(root, dest, args.target)
        with (out / "baseline.log").open("w", encoding="utf-8") as log:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"tests/unit/{args.target}",
                    "-q",
                    "-m",
                    "not heavy and not llm",
                ],
                cwd=dest,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=600,
                check=True,
            )
        with (out / "mutmut.log").open("w", encoding="utf-8") as log:
            try:
                done = subprocess.run(
                    [sys.executable, "-m", "mutmut", "run", "--max-children", "2"],
                    cwd=dest,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=5400,
                    check=False,
                    env={**os.environ, "PYTEST_ADDOPTS": "-m 'not heavy and not llm'"},
                )
            finally:
                if (dest / "mutants").exists():
                    shutil.copytree(dest / "mutants", out / "raw")
        report = summarize(
            out / "raw",
            target=args.target,
            commit=commit,
            date=datetime.now(UTC).isoformat(),
        )
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0 if done.returncode == 0 and report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
