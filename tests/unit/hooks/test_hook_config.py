"""Project hook configuration, CODEOWNERS coverage and the protected_paths CI job."""

import json
import re
from pathlib import Path

import guard_common as gc
import pytest

ROOT = Path(__file__).resolve().parents[3]
_TEXT = (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
SETTINGS = json.loads(_TEXT) if _TEXT.strip() else {}
needs_hooks = pytest.mark.skipif(
    "hooks" not in SETTINGS, reason="the maintainer runs without project hooks in settings.json"
)


def _commands(event: str) -> list[str]:
    return [h["command"] for group in SETTINGS["hooks"][event] for h in group["hooks"]]


def _matchers(event: str) -> list[str]:
    return [group.get("matcher", "") for group in SETTINGS["hooks"][event]]


@needs_hooks
def test_hooks_run_as_uv_run_python_scripts() -> None:
    assert _commands("PreToolUse") == ["uv run python tools/hooks/safety_guard.py"]
    assert _commands("PostToolUse") == ["uv run python tools/hooks/lint_check.py"]
    assert _commands("SessionStart") == ["uv run python tools/hooks/session_start.py"]


@needs_hooks
def test_every_configured_script_exists() -> None:
    for event in ("PreToolUse", "PostToolUse", "SessionStart"):
        for command in _commands(event):
            script = command.rsplit(" ", 1)[-1]
            assert (ROOT / script).is_file(), script


@needs_hooks
def test_matchers() -> None:
    pre = set(_matchers("PreToolUse")[0].split("|"))
    assert pre == {"Bash", "PowerShell", "Write", "Edit"}
    assert set(_matchers("PostToolUse")[0].split("|")) == {"Write", "Edit"}


@needs_hooks
def test_pretooluse_hook_fails_closed_when_it_cannot_run() -> None:
    hook = SETTINGS["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["onFailure"] == "block"


def test_settings_have_no_permission_bypass() -> None:
    text = json.dumps(SETTINGS).lower()
    assert "bypass" not in text
    assert "skipdangerous" not in text


def _codeowners() -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    for line in (ROOT / "CODEOWNERS").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            pattern, *owners = line.split()
            rows.append((pattern.lstrip("/"), owners))
    return rows


def test_every_protected_path_is_covered_by_codeowners() -> None:
    rows = _codeowners()
    for entry in gc.load_protected():
        covered = [
            owners
            for pattern, owners in rows
            if pattern == entry or (pattern.endswith("/") and entry.startswith(pattern))
        ]
        assert covered, f"{entry} is not covered by CODEOWNERS"
        assert covered[0] == ["@agustindiazcano"], entry


def test_codeowners_has_no_entry_outside_the_protected_list() -> None:
    protected = set(gc.load_protected())
    for pattern, _ in _codeowners():
        assert pattern in protected, f"CODEOWNERS entry {pattern} is not in protected_paths.txt"


def test_protected_paths_exist_in_the_repository() -> None:
    for entry in gc.load_protected():
        assert (ROOT / entry.rstrip("/")).exists(), entry


def test_ci_has_informational_protected_paths_job() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"^  protected_paths:", ci, re.MULTILINE)
    assert "pull_request" in ci
    assert "GITHUB_STEP_SUMMARY" in ci
    assert "protected_report.py" in ci
    job = ci.split("  protected_paths:", 1)[1]
    assert "continue-on-error: true" in job
