"""E9 planted-defect campaign runner (EXPERIMENTS.md, E9).

For each defect the runner copies ``src``, ``tests`` and ``pyproject.toml`` to a
temporary directory, applies the defect to the copy only, and runs the declared
detector tests there. A defect is killed when a detector fails on the mutated
copy and the same detectors pass on an unmutated copy; if the baseline fails,
the outcome is ``detector_broken`` and never a kill. The real tree is never
mutated and temporary copies are deleted. Run with
``uv run python -m waggle.experiments.e9_run --out results/e9/dev/planted.json``.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from waggle.experiments.e9_defects import DEFECTS, PlantedDefect, apply_defect, defect_by_id

Status = Literal["killed", "survived", "detector_broken"]
Runner = Callable[[PlantedDefect, Path], int]
_TIMEOUT_S: Final = 900


@dataclass(frozen=True)
class DefectOutcome:
    """One defect result. ``first_detector`` is the first declared detector."""

    id: str
    status: Status
    first_detector: str


def _copy_tree(root: Path, dest: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    shutil.copytree(root / "src", dest / "src", ignore=ignore)
    shutil.copytree(root / "tests", dest / "tests", ignore=ignore)
    shutil.copy2(root / "pyproject.toml", dest / "pyproject.toml")


def _run_real(defect: PlantedDefect, root: Path, *, mutated: bool, work_root: Path | None) -> int:
    with tempfile.TemporaryDirectory(dir=work_root) as tmp:
        dest = Path(tmp) / "tree"
        dest.mkdir()
        _copy_tree(root, dest)
        if mutated:
            target = dest / defect.source
            target.write_text(
                apply_defect(target.read_text(encoding="utf-8"), defect), encoding="utf-8"
            )
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *defect.detectors,
                "-q",
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
            ],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
        return done.returncode


def run_campaign(
    defects: Sequence[PlantedDefect],
    *,
    root: Path,
    work_root: Path | None = None,
    run_detector: Runner | None = None,
    run_baseline: Runner | None = None,
) -> tuple[DefectOutcome, ...]:
    """Run the baseline and mutated detector passes for each defect, in order."""
    outcomes: list[DefectOutcome] = []
    for defect in defects:
        baseline = (
            run_baseline(defect, root)
            if run_baseline is not None
            else _run_real(defect, root, mutated=False, work_root=work_root)
        )
        first = defect.detectors[0] if defect.detectors else ""
        if baseline != 0:
            outcomes.append(DefectOutcome(defect.id, "detector_broken", first))
            continue
        code = (
            run_detector(defect, root)
            if run_detector is not None
            else _run_real(defect, root, mutated=True, work_root=work_root)
        )
        outcomes.append(DefectOutcome(defect.id, "killed" if code != 0 else "survived", first))
    return tuple(outcomes)


def write_result(outcomes: Sequence[DefectOutcome], path: Path, *, commit: str, date: str) -> Path:
    """Write the campaign result JSON. Survivors are listed in full, never dropped."""
    body = {
        "experiment": "E9",
        "kind": "planted_defects",
        "seed_set": "dev",
        "commit": commit,
        "date": date,
        "planted": len(outcomes),
        "killed": sum(1 for o in outcomes if o.status == "killed"),
        "survived": [o.id for o in outcomes if o.status == "survived"],
        "detector_broken": [o.id for o in outcomes if o.status == "detector_broken"],
        "outcomes": [
            {"id": o.id, "status": o.status, "first_detector": o.first_detector} for o in outcomes
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Run the campaign from the repository root and write the result file."""
    parser = argparse.ArgumentParser(prog="e9_run")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--defect", action="append", dest="defects")
    args = parser.parse_args(argv)
    root = Path.cwd()
    defects = [defect_by_id(d) for d in args.defects] if args.defects else list(DEFECTS)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
    ).stdout.strip()
    outcomes = run_campaign(defects, root=root)
    write_result(
        outcomes, args.out, commit=commit or "unknown", date=datetime.now(UTC).date().isoformat()
    )
    for outcome in outcomes:
        print(f"{outcome.id}: {outcome.status} (first detector: {outcome.first_detector})")
    return 0 if all(o.status == "killed" for o in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
