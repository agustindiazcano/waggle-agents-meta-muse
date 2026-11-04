"""Load failure cases into the failure_history table (ADR-088).

The table is filled by this script, never by a migration. A repeated case id is a skip. A
ValueError from add aborts the load: later cases are not added. Synthetic rows are not
evidence, and their part numbers are not catalog parts.
"""

import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TextIO

import psycopg

from waggle.db.connection import Database
from waggle.db.failure_history import FailureHistory, FailureRow
from waggle.experiments.failure_log import generate_failure_log
from waggle.maintenance.failure_cases import FailureCase

USAGE = "usage: load-failure-history SEED COUNT SOURCE\n"


class FailureStore(Protocol):
    """The add method of FailureHistory, so a test double can stand in."""

    def add(self, row: FailureRow, *, source: str) -> bool:
        """Insert one case. Returns False when the case id was already there."""
        ...


@dataclass(frozen=True)
class LoadResult:
    """How many rows were inserted and how many case ids were already present."""

    inserted: int
    skipped: int


def _row(case: FailureCase) -> FailureRow:
    return FailureRow(
        case_id=case.case_id,
        machine_class=case.machine_class,
        mode=case.mode.value,
        onset_to_failure_ticks=case.onset_to_failure_ticks,
        peak_temperature_c=case.peak_temperature_c,
        peak_vibration_rms=case.peak_vibration_rms,
        peak_current_a=case.peak_current_a,
        part_number=case.part_number,
    )


def load_failure_history(
    history: FailureStore, cases: Sequence[FailureCase], source: str
) -> LoadResult:
    """Insert each case. Repeats are counted as skips. A ValueError from add is not caught."""
    inserted = 0
    skipped = 0
    for case in cases:
        if history.add(_row(case), source=source):
            inserted += 1
        else:
            skipped += 1
    return LoadResult(inserted, skipped)


def main(argv: Sequence[str], environ: Mapping[str, str], stderr: TextIO) -> int:
    """Load a generated log into the database named by DATABASE_URL. Returns 0, or 2 on failure."""
    if len(argv) != 3:
        stderr.write(USAGE)
        return 2
    seed_text, count_text, source = argv
    try:
        seed = int(seed_text)
        count = int(count_text)
    except ValueError:
        stderr.write(USAGE)
        return 2
    try:
        cases = generate_failure_log(seed, count)
        database = Database.from_environ(environ)
        result = load_failure_history(FailureHistory(database), cases, source)
    except (ValueError, psycopg.Error) as error:
        stderr.write(f"load-failure-history failed: {type(error).__name__}\n")
        return 2
    sys.stdout.write(f"inserted={result.inserted} skipped={result.skipped}\n")
    return 0


def run() -> int:
    """Process entry: real arguments, environment and standard error."""
    return main(sys.argv[1:], os.environ, sys.stderr)
