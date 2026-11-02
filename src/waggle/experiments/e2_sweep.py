"""E2 sweep: run the development seeds of each arm and write one result file per arm.

``python -m waggle.experiments.e2_sweep`` runs the same ordered seeds for the ``fenced`` arm (the
production repository) and the ``baseline`` arm (no fencing), so the contribution of fencing is
read from an ablation on identical fault plans. Only development seeds exist here: the held-out
seed set is not accepted, so a held-out run cannot be started by mistake (AGENTS.md section 9).
The run conditions are read from the environment and a missing one is an error, never a blank:
``GITHUB_SHA`` for the commit and ``E2_POSTGRES_IMAGE`` for the image. ``DATABASE_URL`` names the
PostgreSQL service. Results are created exclusively under ``results/e2/dev``.
"""

import argparse
import os
import platform
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from waggle.db.connection import Database
from waggle.db.schema import LATEST_REVISION
from waggle.experiments.e2_chaos import ChaosConfig, run_once
from waggle.experiments.e2_chaos_worker import ARMS
from waggle.experiments.e2_faults import FaultParams, ScheduleError, build_schedule
from waggle.experiments.e2_result import build_result_file, write_result

DEVELOPMENT_SEEDS = tuple(range(1, 31))
Runner = Callable[[ChaosConfig], dict[str, object]]


@dataclass(frozen=True)
class SweepArgs:
    """Validated command line."""

    arms: tuple[str, ...]
    seeds: tuple[int, ...]
    params: FaultParams
    out: Path


def parse_args(argv: Sequence[str]) -> SweepArgs:
    """Read the command line; anything outside the development protocol is refused."""
    defaults = FaultParams()
    parser = argparse.ArgumentParser(prog="e2_sweep")
    parser.add_argument("--arm", choices=(*ARMS, "both"), default="both")
    parser.add_argument("--seed-set", choices=("development",), default="development")
    parser.add_argument("--seeds", type=int, default=len(DEVELOPMENT_SEEDS))
    parser.add_argument("--tasks", type=int, default=defaults.tasks)
    parser.add_argument("--workers", type=int, default=defaults.workers)
    parser.add_argument("--horizon", type=int, default=defaults.horizon)
    parser.add_argument("--out", type=Path, default=Path("results/e2/dev"))
    parsed = parser.parse_args(list(argv))
    if not 1 <= parsed.seeds <= len(DEVELOPMENT_SEEDS):
        raise ScheduleError("seeds must be between 1 and 30")
    params = replace(defaults, tasks=parsed.tasks, workers=parsed.workers, horizon=parsed.horizon)
    build_schedule(DEVELOPMENT_SEEDS[0], params)
    arms = ARMS if parsed.arm == "both" else (parsed.arm,)
    return SweepArgs(arms, DEVELOPMENT_SEEDS[: parsed.seeds], params, parsed.out)


def environment(environ: Mapping[str, str]) -> dict[str, object]:
    """The conditions a result file records; a missing one raises ``ScheduleError``."""
    commit = environ.get("GITHUB_SHA", "")
    image = environ.get("E2_POSTGRES_IMAGE", "")
    if not commit or not image:
        raise ScheduleError("GITHUB_SHA and E2_POSTGRES_IMAGE must be set")
    return {
        "commit": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "postgres_image": image,
        "schema_revision": LATEST_REVISION,
    }


def run_sweep(
    arm: str, seeds: Sequence[int], params: FaultParams, runner: Runner
) -> list[dict[str, object]]:
    """Run the ordered seeds of one arm and return their records."""
    return [runner(ChaosConfig(arm=arm, seed=seed, params=params)) for seed in seeds]


def main(argv: Sequence[str], environ: Mapping[str, str], runner: Runner | None = None) -> int:
    """Run the sweep and write one result file per arm; returns 0 when all files were written."""
    args = parse_args(argv)
    conditions = environment(environ)
    if runner is None:
        root = Database.from_environ(environ)

        def runner(config: ChaosConfig) -> dict[str, object]:
            return run_once(root, config)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for arm in args.arms:
        records = run_sweep(arm, args.seeds, args.params, runner)
        data = build_result_file(
            configuration=arm,
            seed_set="development",
            params=args.params,
            runs=records,
            environment=conditions,
        )
        path = args.out / f"chaos_{arm}_{stamp}.json"
        write_result(path, data)
        sys.stderr.write(f"wrote {path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], os.environ))
