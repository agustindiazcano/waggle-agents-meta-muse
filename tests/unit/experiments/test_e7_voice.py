"""E7 voice mock runner: false accepts first, a baseline without read-back that must fail."""

import pytest

from waggle.experiments.e7_voice import VOICE_CASES, VoiceCase, run_voice_mock


def test_the_fixtures_are_declared_with_a_target_layer_and_are_all_pending_review() -> None:
    ids = [case.case_id for case in VOICE_CASES]
    assert len(ids) == len(set(ids)) >= 10
    assert all(case.target_layer for case in VOICE_CASES)
    assert all(case.reviewed is False for case in VOICE_CASES)


def test_the_pipeline_makes_no_false_accept_on_the_fixtures() -> None:
    report = run_voice_mock()
    full = report["arms"]["full"]
    assert full["false_accepts"]["count"] == 0
    assert full["false_accepts"]["failing_cases"] == []


def test_the_baseline_without_read_back_shows_false_accepts() -> None:
    baseline = run_voice_mock()["arms"]["no_readback"]
    assert baseline["false_accepts"]["count"] >= 3
    assert baseline["false_accepts"]["failing_cases"]


def test_false_accepts_are_reported_before_any_accuracy_figure() -> None:
    arm = run_voice_mock()["arms"]["full"]
    assert next(iter(arm)) == "false_accepts"


def test_every_proportion_has_counts_and_a_wilson_interval() -> None:
    entry = run_voice_mock()["arms"]["full"]["false_accepts"]
    assert entry["total"] == len(VOICE_CASES)
    low, high = entry["wilson95"]
    assert 0.0 <= low <= high <= 1.0


def test_the_report_says_it_is_a_mock_run_that_measures_the_rule_not_a_model() -> None:
    report = run_voice_mock()
    assert report["mode"] == "mock"
    assert report["model_ids"] == []
    assert report["llm_calls"] == 0
    assert "rule" in report["note"] and "not a model" in report["note"]
    assert report["pending_review"] == [case.case_id for case in VOICE_CASES]


def test_the_report_records_the_prompt_version_and_the_case_set() -> None:
    report = run_voice_mock()
    assert report["prompt_versions"] == {"voice": "voice-v1"}
    assert report["case_set"] == "fixtures"


def test_two_runs_give_the_same_report() -> None:
    assert run_voice_mock() == run_voice_mock()


def test_false_rejects_and_escalations_are_counted_apart() -> None:
    arm = run_voice_mock()["arms"]["full"]
    assert arm["false_rejects"]["count"] >= 0
    assert arm["escalated"] >= 1
    assert arm["repeat_requested"] >= 1


def test_a_case_that_expects_an_item_must_execute_it_with_a_typed_confirmation() -> None:
    cases = (VoiceCase("X-1", "pick item 7", "ITEM-7", "ITEM-7", True, "benign", "t", False),)
    arm = run_voice_mock(cases)["arms"]["full"]
    assert arm["false_accepts"]["count"] == 0
    assert arm["false_rejects"]["count"] == 0


def test_a_case_with_no_confirmation_never_executes_in_the_full_arm() -> None:
    cases = (VoiceCase("X-2", "pick item 7", "ITEM-7", None, False, "benign", "t", False),)
    arm = run_voice_mock(cases)["arms"]["full"]
    assert arm["false_accepts"]["count"] == 0


def test_an_empty_case_set_is_an_error_not_a_pass() -> None:
    with pytest.raises(ValueError):
        run_voice_mock(())
