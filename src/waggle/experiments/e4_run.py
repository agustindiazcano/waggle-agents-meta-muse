"""E4 runner CLI: scripted court configurations on the development review set.

Run with ``uv run python -m waggle.experiments.e4_run --help``. This is the
harness entry point of COURT_DESIGN branch 8 in scripted mode: reviewers are
``ScriptedProvider`` answers from a strict scripts file, so no network, no
spend and no provider call happens. The result file is the E4 harness record
and carries its scripted-mode warning; it is never a model result.

The CLI has no held-out selection on purpose. It always loads the
``development`` split through ``load_for_evaluation``, which refuses pending
cases and the synthetic placeholder file. A live or held-out run needs the
maintainer's reviewed set, caps and authorization, and is out of scope here.
"""

import argparse
import json
import shutil
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from waggle.experiments.e4_cases import EvalCase, load_for_evaluation
from waggle.experiments.e4_configs import CONFIGURATIONS, Configuration
from waggle.experiments.e4_harness import Scripts, run_e4
from waggle.llm.court_adapter import COURT_ROLES


def load_scripts(path: Path, cases: Sequence[EvalCase]) -> Scripts:
    """Load scripted reviewer answers, strict about cases, roles and text.

    The file maps a case id to a mapping of court role to the raw answer text
    for that reviewer. Unknown case ids, unknown roles, blank or non-text
    answers and non-object payloads are real errors, never an empty pass.
    """
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("scripts file must be an object of case id to role answers")
    known = {case.id for case in cases}
    scripts: dict[str, dict[str, str]] = {}
    for case_id, answers in raw.items():
        if case_id not in known:
            raise ValueError(f"scripts for unknown case {case_id}")
        if not isinstance(answers, dict):
            raise ValueError(f"{case_id}: answers must be an object of role to text")
        loaded: dict[str, str] = {}
        for role, answer in answers.items():
            if role not in COURT_ROLES:
                raise ValueError(f"{case_id}: unknown court role {role}")
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(f"{case_id}: answer for {role} must be non-blank text")
            loaded[role] = answer
        scripts[case_id] = loaded
    return scripts


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git is required for result provenance")
    return subprocess.run(
        [git, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def run(
    config: Configuration,
    cases_path: Path,
    scripts_path: Path | None,
    *,
    repeats: int,
    out_dir: Path,
) -> Path:
    """Run one scripted development configuration and write its result file."""
    cases = load_for_evaluation(cases_path, "development")
    scripts = load_scripts(scripts_path, cases) if scripts_path is not None else {}
    return run_e4(
        config,
        cases,
        scripts,
        repeats=repeats,
        held_out=False,
        commit=_commit(),
        run_date=datetime.now(UTC).date().isoformat(),
        out_dir=out_dir,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one configuration; existing result files are never overwritten."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=sorted(CONFIGURATIONS), required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--scripts", type=Path)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    run(
        CONFIGURATIONS[args.config],
        args.cases,
        args.scripts,
        repeats=args.repeats,
        out_dir=args.out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
