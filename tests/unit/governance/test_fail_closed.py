"""An outage of any provider degrades to escalation, never to approval (ADR-017)."""

import pytest
from llm_support import build

from waggle.governance.court import Decision, Verdict, decide
from waggle.governance.guard import GuardLabel, GuardOutcome, screen
from waggle.llm.client import LlmClient
from waggle.llm.errors import LlmError
from waggle.llm.models import LlmRequest

COURT_ROLES = ["court_1", "court_2", "court_3"]


def vote(client: LlmClient, role: str) -> Verdict | None:
    """Mock members always approve when they answer; a failed call is no vote."""
    try:
        client.call(LlmRequest(request_id=f"v-{role}", role=role, prompt="task"))
    except LlmError:
        return None
    return Verdict.APPROVE


def guard_label(client: LlmClient) -> GuardLabel | None:
    try:
        client.call(LlmRequest(request_id="g", role="guard", prompt="label text"))
    except LlmError:
        return None
    return GuardLabel.BENIGN


def test_healthy_court_executes() -> None:
    client, _, _ = build()
    votes = [vote(client, r) for r in COURT_ROLES]
    assert decide(votes) is Decision.EXECUTE


@pytest.mark.parametrize("provider", ["meta", "baseten", "modal"])
def test_provider_outage_escalates_the_court(provider: str) -> None:
    client, _, _ = build(failing=(provider,), fallbacks=False)
    votes = [vote(client, r) for r in COURT_ROLES]
    assert None in votes
    assert decide(votes) is Decision.ESCALATE


def test_vertex_outage_escalates_when_it_is_the_fallback_in_use() -> None:
    client, _, _ = build(failing=("modal", "vertex"), fallbacks=True)
    votes = [vote(client, r) for r in COURT_ROLES]
    assert decide(votes) is Decision.ESCALATE


@pytest.mark.parametrize("provider", ["meta", "baseten", "modal"])
def test_outage_of_any_provider_never_turns_into_approval(provider: str) -> None:
    client, _, _ = build(failing=(provider,), fallbacks=False)
    votes = [vote(client, r) for r in COURT_ROLES]
    assert decide(votes) is not Decision.EXECUTE


def test_guard_outage_rejects_and_escalates() -> None:
    client, _, _ = build(failing=("modal",), fallbacks=False)
    assert screen(guard_label(client)) is GuardOutcome.REJECT_AND_ESCALATE


def test_guard_with_vertex_fallback_down_rejects_and_escalates() -> None:
    client, _, _ = build(failing=("modal", "vertex"), fallbacks=True)
    assert screen(guard_label(client)) is GuardOutcome.REJECT_AND_ESCALATE


def test_guard_passes_only_benign() -> None:
    assert screen(GuardLabel.BENIGN) is GuardOutcome.PASS
    assert screen(GuardLabel.INJECTION) is GuardOutcome.REJECT_AND_ESCALATE
    assert screen(GuardLabel.UNCERTAIN) is GuardOutcome.REJECT_AND_ESCALATE
    assert screen(None) is GuardOutcome.REJECT_AND_ESCALATE


@pytest.mark.parametrize(
    "votes",
    [
        [],
        [None],
        [Verdict.REJECT],
        [Verdict.APPROVE, Verdict.REJECT, Verdict.APPROVE],
        [Verdict.APPROVE, None, Verdict.APPROVE],
        [Verdict.REJECT, Verdict.REJECT, Verdict.REJECT],
    ],
)
def test_court_never_approves_over_a_rejection_or_a_failure(
    votes: list[Verdict | None],
) -> None:
    assert decide(votes) is Decision.ESCALATE


def test_court_executes_only_on_unanimous_approval() -> None:
    assert decide([Verdict.APPROVE] * 3) is Decision.EXECUTE
