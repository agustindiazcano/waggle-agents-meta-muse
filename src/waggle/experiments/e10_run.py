"""E10 runner CLI: scripted crisis configurations on development templates.

Run with ``uv run python -m waggle.experiments.e10_run --help``. No network, no
spend and no held-out selection: templates are the development fixtures of
``e10_cases`` and each planner answer comes from the template scripts.
"""

import argparse
import shutil
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from waggle.experiments.e10_cases import TEMPLATES
from waggle.experiments.e10_configs import CONFIGURATIONS, Configuration
from waggle.experiments.e10_harness import run_e10


def _commit() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git is required for result provenance")
    return subprocess.run(
        [git, "-c", "safe.directory=*", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def run(config: Configuration, *, out_dir: Path) -> Path:
    """Run one scripted development configuration and write its result file."""
    scripts = {t.id: (t.faulty_raw, t.safe_raw) for t in TEMPLATES}
    return run_e10(
        config,
        TEMPLATES,
        scripts,
        commit=_commit(),
        run_date=datetime.now(UTC).date().isoformat(),
        out_dir=out_dir,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one configuration; existing result files are never overwritten."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=sorted(CONFIGURATIONS), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    run(CONFIGURATIONS[args.config], out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
