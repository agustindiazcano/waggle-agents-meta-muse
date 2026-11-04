"""Cloud-only checks of the failure_history table and its repository (revision 14)."""

import psycopg.errors
import pytest
from postgres_support import isolated_database

from waggle.db.connection import Database
from waggle.db.failure_history import FailureHistory, FailureRow
from waggle.db.schema import current_revision, migrate

pytestmark = pytest.mark.heavy


def _row(case_id: str, **changes: object) -> FailureRow:
    base: dict[str, object] = dict(
        case_id=case_id,
        machine_class="pump",
        mode="BEARING_WEAR",
        onset_to_failure_ticks=900,
        peak_temperature_c=75.0,
        peak_vibration_rms=6.8,
        peak_current_a=7.0,
        part_number="PART-BRG-01",
    )
    base.update(changes)
    return FailureRow(**base)  # type: ignore[arg-type]


def test_revision_fourteen_upgrade_adds_an_empty_table() -> None:
    with isolated_database() as db:
        assert migrate(db, expected_revision=0, target_revision=13) == 13
        assert migrate(db, expected_revision=13, target_revision=14) == 14
        assert current_revision(db) == 14
        assert FailureHistory(db).rows() == []


def test_rows_come_back_ordered_and_equal(database: Database) -> None:
    repo = FailureHistory(database)
    rows = [_row("fl-2"), _row("fl-1", mode="MISALIGNMENT", part_number="PART-ALN-01")]
    for row in rows:
        assert repo.add(row, source="synthetic") is True
    assert repo.rows() == sorted(rows, key=lambda r: r.case_id)


def test_a_repeated_case_id_keeps_the_first_write(database: Database) -> None:
    repo = FailureHistory(database)
    assert repo.add(_row("fl-1"), source="synthetic") is True
    assert repo.add(_row("fl-1", onset_to_failure_ticks=5), source="synthetic") is False
    assert [r.onset_to_failure_ticks for r in repo.rows()] == [900]


def test_the_table_refuses_an_unknown_mode_and_a_negative_peak(database: Database) -> None:
    for sql in (
        "INSERT INTO failure_history (case_id, machine_class, mode, onset_to_failure_ticks, "
        "peak_temperature_c, peak_vibration_rms, peak_current_a, part_number, source) "
        "VALUES ('a', 'pump', 'FIRE', 1, 1, 1, 1, 'P', 's')",
        "INSERT INTO failure_history (case_id, machine_class, mode, onset_to_failure_ticks, "
        "peak_temperature_c, peak_vibration_rms, peak_current_a, part_number, source) "
        "VALUES ('b', 'pump', 'MISALIGNMENT', 1, -1, 1, 1, 'P', 's')",
    ):
        with pytest.raises(psycopg.errors.CheckViolation), database.transaction() as connection:
            connection.execute(sql)
