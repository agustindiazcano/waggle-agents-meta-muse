"""Diagnosis retrieval over the failure log: advisory, catalog checked in code, no model."""

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from waggle.experiments.failure_log import FailureCase, FailureMode, generate_failure_log
from waggle.maintenance.diagnosis import (
    DiagnosisEscalation,
    DiagnosisProposal,
    diagnose,
)

CATALOG = frozenset({"PART-BRG-01", "PART-LUB-01", "PART-ALN-01"})
LOG = generate_failure_log(1, 300)
BEARING_POINT = (75.0, 6.82, 7.0)
LUBE_POINT = (82.7, 5.0, 5.74)


def test_a_bearing_like_reading_proposes_the_bearing_mode_and_part() -> None:
    result = diagnose(LOG, *BEARING_POINT, catalog=CATALOG, k=5)
    assert isinstance(result, DiagnosisProposal)
    assert result.mode is FailureMode.BEARING_WEAR
    assert result.part_number == "PART-BRG-01"
    assert len(result.supporting_case_ids) == 5
    by_id = {c.case_id: c for c in LOG}
    assert all(by_id[i].mode is FailureMode.BEARING_WEAR for i in result.supporting_case_ids)


def test_a_lubrication_like_reading_proposes_the_lubrication_part() -> None:
    result = diagnose(LOG, *LUBE_POINT, catalog=CATALOG, k=5)
    assert isinstance(result, DiagnosisProposal)
    assert result.mode is FailureMode.LUBRICATION_LOSS
    assert result.part_number == "PART-LUB-01"


def test_a_part_outside_the_catalog_escalates_and_never_returns_the_part() -> None:
    result = diagnose(LOG, *BEARING_POINT, catalog=frozenset({"PART-LUB-01"}), k=5)
    assert isinstance(result, DiagnosisEscalation)
    assert result.reason == "part_not_in_catalog"
    assert not hasattr(result, "part_number")


def test_an_empty_catalog_escalates() -> None:
    result = diagnose(LOG, *BEARING_POINT, catalog=frozenset(), k=5)
    assert isinstance(result, DiagnosisEscalation)


def test_an_empty_log_escalates_instead_of_guessing() -> None:
    result = diagnose((), *BEARING_POINT, catalog=CATALOG, k=5)
    assert isinstance(result, DiagnosisEscalation)
    assert result.reason == "no_similar_case"


def test_supporting_cases_that_disagree_on_the_part_escalate() -> None:
    bad = [
        dataclasses.replace(c, part_number="PART-EVIL")
        if c.mode is FailureMode.BEARING_WEAR and i % 2 == 0
        else c
        for i, c in enumerate(LOG)
    ]
    result = diagnose(bad, *BEARING_POINT, catalog=CATALOG, k=8)
    assert isinstance(result, DiagnosisEscalation)
    assert result.reason == "mixed_parts"


def test_an_unknown_candidate_mode_raises() -> None:
    with pytest.raises(ValueError, match="mode"):
        diagnose(LOG, *BEARING_POINT, catalog=CATALOG, k=5, modes=("NOT_A_MODE",))


def test_the_candidate_modes_restrict_the_answer() -> None:
    result = diagnose(LOG, *BEARING_POINT, catalog=CATALOG, k=5, modes=(FailureMode.MISALIGNMENT,))
    assert isinstance(result, DiagnosisProposal)
    assert result.mode is FailureMode.MISALIGNMENT


@pytest.mark.parametrize("bad", [math.nan, math.inf, -1.0])
def test_a_reading_that_cannot_be_scored_raises(bad: float) -> None:
    with pytest.raises(ValueError):
        diagnose(LOG, bad, 6.0, 7.0, catalog=CATALOG, k=5)


def test_diagnosis_is_deterministic() -> None:
    first = diagnose(LOG, *BEARING_POINT, catalog=CATALOG, k=5)
    assert first == diagnose(LOG, *BEARING_POINT, catalog=CATALOG, k=5)


def test_the_proposal_is_frozen_data() -> None:
    result = diagnose(LOG, *BEARING_POINT, catalog=CATALOG, k=5)
    assert isinstance(result, DiagnosisProposal)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.part_number = "X"  # type: ignore[misc]  # frozen on purpose


def test_the_module_imports_no_model_or_authority_code() -> None:
    path = Path(__file__).resolve().parents[3] / "src/waggle/maintenance/diagnosis.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    banned = ("waggle.llm", "waggle.mcp_server", "waggle.sim", "waggle.db")
    assert not [n for n in names if n.startswith(banned)]


def test_cases_are_failure_cases() -> None:
    assert all(isinstance(c, FailureCase) for c in LOG)
