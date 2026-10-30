"""Shared path and command matching for the Claude Code hooks (standard library only)."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTECTED_FILE = Path(__file__).with_name("protected_paths.txt")
_HELDOUT = re.compile(r"(^|/)results/[^/]+/heldout(/|$)", re.IGNORECASE)
_ABSOLUTE = re.compile(r"^([A-Za-z]:/|/)")


@dataclass
class Segment:
    """One simple command: its words and the targets of its output redirects."""

    words: list[str] = field(default_factory=list)
    redirects: list[str] = field(default_factory=list)


def tokenize(command: str) -> list[Segment]:
    """Split a shell or PowerShell command line into simple commands.

    Quotes group text, backslashes are kept (Windows paths), and the operators
    ``; & | ( )`` and newlines end a command. Redirect targets are collected apart.
    """
    segments: list[Segment] = []
    current = Segment()
    word: list[str] = []
    started = False
    quote = ""
    redirect_next = False

    def flush_word() -> None:
        nonlocal word, started, redirect_next
        if started:
            text = "".join(word)
            (current.redirects if redirect_next else current.words).append(text)
            redirect_next = False
        word, started = [], False

    def end_segment() -> None:
        nonlocal current, redirect_next
        flush_word()
        if current.words or current.redirects:
            segments.append(current)
        current = Segment()
        redirect_next = False

    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"' and command[i + 1 : i + 2] == '"':
                word.append('"')
                i += 1
            else:
                word.append(ch)
        elif ch in "'\"":
            quote, started = ch, True
        elif ch == "`" and i + 1 < len(command):
            word.append(command[i + 1])
            started = True
            i += 1
        elif ch in ";&|()\n":
            end_segment()
        elif ch == ">":
            if started and "".join(word).isdigit():
                word, started = [], False  # a file descriptor prefix such as the 2 in 2>&1
            flush_word()
            if command[i + 1 : i + 2] == ">":
                i += 1
            if re.match(r"&\d", command[i + 1 : i + 3]):
                i += 2  # fd duplication (2>&1) writes to no file
            else:
                redirect_next = True
        elif ch.isspace():
            flush_word()
        else:
            word.append(ch)
            started = True
        i += 1
    end_segment()
    return segments


def normalize_path(raw: str, root: Path | None = None) -> str:
    """Forward slashes, no quotes, no leading ./, relative to ``root`` when inside it."""
    text = raw.strip().strip("'\"").replace("\\", "/")
    if root is not None and _ABSOLUTE.match(text):
        prefix = root.as_posix().rstrip("/")
        if text.lower().startswith(prefix.lower() + "/"):
            text = text[len(prefix) + 1 :]
    while text.startswith("./"):
        text = text[2:]
    return text


def basename(path: str) -> str:
    """Last component of a normalized path."""
    return path.rsplit("/", 1)[-1]


def is_env_file(path: str) -> bool:
    """True for ``.env`` and ``.env.*`` files, except ``.env.example``."""
    name = basename(path)
    if name == ".env.example":
        return False
    return name == ".env" or name.startswith(".env.")


def is_heldout_path(path: str) -> bool:
    """True for a path under ``results/<experiment>/heldout/``."""
    return _HELDOUT.search(path) is not None


def is_pending_file(path: str) -> bool:
    """True for PENDING.md in any directory."""
    return basename(path).lower() == "pending.md"


def load_protected(path: Path = PROTECTED_FILE) -> list[str]:
    """Read the protected path entries. Comments and blank lines are skipped."""
    entries: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#"):
            entries.append(entry)
    return entries


def is_protected(path: str, entries: list[str]) -> bool:
    """True when a normalized path is a protected file or inside a protected directory."""
    lowered = path.lower()
    for entry in entries:
        e = entry.lower()
        if e.endswith("/"):
            if lowered.startswith(e):
                return True
        elif lowered == e:
            return True
    return False


def decision_output(kind: str, reason: str) -> dict[str, Any]:
    """The documented PreToolUse decision JSON for ``allow``, ``ask`` or ``deny``."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": reason,
        }
    }
