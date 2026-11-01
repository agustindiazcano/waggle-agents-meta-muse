"""E3 runner for the read-back and item resolution layer (ADR-057)."""

from pathlib import Path

from waggle.experiments.e3_eval import RUNNABLE_LAYERS, load_cases
from waggle.experiments.e3_readback import ATTEMPTS, READBACK_LAYER, run_readback
from waggle.governance.readback import Decision, ReadBackPrompt

ROOT = Path(__file__).resolve().parents[3]
CASES = load_cases(ROOT / "data" / "e3" / "cases.json")
LAYER_IDS = {c.id for c in CASES if c.target_layer == READBACK_LAYER}


def test_every_read_back_case_has_exactly_one_attempt() -> None:
    assert set(ATTEMPTS) == LAYER_IDS
    assert len(LAYER_IDS) == 3


def test_the_read_back_layer_is_runnable() -> None:
    assert READBACK_LAYER in RUNNABLE_LAYERS


def test_the_production_layer_blocks_both_injections_and_serves_the_read_back() -> None:
    report = run_readback(CASES)
    assert report.missed_injections == ()
    assert report.false_blocks == ()
    assert [o.case_id for o in report.outcomes] == ["E3-T4-01", "E3-T4-02", "E3-T4-03"]
    assert all(o.correct for o in report.outcomes)


def test_a_layer_that_executes_without_confirmation_is_reported() -> None:
    # Sensitivity: an authorizer that trusts the transcript lets both injections through.
    def trusting(
        prompt: ReadBackPrompt, transcript: str, confirmation: object, known: object
    ) -> Decision:
        return Decision(True, "confirmed", prompt.item_id)

    report = run_readback(CASES, authorizer=trusting)
    assert report.missed_injections == ("E3-T4-01", "E3-T4-02")


def test_a_layer_that_refuses_everything_reports_the_benign_false_block() -> None:
    def refusing(
        prompt: ReadBackPrompt, transcript: str, confirmation: object, known: object
    ) -> Decision:
        return Decision(False, "no_confirmation")

    def no_prompt(prompt_id: str, item_id: str, known: object) -> ReadBackPrompt:
        raise ValueError("unknown item")

    report = run_readback(CASES, authorizer=refusing, starter=no_prompt)
    assert report.false_blocks == ("E3-T4-03",)
