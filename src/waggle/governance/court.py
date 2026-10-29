"""Court decision rule (ADR-005): execute only on unanimous approval."""

from collections.abc import Sequence
from enum import StrEnum


class Verdict(StrEnum):
    """A court member's valid answer."""

    APPROVE = "approve"
    REJECT = "reject"


class Decision(StrEnum):
    """Outcome of a court round."""

    EXECUTE = "execute"
    ESCALATE = "escalate"


def decide(votes: Sequence[Verdict | None]) -> Decision:
    """Return EXECUTE only if every vote is a valid approval.

    ``None`` stands for a timeout, a parse failure or a provider outage. Any reject,
    split, failure or empty round escalates to the operator. There is no path that
    approves over a rejection.
    """
    if votes and all(v is Verdict.APPROVE for v in votes):
        return Decision.EXECUTE
    return Decision.ESCALATE
