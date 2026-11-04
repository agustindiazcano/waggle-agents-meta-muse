"""Load a failure log into FailureHistory (ADR-088). A repeat is a skip; a bad row aborts."""

import io
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from db_fakes import FakeDatabase

from waggle.db.failure_history import FailureHistory, FailureRow
from waggle.experiments.failure_history_loader import load_failure_history, main
from waggle.experiments.failure_log import generate_failure_log
from waggle.maintenance.failure_cases import FailureMode


@dataclass(frozen=True)
class _Case:
    case_id: str
    machine_class: str
    mode: FailureMode
    onset_to_failure_ticks: int
    peak_temperature_c: float
    peak_vibration_rms: float
    peak_current_a: float
    part_number: str


class _RecordingHistory:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self._seen: set[str] = set()

    def add(self, row: FailureRow, *, source: str) -> bool:
        self.ids.append(row.case_id)
        if row.case_id in self._seen:
            return False
        self._seen.add(row.case_id)
        return True


def test_a_generated_log_issues_one_insert_per_case() -> None:
    cases = generate_failure_log(seed=11, count=7)
    database = FakeDatabase(lambda sql, params: None)
    result = load_failure_history(FailureHistory(database), cases, "synthetic")  # type: ignore[arg-type]
    assert (result.inserted, result.skipped) == (7, 0)
    writes = database.writes()
    assert len(writes) == 7
    assert all(item.startswith("INSERT INTO failure_history") for item in writes)
    assert all("ON CONFLICT (case_id) DO NOTHING" in item for item in writes)


def test_a_second_load_of_the_same_cases_skips_every_id() -> None:
    cases = generate_failure_log(seed=11, count=7)
    history = _RecordingHistory()
    first = load_failure_history(history, cases, "synthetic")
    second = load_failure_history(history, cases, "synthetic")
    assert (first.inserted, first.skipped) == (7, 0)
    assert (second.inserted, second.skipped) == (0, 7)
    assert history.ids == [case.case_id for case in cases] * 2


def test_the_first_invalid_row_raises_and_later_cases_are_not_added() -> None:
    good = generate_failure_log(seed=3, count=1)[0]
    bad = _Case(
        case_id="fl-00001",
        machine_class="crane",
        mode=FailureMode.BEARING_WEAR,
        onset_to_failure_ticks=10,
        peak_temperature_c=1.0,
        peak_vibration_rms=1.0,
        peak_current_a=1.0,
        part_number="PART-BRG-01",
    )
    later = _Case(
        case_id="fl-00002",
        machine_class="pump",
        mode=FailureMode.BEARING_WEAR,
        onset_to_failure_ticks=10,
        peak_temperature_c=1.0,
        peak_vibration_rms=1.0,
        peak_current_a=1.0,
        part_number="PART-BRG-01",
    )
    database = FakeDatabase(lambda sql, params: None)
    with pytest.raises(ValueError):
        load_failure_history(
            FailureHistory(database),  # type: ignore[arg-type]
            (good, bad, later),  # type: ignore[arg-type]
            "synthetic",
        )
    assert len(database.writes()) == 1


def test_wrong_argv_returns_2_and_does_not_construct_a_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = MagicMock(side_effect=AssertionError("database constructed"))
    monkeypatch.setattr(
        "waggle.experiments.failure_history_loader.Database.from_environ",
        constructed,
    )
    err = io.StringIO()
    code = main(["1", "2"], {"DATABASE_URL": "postgresql://secret.example/db"}, err)
    assert code == 2
    constructed.assert_not_called()
    text = err.getvalue()
    assert "usage:" in text
    assert "secret.example" not in text


def test_missing_database_url_returns_2_and_stderr_has_no_value() -> None:
    err = io.StringIO()
    code = main(["1", "3", "synthetic"], {"OTHER": "leaked-secret-value"}, err)
    assert code == 2
    text = err.getvalue()
    assert "leaked-secret-value" not in text
    assert "postgresql" not in text.lower()
