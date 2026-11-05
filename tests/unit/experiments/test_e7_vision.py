"""E7 vision mock runner: false accepts first, a trust-the-label baseline that must fail."""

import pytest

from waggle.experiments.e7_vision import VISION_CASES, VisionCase, run_vision_mock


def test_the_fixtures_are_declared_with_a_target_layer_and_are_all_pending_review() -> None:
    ids = [case.case_id for case in VISION_CASES]
    assert len(ids) == len(set(ids)) >= 8
    assert all(case.target_layer for case in VISION_CASES)
    assert all(case.reviewed is False for case in VISION_CASES)


def test_the_fixtures_cover_the_declared_categories() -> None:
    categories = {case.category for case in VISION_CASES}
    assert {
        "correct",
        "blurred",
        "conflicting",
        "injection",
        "injection_missed_by_guard",
        "unknown_id",
        "invalid_output",
    } <= categories


def test_the_full_arm_makes_no_false_accept_on_the_fixtures() -> None:
    full = run_vision_mock()["arms"]["full"]
    assert full["false_accepts"]["count"] == 0
    assert full["false_accepts"]["failing_cases"] == []


def test_the_trust_label_baseline_shows_false_accepts() -> None:
    baseline = run_vision_mock()["arms"]["trust_label"]
    assert baseline["false_accepts"]["count"] >= 3
    assert baseline["false_accepts"]["failing_cases"]


def test_false_accepts_are_reported_before_any_other_figure() -> None:
    arm = run_vision_mock()["arms"]["full"]
    assert next(iter(arm)) == "false_accepts"


def test_every_proportion_has_counts_and_a_wilson_interval() -> None:
    entry = run_vision_mock()["arms"]["full"]["false_accepts"]
    assert entry["total"] == len(VISION_CASES)
    low, high = entry["wilson95"]
    assert 0.0 <= low <= high <= 1.0


def test_the_report_says_it_is_a_mock_run_that_measures_the_rule_not_a_model() -> None:
    report = run_vision_mock()
    assert report["mode"] == "mock"
    assert report["model_ids"] == []
    assert report["llm_calls"] == 0
    assert "rule" in report["note"] and "not a model" in report["note"]
    assert report["pending_review"] == [case.case_id for case in VISION_CASES]


def test_the_report_records_the_prompt_version_and_the_case_set() -> None:
    report = run_vision_mock()
    assert report["prompt_versions"] == {"vision": "vision-v1"}
    assert report["case_set"] == "fixtures"


def test_two_runs_give_the_same_report() -> None:
    assert run_vision_mock() == run_vision_mock()


def test_false_rejects_unknowns_and_escalations_are_counted_apart() -> None:
    arm = run_vision_mock()["arms"]["full"]
    assert arm["false_rejects"]["count"] >= 1
    assert arm["unknown"]["count"] >= 1
    assert arm["escalated"] >= 1


def test_a_correct_case_is_identified_in_the_full_arm() -> None:
    cases = (
        VisionCase(
            "X-1",
            '{"label_text":"PKG-7","obstruction_class":"none","legibility":0.95}',
            "PKG-7",
            "benign",
            "registry_lookup",
            False,
        ),
    )
    arm = run_vision_mock(cases)["arms"]["full"]
    assert arm["false_accepts"]["count"] == 0
    assert arm["false_rejects"]["count"] == 0


def test_an_empty_case_set_is_an_error_not_a_pass() -> None:
    with pytest.raises(ValueError):
        run_vision_mock(())
