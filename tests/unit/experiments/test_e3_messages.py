"""E3 runner for the message schema layer (ADR-055)."""

from pathlib import Path

from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.experiments.e3_messages import MESSAGE_LAYER, run_message_schema

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")


def test_the_message_layer_is_runnable() -> None:
    assert MESSAGE_LAYER in RUNNABLE_LAYERS


def test_the_override_message_is_blocked() -> None:
    report = run_message_schema(CASES)
    assert [o.case_id for o in report.outcomes] == ["E3-T5-02"]
    assert report.missed_injections == ()
    assert report.outcomes[0].code == "unknown_field"


def test_a_schema_that_ignores_extra_fields_is_reported() -> None:
    # Sensitivity: a parser that only checks the three known fields lets the case through.
    def lax(raw: str, sender: str) -> object:
        return object()

    report = run_message_schema(CASES, parser=lax)
    assert report.missed_injections == ("E3-T5-02",)
