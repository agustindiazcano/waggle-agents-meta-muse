"""Style rules from AGENTS.md section 13, enforced over tracked text files.

The scanning lives in ``find_violations`` so the detector itself is tested with bad
and clean samples. Banned words are built from fragments so this file does not
contain them as plain text.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()

EM_DASH = chr(0x2014)
BOM = "﻿"
EMOJI = re.compile(
    "[☀-➿⭐⭕⌚⌛⏩-⏳⏸-⏺"
    "\U0001f000-\U0001faff]"
)
BANNED_WORDS = [
    "ro" + "bust",
    "rigo" + "rous",
    "compre" + "hensive",
    "seam" + "less",
    "pow" + "erful",
    "cutting" + "-edge",
    "state-of-the" + "-art",
    "cru" + "cial",
    "piv" + "otal",
    "del" + "ve",
    "lever" + "age",
    "ho" + "listic",
]
BANNED_STEM = "ho" + "nes"
WORD_RE = re.compile(
    r"(?<![\w-])(?:" + "|".join(re.escape(w) for w in BANNED_WORDS) + r")(?![\w-])"
    r"|(?<![\w-])" + BANNED_STEM + r"\w*",
    re.IGNORECASE,
)


def find_violations(text: str) -> list[str]:
    """Return a list of style violations found in ``text``."""
    found: list[str] = []
    if text.startswith(BOM):
        found.append("UTF-8 BOM at start of file")
    if EM_DASH in text:
        found.append("em dash")
    emoji = EMOJI.findall(text)
    if emoji:
        found.append(f"emoji: {''.join(sorted(set(emoji)))}")
    words = sorted({m.group(0).lower() for m in WORD_RE.finditer(text)})
    if words:
        found.append(f"banned wording: {', '.join(words)}")
    return found


def _tracked_text_files() -> list[Path]:
    git = shutil.which("git")
    assert git is not None
    out = subprocess.run(
        [git, "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=30
    ).stdout.decode("utf-8")
    files: list[Path] = []
    for name in out.split("\0"):
        path = ROOT / name
        if not name or name == "uv.lock" or path.resolve() == THIS_FILE or not path.is_file():
            continue
        files.append(path)
    return files


@pytest.mark.parametrize(
    ("sample", "kind"),
    [
        (f"a {EM_DASH} b", "em dash"),
        ("done \U0001f680", "emoji"),
        ("ok ✅", "emoji"),
        *[(f"this is {word} text", "banned word") for word in BANNED_WORDS],
        (f"{BANNED_STEM}t answer", "banned stem"),
        (f"{BANNED_STEM}tly", "banned stem"),
        (f"{BOM}# title", "BOM"),
    ],
)
def test_detector_flags_bad_samples(sample: str, kind: str) -> None:
    violations = find_violations(sample)
    assert violations, f"{kind} sample was not flagged: {sample!r}"


@pytest.mark.parametrize(
    "sample",
    [
        "Plain technical wording about leases and fencing tokens.",
        "Use a hyphen - or two -- in code.",
        "Arrows like -> and => are fine.",
        "The word rob is fine, and so is hone.",
    ],
)
def test_detector_accepts_clean_samples(sample: str) -> None:
    assert find_violations(sample) == []


def test_tracked_text_files_follow_style_rules() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found = find_violations(text)
        if found:
            offenders[str(path.relative_to(ROOT))] = found
    assert not offenders, offenders
