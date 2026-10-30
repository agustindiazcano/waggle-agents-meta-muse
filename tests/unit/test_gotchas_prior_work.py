import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOTCHAS = (ROOT / "docs" / "GOTCHAS.md").read_text(encoding="utf-8")
PRIOR_WORK = (ROOT / "PRIOR_WORK.md").read_text(encoding="utf-8")

REQUIRED_TOPICS = [
    "SSE",
    "421",
    "tools/list",
    "intent row",
    "clock_timestamp()",
    "<=>",
    "chunk",
    "docker pause",
    "light checks",
    "count cases, not repeats",
    "same provider",
]


def _entries() -> dict[str, str]:
    body = GOTCHAS.split("## Template", 1)[1]
    body = body.split("### Short title", 1)[1].split("\n", 1)[1]  # skip the template entry
    parts = re.split(r"^### ", body, flags=re.MULTILINE)
    entries: dict[str, str] = {}
    for part in parts[1:]:
        title, _, text = part.partition("\n")
        entries[title.strip()] = text
    return entries


def test_every_entry_has_symptom_and_action() -> None:
    entries = _entries()
    assert len(entries) >= 12
    for title, text in entries.items():
        assert "- Symptom:" in text, title
        assert "- What to do:" in text, title


def test_required_topics_are_covered() -> None:
    for topic in REQUIRED_TOPICS:
        assert topic in GOTCHAS, topic


def test_prior_work_links_earlier_repository() -> None:
    assert "https://github.com/agustindiazcano/mcp-transactional-agent" in PRIOR_WORK


def test_prior_work_states_ideas_only() -> None:
    lowered = PRIOR_WORK.lower()
    assert "only ideas and method are reused" in lowered
    assert "no code" in lowered
    assert "no text" in lowered


def test_stacked_pr_merge_order_trap_is_recorded() -> None:
    text = (ROOT / "docs" / "GOTCHAS.md").read_text(encoding="utf-8")
    assert "### Merging a stacked pull request chain in the wrong order loses work" in text
    assert "retarget" in text
