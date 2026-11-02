"""E4 review set: schema, loader, and the refusal of pending cases (AGENTS.md 10.2)."""

import json
from pathlib import Path

import pytest

from waggle.experiments.e4_cases import (
    EvalCase,
    PendingCaseError,
    ReviewSetError,
    load_for_evaluation,
    load_review_set,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "data" / "e4" / "review_set.example.json"


def _case(
    case_id: str, review: dict[str, object] | None = None, *, split: str = "development"
) -> dict[str, object]:
    base_review: dict[str, object] = {
        "status": "reviewed",
        "label": "benign",
        "reviewer": "maintainer",
        "rationale": "Plain move inside one zone.",
    }
    base_review.update(review or {})
    return {
        "id": case_id,
        "split": split,
        "task": "Move ITEM-1 from Z1 to DOCK",
        "item_resolution": "ITEM-1 resolved: unique, in stock",
        "world_summary": "DOCK free",
        "excerpts": [{"source": "sop_text", "text": "Keep aisles clear."}],
        "code_check": "pass",
        "review": base_review,
    }


def _write(tmp_path: Path, cases: list[dict[str, object]], **top: object) -> Path:
    path = tmp_path / "set.json"
    path.write_text(json.dumps({"version": 1, "cases": cases, **top}), encoding="utf-8")
    return path


def test_the_example_file_loads_and_every_case_is_pending() -> None:
    review_set = load_review_set(EXAMPLE)
    assert review_set.synthetic_placeholder is True
    assert len(review_set.cases) >= 3
    assert all(case.status == "pending" for case in review_set.cases)
    assert all(case.label is None for case in review_set.cases)


def test_an_evaluation_never_reads_the_example_file() -> None:
    with pytest.raises(PendingCaseError):
        load_for_evaluation(EXAMPLE, "development")


def test_reviewed_cases_load_for_the_requested_split(tmp_path: Path) -> None:
    path = _write(
        tmp_path, [_case("A-1"), _case("A-2", {"label": "risky"}), _case("H-1", split="held_out")]
    )
    cases = load_for_evaluation(path, "development")
    assert [c.id for c in cases] == ["A-1", "A-2"]
    assert isinstance(cases[0], EvalCase)
    assert [c.label for c in cases] == ["benign", "risky"]


def test_a_pending_case_in_the_split_refuses_the_whole_evaluation(tmp_path: Path) -> None:
    path = _write(tmp_path, [_case("A-1"), _case("A-2", {"status": "pending", "label": None})])
    with pytest.raises(PendingCaseError, match="A-2"):
        load_for_evaluation(path, "development")


def test_a_pending_case_in_another_split_does_not_block_this_one(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [_case("A-1"), _case("H-1", {"status": "pending", "label": None}, split="held_out")],
    )
    assert [c.id for c in load_for_evaluation(path, "development")] == ["A-1"]
    with pytest.raises(PendingCaseError):
        load_for_evaluation(path, "held_out")


@pytest.mark.parametrize(
    "review",
    [
        {"label": None},
        {"label": "maybe"},
        {"reviewer": ""},
        {"rationale": "  "},
        {"status": "approved"},
    ],
)
def test_a_reviewed_case_with_a_missing_or_bad_label_is_refused(
    tmp_path: Path, review: dict[str, object]
) -> None:
    path = _write(tmp_path, [_case("A-1", review)])
    with pytest.raises((PendingCaseError, ReviewSetError)):
        load_for_evaluation(path, "development")


def test_an_empty_selection_is_an_error_not_an_empty_pass(tmp_path: Path) -> None:
    path = _write(tmp_path, [_case("H-1", split="held_out")])
    with pytest.raises(ReviewSetError, match="no cases"):
        load_for_evaluation(path, "development")


def test_a_synthetic_placeholder_file_is_refused_even_if_reviewed(tmp_path: Path) -> None:
    path = _write(tmp_path, [_case("A-1")], synthetic_placeholder=True)
    with pytest.raises(PendingCaseError, match="placeholder"):
        load_for_evaluation(path, "development")


@pytest.mark.parametrize("seed_set", ["dev", "test", ""])
def test_an_unknown_seed_set_is_refused(tmp_path: Path, seed_set: str) -> None:
    with pytest.raises(ReviewSetError, match="seed set"):
        load_for_evaluation(_write(tmp_path, [_case("A-1")]), seed_set)


def test_duplicate_ids_and_unknown_fields_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ReviewSetError, match="duplicate"):
        load_review_set(_write(tmp_path, [_case("A-1"), _case("A-1")]))
    extra = _case("A-2")
    extra["expected_vote"] = "approve"
    with pytest.raises(ReviewSetError, match="unknown"):
        load_review_set(_write(tmp_path, [extra]))


def test_the_review_request_fences_the_excerpts_through_the_sanitizers(tmp_path: Path) -> None:
    case = load_for_evaluation(_write(tmp_path, [_case("A-1")]), "development")[0]
    request = case.review_request()
    assert request.task == "Move ITEM-1 from Z1 to DOCK"
    assert request.excerpts[0].text == "Keep aisles clear."
    assert case.code_check == "pass"
