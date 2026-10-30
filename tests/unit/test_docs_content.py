"""Content checks for documents that carry rules the maintainer asked for."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_claude_md_links_to_gotchas() -> None:
    assert "](docs/GOTCHAS.md)" in _read("CLAUDE.md")


def test_plan_states_priority_order_not_equal_scope() -> None:
    plan = _read("PLAN.md")
    assert "Nothing is cut from scope" not in plan
    assert "Priority order" in plan
    assert "Phase 8 stays reserved from Nov 3 morning" in plan
    agents = _read("AGENTS.md")
    section = agents.split("## 18. Priorities when time runs short", 1)[1]
    items = re.findall(r"^\d\. (.+)$", section.split("## 19.", 1)[0], flags=re.MULTILINE)
    assert len(items) == 7
    for item in items:
        assert item.split(",")[0] in plan, item


def test_submission_notes_video_text_fallback() -> None:
    assert "text commands" in _read("SUBMISSION.md")


def test_readme_has_disclosure_section() -> None:
    readme = _read("README.md")
    assert "## Disclosure" in readme
    section = readme.split("## Disclosure", 1)[1].split("\n## ", 1)[0]
    for needle in ("Claude Code", "PRIOR_WORK.md", "ASSETS.md", "Muse Spark"):
        assert needle in section, needle


def test_agents_context_file_rules() -> None:
    agents = _read("AGENTS.md")
    assert "Always read `LASTCONTEXT.md` and `PENDING.md`" in agents
    assert "ready-to-paste prompt for the next session" in agents
    assert "list of pending tasks" in agents
    assert "change session" in agents


def test_lastcontext_has_done_state_and_prompt() -> None:
    text = _read("LASTCONTEXT.md")
    for heading in ("## Done last", "## Current state", "## Prompt for the next session"):
        assert heading in text, heading


def test_pending_is_a_prioritized_task_list() -> None:
    text = _read("PENDING.md")
    assert "| # | Priority | Task | Owner | Status |" in text
    assert re.search(r"^\| 1 \| P[1-4] \|", text, flags=re.MULTILINE)


def test_compose_images_are_tagged_dev_never_latest() -> None:
    compose = _read("docker-compose.yml")
    assert "waggle-hive:${WAGGLE_IMAGE_TAG:-dev}" in compose
    assert ":latest" not in compose
