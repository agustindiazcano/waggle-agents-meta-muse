"""Guard outcome rule (ADR-008, ADR-017): untrusted input fails closed."""

from enum import StrEnum


class GuardLabel(StrEnum):
    """Label returned by the guard classifier."""

    BENIGN = "benign"
    INJECTION = "injection"
    UNCERTAIN = "uncertain"


class GuardOutcome(StrEnum):
    """What happens to an input after screening."""

    PASS = "pass"
    REJECT_AND_ESCALATE = "reject_and_escalate"


def screen(label: GuardLabel | None) -> GuardOutcome:
    """Pass only a clear benign label.

    ``None`` stands for a parse failure, a timeout or an outage. Injection,
    uncertain and failure all reject and escalate.
    """
    if label is GuardLabel.BENIGN:
        return GuardOutcome.PASS
    return GuardOutcome.REJECT_AND_ESCALATE
