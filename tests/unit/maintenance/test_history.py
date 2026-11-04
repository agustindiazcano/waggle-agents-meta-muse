"""Database diagnosis reads committed history and keeps machine classes separate."""

from unittest.mock import MagicMock

import psycopg
import pytest

from waggle.db.connection import Database
from waggle.db.failure_history import FailureHistory
from waggle.maintenance.diagnosis import DiagnosisEscalation, DiagnosisProposal
from waggle.maintenance.history import DatabaseDiagnosis
from waggle.maintenance.predictor import Reading


def test_database_rows_are_converted_and_filtered_after_transaction() -> None:
    database = MagicMock(spec=Database)
    connection = database.transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = [
        ("case-real-1", "pump", "BEARING_WEAR", 100, 60.0, 3.0, 4.0, "P-1"),
        ("case-real-2", "lift", "MISALIGNMENT", 100, 60.0, 3.0, 4.0, "P-2"),
    ]
    found = DatabaseDiagnosis(FailureHistory(database)).diagnose(
        "pump", Reading(1, 10, 60.0, 3.0, 4.0, 0.5), {"P-1", "P-2"}
    )
    assert isinstance(found, DiagnosisProposal)
    assert found.part_number == "P-1"
    assert found.supporting_case_ids == ("case-real-1",)
    database.transaction.return_value.__exit__.assert_called_once()


def test_missing_history_escalates() -> None:
    database = MagicMock(spec=Database)
    connection = database.transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = []
    assert DatabaseDiagnosis(FailureHistory(database)).diagnose(
        "pump", Reading(1, 10, 60.0, 3.0, 4.0, 0.5), {"P-1"}
    ) == DiagnosisEscalation("no_similar_case")


def test_database_failure_is_a_real_error() -> None:
    database = MagicMock(spec=Database)
    database.transaction.side_effect = psycopg.OperationalError("unavailable")
    with pytest.raises(psycopg.OperationalError):
        DatabaseDiagnosis(FailureHistory(database)).diagnose(
            "pump", Reading(1, 10, 60.0, 3.0, 4.0, 0.5), {"P-1"}
        )


def test_unknown_machine_class_is_rejected_before_database() -> None:
    database = MagicMock(spec=Database)
    with pytest.raises(ValueError, match="machine class"):
        DatabaseDiagnosis(FailureHistory(database)).diagnose(
            "unknown", Reading(1, 10, 60.0, 3.0, 4.0, 0.5), {"P-1"}
        )
    database.transaction.assert_not_called()
