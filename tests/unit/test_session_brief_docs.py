"""The Phase 1 session brief is stored in the repository and wired into the context files."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIEF = "docs/PHASE1_BRIEF.md"


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_brief_exists_with_its_parts_and_branch_order() -> None:
    text = _read(BRIEF)
    for part in range(0, 7):
        assert f"PART {part}" in text, f"PART {part} missing"
    for branch in (
        "chore/push-guard-hardening",
        "docs/phase1-conventions",
        "docs/crisis-replanning-design",
        "feat/sim-core",
        "feat/sim-scenarios",
    ):
        assert branch in text, branch
    for adr in ("ADR-023", "ADR-024", "ADR-025"):
        assert adr in text, adr


def test_pending_tracks_the_brief_and_open_decisions() -> None:
    text = _read("PENDING.md")
    assert BRIEF in text
    assert re.search(r"FastAPI.*viewer", text, re.I)
    assert re.search(r"gates?", text, re.I)


def test_claude_md_read_order_mentions_the_brief() -> None:
    assert BRIEF in _read("CLAUDE.md")


def test_agents_section_18_uses_contingency_order_and_gates() -> None:
    text = _read("AGENTS.md")
    section = text.split("## 18.")[1].split("## 19.")[0]
    for term in ("Contingency order", "G1", "G2", "G3", "G4", "I decide", "Reserved and never cut"):
        assert term in section or term.replace("I decide", "maintainer decides") in section, term
    assert "Predictive maintenance" in section and "crisis replanning" in section.lower()


def test_adr_022_records_the_push_guard_conditions() -> None:
    text = _read("docs/DECISIONS.md")
    adr = text.split("## ADR-022:")[1].split("\n## ADR-")[0]
    for term in (
        "type/short-description",
        "pre_push_check.py",
        "gitleaks",
        "uv run ci",
        "results/**/heldout/",
        "gh pr merge",
    ):
        assert term in adr, term


def test_agents_section_3_is_cloud_first() -> None:
    text = _read("AGENTS.md")
    section = text.split("## 3.")[1].split("## 4.")[0]
    for term in (
        "Cloud first",
        "push the branch",
        "GitHub",
        "very fast",
        "dev seeds",
        "pre-push check",
    ):
        assert term in section, term
