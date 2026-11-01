"""E3 evaluator pieces: reviewed cases only, explicit layers, structure scored on its own."""

import asyncio
import json
from pathlib import Path

import pytest

from waggle.experiments.e3_eval import (
    STRUCTURAL_EXPECTED,
    Case,
    MissingLayer,
    PendingCases,
    load_cases,
    plan_layers,
    score_structure,
    screen_cases,
)
from waggle.governance.classifier import MockClassifier

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "e3" / "cases.json"
PASS_ALL = '{"label":"benign","reason_code":"fixture"}'
REJECT_ALL = '{"label":"injection","reason_code":"fixture"}'


def _write(tmp_path: Path, change: dict[str, object]) -> Path:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    data["cases"][0]["review"].update(change)
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_reviewed_corpus_loads_with_its_labels() -> None:
    cases = load_cases(CORPUS)
    assert len(cases) == 25
    assert {c.label for c in cases} <= {"benign", "injection", "uncertain"}


@pytest.mark.parametrize(
    "change",
    [
        {"status": "pending"},
        {"label": None},
        {"reviewer": ""},
        {"rationale": "  "},
        {"label": "maybe"},
    ],
)
def test_a_pending_or_incomplete_case_is_refused_before_anything_runs(
    tmp_path: Path, change: dict[str, object]
) -> None:
    with pytest.raises(PendingCases):
        load_cases(_write(tmp_path, change))


def test_structure_is_scored_against_the_declared_expectation_not_a_guard_label() -> None:
    outcomes = {o.case_id: o for o in score_structure(load_cases(CORPUS))}
    assert {k: o.valid for k, o in outcomes.items()} == STRUCTURAL_EXPECTED
    assert all(o.correct for o in outcomes.values())


def test_the_structural_expectation_matches_the_corpus_readme() -> None:
    assert STRUCTURAL_EXPECTED == {"E3-T11-01": False, "E3-T11-02": False, "E3-T11-03": True}


def test_a_target_layer_without_a_runner_is_a_real_error() -> None:
    with pytest.raises(MissingLayer, match="catalog_check"):
        plan_layers(load_cases(CORPUS), available=frozenset({"output_schema"}), selected=None)


def test_a_subset_lists_everything_it_did_not_evaluate() -> None:
    run, skipped = plan_layers(
        load_cases(CORPUS),
        available=frozenset({"output_schema"}),
        selected=frozenset({"output_schema"}),
    )
    assert {c.id for c in run} == set(STRUCTURAL_EXPECTED)
    assert len(run) + len(skipped) == 25
    assert all(reason for _, reason in skipped)


def test_selecting_a_layer_that_has_no_runner_fails() -> None:
    with pytest.raises(MissingLayer):
        plan_layers(
            load_cases(CORPUS),
            available=frozenset({"output_schema"}),
            selected=frozenset({"plan_schema"}),
        )


def test_guard_screening_excludes_model_output_and_uncertain_cases() -> None:
    report = asyncio.run(screen_cases(load_cases(CORPUS), MockClassifier(PASS_ALL)))
    assert report.evaluated == 22
    assert not any(i.startswith("E3-T11") for i in report.ids)


def test_a_guard_that_passes_everything_misses_every_injection() -> None:
    cases = load_cases(CORPUS)
    report = asyncio.run(screen_cases(cases, MockClassifier(PASS_ALL)))
    injections = {c.id for c in cases if c.label == "injection"}
    assert set(report.missed_injections) == injections
    assert report.false_rejections == ()
    low, high = report.miss_interval
    assert 0.0 <= low <= high <= 1.0 and high > 0.8


def test_a_guard_that_rejects_everything_has_no_misses_but_false_rejections() -> None:
    cases = load_cases(CORPUS)
    report = asyncio.run(screen_cases(cases, MockClassifier(REJECT_ALL)))
    benign = {c.id for c in cases if c.label == "benign"}
    assert report.missed_injections == ()
    assert set(report.false_rejections) == benign


def test_incident_text_cases_reach_the_guard_through_a_real_sanitizer_source() -> None:
    classifier = MockClassifier(PASS_ALL)
    asyncio.run(screen_cases(load_cases(CORPUS), classifier))
    assert any('source="incident_text"' in seen for seen in classifier.inputs)


def test_case_is_a_plain_frozen_record() -> None:
    case = load_cases(CORPUS)[0]
    assert isinstance(case, Case)
    with pytest.raises(AttributeError):
        case.label = "benign"  # type: ignore[misc]
