"""FailureHistory refuses a bad record before any query and writes one INSERT per case."""

import pytest
from db_fakes import FakeDatabase

from waggle.db.failure_history import FailureHistory, FailureRow


def _row(**changes: object) -> FailureRow:
    base: dict[str, object] = dict(
        case_id="fl-00001",
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


def _repo() -> tuple[FailureHistory, FakeDatabase]:
    db = FakeDatabase(lambda sql, params: None)
    return FailureHistory(db), db  # type: ignore[arg-type]


def test_a_row_is_one_insert_that_ignores_a_repeated_case_id() -> None:
    repo, db = _repo()
    repo.add(_row(), source="synthetic")
    assert len(db.writes()) == 1
    assert db.writes()[0].startswith("INSERT INTO failure_history")
    assert "ON CONFLICT (case_id) DO NOTHING" in db.writes()[0]


@pytest.mark.parametrize(
    "changes",
    [
        {"case_id": ""},
        {"case_id": "x" * 65},
        {"machine_class": "crane"},
        {"mode": "FIRE"},
        {"onset_to_failure_ticks": 0},
        {"onset_to_failure_ticks": True},
        {"peak_temperature_c": float("nan")},
        {"peak_vibration_rms": float("inf")},
        {"peak_current_a": -1.0},
        {"part_number": "bad part"},
    ],
)
def test_an_invalid_field_is_refused_before_any_query(changes: dict[str, object]) -> None:
    repo, db = _repo()
    with pytest.raises(ValueError):
        repo.add(_row(**changes), source="synthetic")
    assert db.log == []


@pytest.mark.parametrize("source", ["", "x" * 65, 3])
def test_a_bad_source_label_is_refused(source: object) -> None:
    repo, db = _repo()
    with pytest.raises(ValueError):
        repo.add(_row(), source=source)  # type: ignore[arg-type]
    assert db.log == []
