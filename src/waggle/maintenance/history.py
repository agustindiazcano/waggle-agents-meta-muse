"""Advisory deterministic diagnosis from committed database failure history.

The repository closes its read transaction before returning rows. No tool is called here;
database and malformed-history errors propagate instead of masquerading as an empty history.
"""

from collections.abc import Set

from waggle.db.failure_history import MACHINE_CLASSES, FailureHistory
from waggle.maintenance.diagnosis import DiagnosisEscalation, DiagnosisProposal, diagnose
from waggle.maintenance.failure_cases import FailureCase, FailureMode
from waggle.maintenance.predictor import Reading


class DatabaseDiagnosis:
    """Load history for the requested machine class, then propose a mode and catalog part."""

    def __init__(self, history: FailureHistory) -> None:
        self._history = history

    def diagnose(
        self, machine_class: str, reading: Reading, catalog: Set[str], k: int = 5
    ) -> DiagnosisProposal | DiagnosisEscalation:
        """Read a fresh committed history snapshot; no match returns an explicit escalation."""
        if machine_class not in MACHINE_CLASSES:
            raise ValueError("invalid machine class")
        cases = [
            FailureCase(
                row.case_id,
                row.machine_class,
                FailureMode(row.mode),
                row.onset_to_failure_ticks,
                row.peak_temperature_c,
                row.peak_vibration_rms,
                row.peak_current_a,
                row.part_number,
            )
            for row in self._history.rows()
            if row.machine_class == machine_class
        ]
        return diagnose(cases, reading.temperature, reading.vibration, reading.current, catalog, k)
