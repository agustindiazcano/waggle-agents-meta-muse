"""E3 declarations and review metadata are checked without evaluating a model."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "e3" / "cases.json"
TARGETS = {
    "T1": {"mcp_identity"},
    "T2": {"mcp_schema_bounds", "fast_layer"},
    "T3": {"catalog_check"},
    "T4": {"read_back_item_resolution"},
    "T5": {"message_schema", "mcp_identity"},
    "T6": {"court_unanimity"},
    "T11": {"output_schema"},
    "T18": {"untrusted_data_boundary", "plan_schema", "plan_validator", "mcp_identity"},
}
FIELDS = {
    "id",
    "threat",
    "target_layer",
    "source",
    "entry_point",
    "setup",
    "input",
    "probe",
    "construction",
    "review",
}
SOURCES = {
    "package_label",
    "sop_text",
    "manual_text",
    "voice_transcript",
    "robot_message",
    "model_output",
    "incident_text",
}


def cases() -> list[dict[str, object]]:
    """Read the development corpus, failing on missing files or invalid structure."""
    payload: object = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert set(payload) == {"version", "split", "cases"}
    assert payload["version"] == 1
    assert payload["split"] == "dev"
    rows = payload["cases"]
    assert isinstance(rows, list) and rows
    result: list[dict[str, object]] = []
    for row in rows:
        assert isinstance(row, dict)
        result.append(row)
    return result


def assert_case(case: dict[str, object]) -> None:
    """Validate a declaration without deciding its ground-truth label."""
    assert set(case) == FIELDS
    for field in FIELDS - {"review"}:
        assert isinstance(case[field], str) and str(case[field]).strip(), field
    threat = str(case["threat"])
    assert threat in TARGETS
    assert case["target_layer"] in TARGETS[threat]
    assert str(case["id"]).startswith(f"E3-{threat}-")
    assert case["source"] in SOURCES
    assert case["construction"] in {"directive", "reference", "malformed_output"}
    review = case["review"]
    assert isinstance(review, dict)
    assert set(review) == {"status", "label", "reviewer", "rationale"}
    assert review["status"] in {"pending", "reviewed"}
    if review["status"] == "pending":
        assert all(review[field] is None for field in ("label", "reviewer", "rationale"))
    else:
        assert review["label"] in {"benign", "injection", "uncertain"}
        for field in ("reviewer", "rationale"):
            assert isinstance(review[field], str) and review[field].strip(), field


def test_corpus_has_unique_ids_and_declared_target_layers() -> None:
    rows = cases()
    for row in rows:
        assert_case(row)
    assert len({row["id"] for row in rows}) == len(rows)
    assert {row["threat"] for row in rows} == set(TARGETS)


@pytest.mark.parametrize("threat", list(TARGETS))
def test_every_threat_has_references_and_multiple_probes(threat: str) -> None:
    rows = [row for row in cases() if row["threat"] == threat]
    assert any(row["construction"] == "reference" for row in rows)
    assert sum(row["construction"] != "reference" for row in rows) >= 2
    assert len({row["input"] for row in rows}) == len(rows)


def test_reviewed_case_accepts_a_label_with_reviewer_and_rationale() -> None:
    row = dict(cases()[0])
    row["review"] = {
        "status": "reviewed",
        "label": "uncertain",
        "reviewer": "maintainer_fixture",
        "rationale": "Synthetic metadata for validation only, not a corpus review.",
    }
    assert_case(row)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_layer", "guard_only"),
        ("threat", "T99"),
        ("input", ""),
        ("source", "trusted_system"),
        ("review", {"status": "pending", "label": "benign", "reviewer": None, "rationale": None}),
        ("review", {"status": "reviewed", "label": "benign", "reviewer": None, "rationale": "x"}),
        ("review", {"status": "reviewed", "label": "benign", "reviewer": "M", "rationale": ""}),
    ],
)
def test_invalid_declarations_or_unreviewed_labels_are_detected(field: str, value: object) -> None:
    row = dict(cases()[0])
    row[field] = value
    with pytest.raises(AssertionError):
        assert_case(row)


def test_threat_ids_match_the_written_threat_model() -> None:
    model = (ROOT / "docs" / "THREAT_MODEL.md").read_text(encoding="utf-8")
    for threat in TARGETS:
        assert f"| {threat} |" in model


def test_t11_contains_duplicate_keys_and_oversized_reason_output() -> None:
    raw = [str(row["input"]) for row in cases() if row["threat"] == "T11"]
    assert any(text.count('"label"') == 2 for text in raw)
    assert any("a" * 65 in text for text in raw)
