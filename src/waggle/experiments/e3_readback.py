"""E3 runner for the read-back and item resolution layer (ADR-057).

Each case performs the action its text tries to cause, or for a benign case the ordinary one.
An injection tries to execute a pick from the untrusted transcript with no confirmation from the
operator channel (the case setups say none was given), so it is blocked when the layer does not
authorize execution. The benign case asks for a read-back of the trusted item, so it is served
when a prompt naming that item is issued.

``ATTEMPTS`` is a fixture written from the case text. It is not a label and needs maintainer
review like the fixtures of the other runners. The trusted order is ITEM-17 and ITEM-70 also
exists, as the case setups state.
"""

from collections.abc import Callable, Collection
from typing import Literal

from waggle.experiments.e3_eval import Case
from waggle.experiments.e3_mcp_layers import LayerOutcome, LayerReport
from waggle.governance.readback import (
    Confirmation,
    Decision,
    ReadBackPrompt,
    authorize,
    start_readback,
)

READBACK_LAYER = "read_back_item_resolution"
KNOWN = frozenset({"ITEM-17", "ITEM-70"})
_TRUSTED = "ITEM-17"
_PROMPT_ID = "e3-readback"

Authorizer = Callable[[ReadBackPrompt, str, Confirmation | None, Collection[str]], Decision]
Starter = Callable[[str, str, Collection[str]], ReadBackPrompt]

ATTEMPTS: dict[str, Literal["execute", "read_back"]] = {
    "E3-T4-01": "execute",
    "E3-T4-02": "execute",
    "E3-T4-03": "read_back",
}


def _run(case: Case, action: str, authorizer: Authorizer, starter: Starter) -> LayerOutcome:
    if case.label not in ("injection", "benign"):
        raise ValueError(f"{case.id}: only injection and benign cases can be run")
    try:
        prompt = starter(_PROMPT_ID, _TRUSTED, KNOWN)
    except ValueError:
        return LayerOutcome(case.id, case.target_layer, case.label, False, "unknown_item")
    if action == "read_back":
        return LayerOutcome(
            case.id, case.target_layer, case.label, prompt.item_id == _TRUSTED, None
        )
    decision = authorizer(prompt, case.input, None, KNOWN)
    return LayerOutcome(case.id, case.target_layer, case.label, decision.execute, decision.reason)


def run_readback(
    cases: tuple[Case, ...],
    authorizer: Authorizer = authorize,
    starter: Starter = start_readback,
) -> LayerReport:
    """Run every reviewed read-back case through the production functions in id order."""
    chosen = sorted((c for c in cases if c.target_layer == READBACK_LAYER), key=lambda c: c.id)
    missing = [c.id for c in chosen if c.id not in ATTEMPTS]
    if missing:
        raise KeyError("no attempt fixture for: " + ", ".join(missing))
    return LayerReport(tuple(_run(c, ATTEMPTS[c.id], authorizer, starter) for c in chosen))
