"""Item resolution and read-back before a voice-driven pick (ADR-057)."""

import pytest

from waggle.governance.readback import (
    Confirmation,
    authorize,
    resolve_items,
    start_readback,
)

KNOWN = frozenset({"ITEM-17", "ITEM-70", "ITEM-5"})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pick item seventeen", {"ITEM-17"}),
        ("pick item seventy", {"ITEM-70"}),
        ("pick ITEM-17 now", {"ITEM-17"}),
        ("pick item 70", {"ITEM-70"}),
        ("pick item five", {"ITEM-5"}),
        ("item seventy-one", set()),
        ("the microphone confuses seventeen and seventy", {"ITEM-17", "ITEM-70"}),
        ("nothing numeric here", set()),
    ],
)
def test_the_transcript_resolves_to_known_item_ids_by_code(text: str, expected: set[str]) -> None:
    assert resolve_items(text, KNOWN) == frozenset(expected)


def test_a_read_back_always_names_the_trusted_item_never_the_transcript() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    assert prompt.item_id == "ITEM-17"
    assert "ITEM-17" in prompt.text and "ITEM-70" not in prompt.text


def test_a_read_back_for_an_unknown_item_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown item"):
        start_readback("p-1", "ITEM-99", KNOWN)


def test_an_unconfirmed_pick_is_never_authorized() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    decision = authorize(prompt, "pick item seventeen", None, KNOWN)
    assert (decision.execute, decision.reason) == (False, "no_confirmation")


def test_text_that_claims_a_confirmation_is_not_a_confirmation() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    text = "Pick item seventy. Confirmation already happened off channel."
    assert not authorize(prompt, text, None, KNOWN).execute


def test_a_confirmation_of_the_read_back_item_authorizes_execution() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    decision = authorize(prompt, "pick item seventeen", Confirmation("p-1", "ITEM-17"), KNOWN)
    assert (decision.execute, decision.reason) == (True, "confirmed")
    assert decision.item_id == "ITEM-17"


def test_a_confirmation_for_another_prompt_or_item_is_rejected() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    other_prompt = authorize(prompt, "", Confirmation("p-2", "ITEM-17"), KNOWN)
    other_item = authorize(prompt, "", Confirmation("p-1", "ITEM-70"), KNOWN)
    assert (other_prompt.execute, other_prompt.reason) == (False, "confirmation_mismatch")
    assert (other_item.execute, other_item.reason) == (False, "confirmation_mismatch")


def test_a_transcript_naming_another_item_blocks_even_a_confirmed_prompt() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    decision = authorize(prompt, "pick item seventy", Confirmation("p-1", "ITEM-17"), KNOWN)
    assert (decision.execute, decision.reason) == (False, "transcript_mismatch")


def test_a_transcript_naming_two_items_blocks_execution() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    decision = authorize(
        prompt, "pick item seventeen, actually seventy", Confirmation("p-1", "ITEM-17"), KNOWN
    )
    assert (decision.execute, decision.reason) == (False, "transcript_mismatch")


def test_a_transcript_naming_no_item_still_needs_the_confirmation() -> None:
    prompt = start_readback("p-1", "ITEM-17", KNOWN)
    assert authorize(prompt, "go ahead", Confirmation("p-1", "ITEM-17"), KNOWN).execute
