"""Project name and documentation consistency checks over tracked files."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()

# Built from fragments so this file does not contain the names it forbids elsewhere.
TENTATIVE_NAMES = ["Aegis" + "Fleet", "waggle-agents-" + "fleet"]
READ_ORDER = [
    "AGENTS.md",
    "PLAN.md",
    "docs/ARCHITECTURE.md",
    "docs/DECISIONS.md",
    "docs/THREAT_MODEL.md",
    "docs/EXPERIMENTS.md",
    "docs/GOTCHAS.md",
    "LASTCONTEXT.md",
    "PENDING.md",
]
NAMED_DOCS = [
    "README.md",
    "PLAN.md",
    "AGENTS.md",
    "PRIOR_WORK.md",
    "ASSETS.md",
    "SUBMISSION.md",
    "LASTCONTEXT.md",
    "PENDING.md",
    "docs/ARCHITECTURE.md",
    "docs/DECISIONS.md",
    "docs/THREAT_MODEL.md",
    "docs/EXPERIMENTS.md",
]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _tracked() -> list[Path]:
    git = shutil.which("git")
    assert git is not None
    out = subprocess.run(
        [git, "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout.decode("utf-8")
    return [ROOT / name for name in out.split("\0") if name]


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return None


def test_no_tentative_project_names_in_tracked_files() -> None:
    offenders: list[str] = []
    for path in _tracked():
        if path.name == "uv.lock" or path.resolve() == THIS_FILE:
            continue
        text = _text(path)
        if text is None:
            continue
        offenders += [
            f"{path.relative_to(ROOT)}: {name}" for name in TENTATIVE_NAMES if name in text
        ]
    assert not offenders, offenders


def test_claude_md_imports_agents_and_points_to_context_files() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in text.splitlines()[0]
    for name in ("PLAN.md", "LASTCONTEXT.md", "PENDING.md"):
        assert name in text


def test_claude_md_read_order() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    positions = [text.find(f"`{name}`") for name in READ_ORDER]
    assert all(p >= 0 for p in positions), dict(zip(READ_ORDER, positions, strict=True))
    assert positions == sorted(positions), "CLAUDE.md read order is not the documented one"


def test_claude_md_describes_project() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Waggle Hive" in text
    assert "Safety and reliability control plane for LLM-directed warehouse robot fleets" in text


def test_markdown_links_resolve() -> None:
    broken: list[str] = []
    for path in _tracked():
        if path.suffix != ".md":
            continue
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            file_part = target.split("#", 1)[0]
            if file_part and not (path.parent / file_part).exists():
                broken.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not broken, broken


def test_readme_title_has_project_name() -> None:
    first = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("# ")
    assert "Waggle Hive" in first


@pytest.mark.parametrize("name", NAMED_DOCS)
def test_docs_carry_project_name(name: str) -> None:
    assert "Waggle Hive" in (ROOT / name).read_text(encoding="utf-8").splitlines()[0]


def test_config_files_carry_project_name() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^description = ".*Waggle Hive', pyproject, re.MULTILINE)
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.startswith("name: Waggle Hive")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"^name: waggle-hive$", compose, re.MULTILINE)
