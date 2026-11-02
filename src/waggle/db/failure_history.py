"""Failure history repository: the ``failure_history`` table of schema revision 14 (ADR-084).

Rows are numeric peaks and labels only: no manual text and no model output. The table is data
for diagnosis retrieval, loaded by a script, never by a migration. This module only touches the
database; matching and ranking live in ``waggle.maintenance.diagnosis``.
"""

import math
import re
from dataclasses import dataclass
from typing import cast

from waggle.db.connection import Database

MODES = ("BEARING_WEAR", "LUBRICATION_LOSS", "MISALIGNMENT")
MACHINE_CLASSES = ("conveyor", "pump", "lift")
_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_TICKS_MAX = 2**62


@dataclass(frozen=True)
class FailureRow:
    """One failure case as stored. Validated on construction and again on ``add``."""

    case_id: str
    machine_class: str
    mode: str
    onset_to_failure_ticks: int
    peak_temperature_c: float
    peak_vibration_rms: float
    peak_current_a: float
    part_number: str


def _peak(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("invalid peak value")
    if not math.isfinite(value) or value < 0:
        raise ValueError("invalid peak value")
    return float(value)


def _validate(row: FailureRow, source: object) -> None:
    for name in ("case_id", "part_number"):
        value = getattr(row, name)
        if not isinstance(value, str) or _ID.fullmatch(value) is None:
            raise ValueError(f"invalid {name}")
    if row.machine_class not in MACHINE_CLASSES:
        raise ValueError("invalid machine class")
    if row.mode not in MODES:
        raise ValueError("invalid mode")
    ticks = row.onset_to_failure_ticks
    if type(ticks) is not int or not 1 <= ticks <= _TICKS_MAX:
        raise ValueError("invalid onset_to_failure_ticks")
    _peak(row.peak_temperature_c)
    _peak(row.peak_vibration_rms)
    _peak(row.peak_current_a)
    if not isinstance(source, str) or not 1 <= len(source) <= 64:
        raise ValueError("invalid source")


class FailureHistory:
    """Append-only store of failure cases. A repeated case id is kept once (first write wins)."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def add(self, row: FailureRow, *, source: str) -> bool:
        """Insert one case. Returns False when the case id was already there."""
        _validate(row, source)
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO failure_history (case_id, machine_class, mode, "
                "onset_to_failure_ticks, peak_temperature_c, peak_vibration_rms, "
                "peak_current_a, part_number, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (case_id) DO NOTHING",
                (
                    row.case_id,
                    row.machine_class,
                    row.mode,
                    row.onset_to_failure_ticks,
                    float(row.peak_temperature_c),
                    float(row.peak_vibration_rms),
                    float(row.peak_current_a),
                    row.part_number,
                    source,
                ),
            )
            return cursor.rowcount != 0

    def rows(self) -> list[FailureRow]:
        """Every stored case ordered by case id."""
        with self._database.transaction() as connection:
            found = connection.execute(
                "SELECT case_id, machine_class, mode, onset_to_failure_ticks, "
                "peak_temperature_c, peak_vibration_rms, peak_current_a, part_number "
                "FROM failure_history ORDER BY case_id"
            ).fetchall()
        # Column types and the table checks fix the row types.
        return [
            FailureRow(
                case_id=cast(str, r[0]),
                machine_class=cast(str, r[1]),
                mode=cast(str, r[2]),
                onset_to_failure_ticks=cast(int, r[3]),
                peak_temperature_c=cast(float, r[4]),
                peak_vibration_rms=cast(float, r[5]),
                peak_current_a=cast(float, r[6]),
                part_number=cast(str, r[7]),
            )
            for r in found
        ]
