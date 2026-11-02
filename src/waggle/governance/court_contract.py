"""Court contract: the reviewer input, the vote schema and the strict vote parser.

A reviewer answers with a verdict and codes from a closed vocabulary, never free text, because
free text is an output channel that injected text can steer. Anything outside the schema is a
parse failure, which the decision rule treats as no vote (fail closed).
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from waggle.governance.court import Verdict
from waggle.governance.sanitizers import Sanitized

MAX_VOTE_CHARS: Final = 512
MAX_REASON_CODES: Final = 3
NO_ISSUE: Final = "no_issue"
REASON_CODES: Final = frozenset(
    {
        NO_ISSUE,
        "sop_violation",
        "injection_suspected",
        "operational_conflict",
        "item_ambiguous",
        "insufficient_information",
        "other_risk",
    }
)


@dataclass(frozen=True)
class ReviewRequest:
    """Input of one court round, built by code and identical for every reviewer.

    ``task``, ``item_resolution`` and ``world_summary`` are trusted structured data rendered by
    code. ``excerpts`` are screened SOP texts, still untrusted: they are fenced as data.
    """

    task: str
    item_resolution: str
    world_summary: str
    excerpts: tuple[Sanitized, ...]

    def digest(self) -> str:
        """SHA-256 of the canonical form. Equal requests give equal digests."""
        canonical = json.dumps(
            {
                "task": self.task,
                "item_resolution": self.item_resolution,
                "world_summary": self.world_summary,
                "excerpts": [[e.source.value, e.text] for e in self.excerpts],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Vote:
    """A valid reviewer answer."""

    verdict: Verdict
    reason_codes: tuple[str, ...]


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("duplicate vote field")
        fields[key] = value
    return fields


def _codes(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_REASON_CODES:
        raise ValueError("invalid reason code list")
    if not all(isinstance(c, str) and c in REASON_CODES for c in value):
        raise ValueError("reason code outside the vocabulary")
    if len(set(value)) != len(value):
        raise ValueError("duplicate reason code")
    return tuple(value)


def parse_vote(raw: str) -> Vote:
    """Validate a raw reviewer answer strictly, or raise ValueError."""
    if not isinstance(raw, str) or len(raw) > MAX_VOTE_CHARS:
        raise ValueError("invalid vote text")
    try:
        payload: object = json.loads(raw, object_pairs_hook=_unique_fields)
    except RecursionError:
        raise ValueError("vote nesting too deep") from None
    if not isinstance(payload, dict) or set(payload) != {"verdict", "reason_codes"}:
        raise ValueError("invalid vote fields")
    verdict, codes = payload["verdict"], _codes(payload["reason_codes"])
    if verdict == "approve":
        if codes != (NO_ISSUE,):
            raise ValueError("approve needs exactly no_issue")
        return Vote(Verdict.APPROVE, codes)
    if verdict == "reject":
        if NO_ISSUE in codes:
            raise ValueError("reject cannot carry no_issue")
        return Vote(Verdict.REJECT, codes)
    raise ValueError("verdict must be approve or reject")


def vote_or_none(raw: str) -> Vote | None:
    """Parse a reviewer answer, returning None for any invalid one."""
    try:
        return parse_vote(raw)
    except ValueError:
        return None
