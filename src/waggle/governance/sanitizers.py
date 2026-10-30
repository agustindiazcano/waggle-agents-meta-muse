"""Deterministic sanitizers for untrusted text, run before the guard classifier (ADR-032).

Pure functions. Over-long, non-text or empty input is rejected, never truncated or repaired
silently. Removed characters are reported as flags so a caller can log them.
"""

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

_DROPPED_CONTROL: Final = "Cc"
_DROPPED_INVISIBLE: Final = frozenset({"Cf", "Cs", "Co", "Cn"})


class UntrustedSource(StrEnum):
    """Where an untrusted text came from. Each source has its own length cap."""

    VOICE_TRANSCRIPT = "voice_transcript"
    PACKAGE_LABEL = "package_label"
    SOP_TEXT = "sop_text"
    MANUAL_TEXT = "manual_text"
    ROBOT_MESSAGE = "robot_message"


# Caps in characters are assumptions to calibrate on real inputs.
MAX_CHARS: Final[dict[UntrustedSource, int]] = {
    UntrustedSource.VOICE_TRANSCRIPT: 1000,
    UntrustedSource.PACKAGE_LABEL: 200,
    UntrustedSource.SOP_TEXT: 4000,
    UntrustedSource.MANUAL_TEXT: 4000,
    UntrustedSource.ROBOT_MESSAGE: 500,
}

SanitizeCode = Literal["bad_type", "empty", "too_long"]


class SanitizeError(ValueError):
    """The input cannot be screened. The caller rejects and escalates."""

    def __init__(self, code: SanitizeCode) -> None:
        super().__init__(code)
        self.code: SanitizeCode = code


@dataclass(frozen=True)
class Sanitized:
    """Cleaned text, its source and the sorted flags of what was changed."""

    text: str
    source: UntrustedSource
    flags: tuple[str, ...]


def _clean(text: str) -> tuple[str, set[str]]:
    flags: set[str] = set()
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = unicodedata.normalize("NFKC", unified)
    if normalized != unified:
        flags.add("normalized")
    kept: list[str] = []
    for char in normalized:
        if char == "\n":
            kept.append(char)
        elif char == "\t":
            kept.append(" ")
        else:
            category = unicodedata.category(char)
            if category == _DROPPED_CONTROL:
                flags.add("controls_removed")
            elif category in _DROPPED_INVISIBLE:
                flags.add("invisible_removed")
            else:
                kept.append(char)
    return "".join(kept), flags


def sanitize(text: str, source: UntrustedSource) -> Sanitized:
    """Normalize and clean ``text`` or raise SanitizeError.

    The cap is checked before cleaning to bound the work and again after, because
    normalization can expand text.
    """
    if not isinstance(text, str):
        raise SanitizeError("bad_type")
    cap = MAX_CHARS[source]
    if len(text) > cap:
        raise SanitizeError("too_long")
    cleaned, flags = _clean(text)
    if len(cleaned) > cap:
        raise SanitizeError("too_long")
    if not cleaned.strip():
        raise SanitizeError("empty")
    return Sanitized(cleaned, source, tuple(sorted(flags)))


def fence(clean: Sanitized) -> str:
    """Wrap clean text as data. `&`, `<` and `>` are escaped, so the text cannot close the
    fence or open another one."""
    body = clean.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<untrusted source="{clean.source.value}">\n{body}\n</untrusted>'
