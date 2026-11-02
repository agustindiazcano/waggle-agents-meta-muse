"""Generate a replay file from a scenario: ``python -m waggle.replay.generate``.

Builds the scenario for a seed, steps the simulator with no control, records one frame per tick
with ``ReplayRecorder`` and writes the file once, in exclusive-create mode. The same arguments
give the same bytes: nothing here reads the clock, the network or a global random stream, and the
commit comes from ``--commit`` or ``WAGGLE_COMMIT`` (default ``unknown``), never from git. The
file is marked re-runnable, so ``replay-verify`` can rebuild it from the seed. Messages go to
standard error; standard output stays empty. Exit codes: 0 written, 1 refused or failed, 2 bad
arguments.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, TextIO

from waggle.replay.recorder import ReplayRecorder
from waggle.sim import frame, scenarios


class _UsageError(Exception):
    """The arguments are invalid."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        raise _UsageError(message or "exit requested")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m waggle.replay.generate", add_help=False)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--ticks", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--commit", default=os.environ.get("WAGGLE_COMMIT", "unknown"))
    return parser


def generate(path: Path, scenario_id: str, seed: int, ticks: int, commit: str) -> int:
    """Write a replay of ``ticks`` ticks and return the frame count.

    ValueError for an unknown scenario, a negative seed or a tick count outside 1 to the scenario
    duration. FileExistsError if ``path`` exists. A failure leaves no file.
    """
    scenario = scenarios.generate(scenario_id, seed)
    if not 1 <= ticks <= scenario.duration_ticks:
        raise ValueError(f"ticks must be between 1 and {scenario.duration_ticks}")
    sim, _detector = scenarios.build_engine(scenario)
    world = frame.world_hash(scenarios.load_map(scenario.map_name))
    run = frame.RunInfo(commit, seed, scenario.id, "replay")
    with ReplayRecorder(path, run, world, resimulable=True) as recorder:
        for _ in range(ticks):
            sim.step()
            recorder.add(frame.export_frame(sim, run))
    return ticks


def main(argv: Sequence[str], stderr: TextIO) -> int:
    """Run the command and return its exit code."""
    try:
        args = _parser().parse_args(list(argv))
    except _UsageError as error:
        print(f"replay-generate: {error}", file=stderr)
        return 2
    try:
        count = generate(args.out, args.scenario, args.seed, args.ticks, args.commit)
    except ValueError as error:
        print(f"replay-generate: {error}", file=stderr)
        return 2
    except FileExistsError:
        print(f"replay-generate: {args.out} exists, not overwritten", file=stderr)
        return 1
    except (OSError, frame.FrameTooLarge) as error:
        print(f"replay-generate: cannot write {args.out}: {error}", file=stderr)
        return 1
    print(f"replay-generate: wrote {count} frames to {args.out}", file=stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stderr))
