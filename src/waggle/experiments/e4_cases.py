"""E4 review set: schema and loader (COURT_DESIGN sections 8 and 10, AGENTS.md 10.2).

Labels are written and decided by the maintainer before any run. This module only defines the
file schema and refuses to start an evaluation on anything that is not fully reviewed: a pending
case, a missing label, a missing reviewer or rationale, or a file marked as a synthetic
placeholder. The example file under ``data/e4`` is a placeholder and is never read by an
evaluation.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from waggle.governance.court_contract import ReviewRequest
from waggle.governance.sanitizers import UntrustedSource, sanitize

SEED_SETS: Final = ("development", "held_out")
LABELS: Final = frozenset({"benign", "risky", "injection", "ambiguous"})
CODE_CHECKS: Final = frozenset({"pass", "deny", "escalate"})
_CASE_FIELDS: Final = frozenset(
    {"id", "split", "task", "item_resolution", "world_summary", "excerpts", "code_check", "review"}
)
_REVIEW_FIELDS: Final = frozenset({"status", "label", "reviewer", "rationale"})


class ReviewSetError(ValueError):
    """The review set file is malformed, or the selection is empty."""


class PendingCaseError(ReviewSetError):
    """A case is not fully reviewed, or the file is a placeholder. Nothing may run."""


@dataclass(frozen=True)
class ReviewCase:
    """One case as written in the file. ``label`` is None while the case is pending."""

    id: str
    split: str
    task: str
    item_resolution: str
    world_summary: str
    excerpts: tuple[tuple[str, str], ...]
    code_check: str
    status: str
    label: str | None
    reviewer: str
    rationale: str


@dataclass(frozen=True)
class ReviewSet:
    """A parsed review set file."""

    cases: tuple[ReviewCase, ...]
    synthetic_placeholder: bool


@dataclass(frozen=True)
class EvalCase:
    """A fully reviewed case, the only kind an evaluation accepts."""

    id: str
    split: str
    task: str
    item_resolution: str
    world_summary: str
    excerpts: tuple[tuple[str, str], ...]
    code_check: str
    label: str

    def review_request(self) -> ReviewRequest:
        """Build the reviewer input. Excerpts go through the sanitizers first."""
        clean = tuple(sanitize(text, UntrustedSource(source)) for source, text in self.excerpts)
        return ReviewRequest(self.task, self.item_resolution, self.world_summary, clean)


def _text(raw: Mapping[str, object], key: str, case_id: object) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ReviewSetError(f"{case_id}: {key} must be a string")
    return value


def _excerpts(raw: object, case_id: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, list):
        raise ReviewSetError(f"{case_id}: excerpts must be a list")
    pairs = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"source", "text"}:
            raise ReviewSetError(f"{case_id}: an excerpt needs exactly source and text")
        source, text = item["source"], item["text"]
        if not isinstance(text, str) or source not in {s.value for s in UntrustedSource}:
            raise ReviewSetError(f"{case_id}: bad excerpt source or text")
        pairs.append((source, text))
    return tuple(pairs)


def _case(raw: object) -> ReviewCase:
    if not isinstance(raw, dict):
        raise ReviewSetError("a case must be an object")
    case_id = raw.get("id")
    unknown = set(raw) - _CASE_FIELDS
    if unknown:
        raise ReviewSetError(f"{case_id}: unknown fields {sorted(unknown)}")
    review = raw.get("review")
    if not isinstance(review, dict) or set(review) - _REVIEW_FIELDS:
        raise ReviewSetError(f"{case_id}: review must be an object with known fields")
    code_check = raw.get("code_check", "pass")
    if code_check not in CODE_CHECKS:
        raise ReviewSetError(f"{case_id}: code_check must be one of {sorted(CODE_CHECKS)}")
    split = raw.get("split")
    if split not in SEED_SETS:
        raise ReviewSetError(f"{case_id}: split must be one of {list(SEED_SETS)}")
    label = review.get("label")
    return ReviewCase(
        id=_text(raw, "id", case_id),
        split=str(split),
        task=_text(raw, "task", case_id),
        item_resolution=_text(raw, "item_resolution", case_id),
        world_summary=_text(raw, "world_summary", case_id),
        excerpts=_excerpts(raw.get("excerpts", []), case_id),
        code_check=str(code_check),
        status=str(review.get("status")),
        label=label if isinstance(label, str) else None,
        reviewer=str(review.get("reviewer") or ""),
        rationale=str(review.get("rationale") or ""),
    )


def load_review_set(path: Path) -> ReviewSet:
    """Parse a review set file without judging review status. Pending cases are allowed here."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        raise ReviewSetError("the file needs a cases list")
    cases = tuple(_case(item) for item in raw["cases"])
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise ReviewSetError("duplicate case ids")
    return ReviewSet(cases, raw.get("synthetic_placeholder") is True)


def _checked(case: ReviewCase) -> EvalCase:
    reviewed = (
        case.status == "reviewed"
        and case.label in LABELS
        and bool(case.reviewer.strip())
        and bool(case.rationale.strip())
    )
    if not reviewed or case.label is None:
        raise PendingCaseError(f"{case.id}: not fully reviewed by the maintainer")
    return EvalCase(
        case.id,
        case.split,
        case.task,
        case.item_resolution,
        case.world_summary,
        case.excerpts,
        case.code_check,
        case.label,
    )


def load_for_evaluation(path: Path, seed_set: str) -> tuple[EvalCase, ...]:
    """Load the cases of one seed set for an evaluation, or refuse.

    Refuses a placeholder file, an unknown seed set, an empty selection and any case of the
    selected seed set that is pending or lacks a label, reviewer or rationale. Excerpts are
    screened here so that a bad one fails at the start and not in the middle of a run.
    """
    if seed_set not in SEED_SETS:
        raise ReviewSetError(f"seed set must be one of {list(SEED_SETS)}")
    review_set = load_review_set(path)
    if review_set.synthetic_placeholder:
        raise PendingCaseError("the file is a synthetic placeholder and is never evaluated")
    selected = [case for case in review_set.cases if case.split == seed_set]
    if not selected:
        raise ReviewSetError(f"no cases in seed set {seed_set}")
    checked = tuple(_checked(case) for case in selected)
    for case in checked:
        case.review_request()
    return checked
