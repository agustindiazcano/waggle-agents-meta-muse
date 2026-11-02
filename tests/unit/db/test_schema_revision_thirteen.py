"""Revision 13 adds the llm_calls table (ADR-077). It holds metadata only: no prompt, no text."""

from waggle.db import schema


def _statements() -> tuple[str, ...]:
    return tuple(" ".join(s.split()) for s in schema._MIGRATIONS[13])


def test_revision_thirteen_is_in_the_chain() -> None:
    assert schema.LATEST_REVISION >= 13
    assert sorted(schema._MIGRATIONS) == list(range(1, schema.LATEST_REVISION + 1))


def test_the_table_carries_the_call_record_fields_and_a_mode_label() -> None:
    table = _statements()[0]
    assert table.startswith("CREATE TABLE llm_calls")
    for column in (
        "request_id",
        "task_id",
        "role",
        "provider",
        "model_id",
        "status",
        "tokens_in",
        "tokens_out",
        "latency_s",
        "cost_usd",
        "fallback_label",
        "mode",
    ):
        assert f" {column} " in table
    assert "status IN ('ok', 'denied', 'error', 'cached')" in table
    assert "mode IN ('mock', 'http')" in table
    assert "created_at timestamptz NOT NULL DEFAULT clock_timestamp()" in table


def test_the_table_has_no_column_for_a_prompt_or_a_response() -> None:
    table = _statements()[0]
    for forbidden in ("prompt", "response", "completion", "body", "content"):
        assert forbidden not in table


def test_costs_and_latency_must_be_finite_and_not_negative() -> None:
    table = _statements()[0]
    assert (
        "cost_usd double precision NOT NULL CHECK (cost_usd >= 0 AND cost_usd < 'Infinity')"
        in table
    )
    assert "tokens_in integer NOT NULL CHECK (tokens_in >= 0)" in table


def test_the_migration_inserts_no_data_and_drops_nothing() -> None:
    upper = " ".join(_statements()).upper()
    for forbidden in ("INSERT", "DROP", "DELETE", "UPDATE", "TRUNCATE"):
        assert forbidden not in upper
