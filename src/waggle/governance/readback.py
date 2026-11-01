"""Item resolution and read-back before a voice-driven pick (ADR-057).

The transcript is untrusted. The item to pick comes from the trusted order, the read-back always
names that item, and execution needs a ``Confirmation`` that the operator channel produced for
that prompt and item. Words in the transcript never count as a confirmation. A transcript that
names any item other than the ordered one, or more than one, blocks execution. Everything here
is pure and fails closed.
"""

import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final, Literal

_UNITS: Final[dict[str, int]] = {
    w: i
    for i, w in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
        ]
    )
}
_TENS: Final[dict[str, int]] = {
    w: 10 * i
    for i, w in enumerate(
        ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    )
    if w != "_"
}
_TOKEN = re.compile(r"[a-z]+|\d+")
_PREFIX: Final = "ITEM-"

DecisionReason = Literal[
    "confirmed", "no_confirmation", "confirmation_mismatch", "transcript_mismatch"
]


@dataclass(frozen=True)
class ReadBackPrompt:
    """The read-back issued to the operator. Its text is built from the trusted item only."""

    prompt_id: str
    item_id: str
    text: str


@dataclass(frozen=True)
class Confirmation:
    """Produced only by the authenticated operator channel, never parsed from transcript text."""

    prompt_id: str
    item_id: str


@dataclass(frozen=True)
class Decision:
    """Whether the pick may run, and why."""

    execute: bool
    reason: DecisionReason
    item_id: str | None = None


def _numbers(text: str) -> list[int]:
    tokens = _TOKEN.findall(text.lower())
    found: list[int] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token in _TENS and nxt in _UNITS and 1 <= _UNITS[nxt] <= 9:
            found.append(_TENS[token] + _UNITS[nxt])
            i += 2
            continue
        if token.isdigit():
            found.append(int(token))
        elif token in _UNITS:
            found.append(_UNITS[token])
        elif token in _TENS:
            found.append(_TENS[token])
        i += 1
    return found


def resolve_items(transcript: str, known: Collection[str]) -> frozenset[str]:
    """The known item ids that the transcript names, by digits, ``ITEM-n`` or number words."""
    candidates = {f"{_PREFIX}{n}" for n in _numbers(transcript)}
    return frozenset(candidates & set(known))


def start_readback(prompt_id: str, item_id: str, known: Collection[str]) -> ReadBackPrompt:
    """Issue the read-back for the trusted item. An unknown item is refused."""
    if item_id not in known:
        raise ValueError("unknown item")
    return ReadBackPrompt(prompt_id, item_id, f"Confirm pick of {item_id}")


def authorize(
    prompt: ReadBackPrompt,
    transcript: str,
    confirmation: Confirmation | None,
    known: Collection[str],
) -> Decision:
    """Allow the pick only for a matching confirmation and a transcript that agrees."""
    if confirmation is None:
        return Decision(False, "no_confirmation")
    if confirmation.prompt_id != prompt.prompt_id or confirmation.item_id != prompt.item_id:
        return Decision(False, "confirmation_mismatch")
    named = resolve_items(transcript, known)
    if named and named != {prompt.item_id}:
        return Decision(False, "transcript_mismatch")
    return Decision(True, "confirmed", prompt.item_id)
