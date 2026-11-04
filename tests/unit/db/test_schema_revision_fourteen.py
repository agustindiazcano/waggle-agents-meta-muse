"""Revision 14 adds the failure_history table (ADR-084). Forward only, no data, nothing dropped."""

from waggle.db import schema


def _statements() -> tuple[str, ...]:
    return tuple(" ".join(s.split()) for s in schema._MIGRATIONS[14])


def test_revision_fourteen_is_in_the_chain() -> None:
    assert schema.LATEST_REVISION >= 14
    assert sorted(schema._MIGRATIONS) == list(range(1, schema.LATEST_REVISION + 1))


def test_the_table_carries_the_case_fields_and_a_source_label() -> None:
    table = _statements()[0]
    assert table.startswith("CREATE TABLE failure_history")
    for column in (
        "case_id",
        "machine_class",
        "mode",
        "onset_to_failure_ticks",
        "peak_temperature_c",
        "peak_vibration_rms",
        "peak_current_a",
        "part_number",
        "source",
    ):
        assert f" {column} " in table
    assert "case_id text PRIMARY KEY" in table
    assert "created_at timestamptz NOT NULL DEFAULT clock_timestamp()" in table


def test_the_mode_and_machine_class_are_closed_sets() -> None:
    table = _statements()[0]
    assert "mode IN ('BEARING_WEAR', 'LUBRICATION_LOSS', 'MISALIGNMENT')" in table
    assert "machine_class IN ('conveyor', 'pump', 'lift')" in table


def test_peaks_must_be_finite_and_not_negative() -> None:
    table = _statements()[0]
    for column in ("peak_temperature_c", "peak_vibration_rms", "peak_current_a"):
        assert (
            f"{column} double precision NOT NULL CHECK ({column} >= 0 AND {column} < 'Infinity')"
            in table
        )
    assert "onset_to_failure_ticks bigint NOT NULL CHECK (onset_to_failure_ticks >= 1)" in table


def test_the_table_has_no_column_for_free_text_from_a_manual_or_a_model() -> None:
    table = _statements()[0]
    for forbidden in ("prompt", "response", "notes", "description", "text_body", "manual"):
        assert forbidden not in table


def test_the_migration_inserts_no_data_and_drops_nothing() -> None:
    upper = " ".join(_statements()).upper()
    for forbidden in ("INSERT", "DROP", "DELETE", "UPDATE", "TRUNCATE"):
        assert forbidden not in upper
