"""PreToolUse safety guard: one stdin event per rule and the expected decision."""

import io
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import safety_guard

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "hooks" / "safety_guard.py"
PROTECTED = [
    "src/waggle/control/",
    "src/waggle/coordination/",
    "src/waggle/mcp_server/",
    "tests/importlint_fixtures/",
    ".github/workflows/",
    "AGENTS.md",
    "CODEOWNERS",
    ".claude/",
    "tools/hooks/",
]


def bash(command: str, tool: str = "Bash") -> dict[str, Any]:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}}


def write(path: str, content: str = "x") -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": content},
    }


def edit(path: str) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": "a", "new_string": "b"},
    }


def run_guard(
    raw: str,
    staged: Callable[[], list[str]] | None = None,
) -> tuple[str, str, str]:
    """Return (decision, reason, stderr) from running the guard on a raw stdin string."""
    out, err = io.StringIO(), io.StringIO()
    code = safety_guard.main(
        io.StringIO(raw),
        out,
        err,
        protected=PROTECTED,
        root=ROOT,
        staged_files=staged or (lambda: []),
    )
    assert code == 0, "the guard reports decisions in JSON and exits 0"
    text = out.getvalue().strip()
    if not text:
        return "allow", "", err.getvalue()
    spec = json.loads(text)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    return spec["permissionDecision"], spec.get("permissionDecisionReason", ""), err.getvalue()


def decide(event: dict[str, Any], staged: Callable[[], list[str]] | None = None) -> str:
    return run_guard(json.dumps(event), staged)[0]


DENY_COMMANDS = [
    "git push",
    "git push origin feat/x",
    "git push --force",
    "git push --force-with-lease origin x",
    "git push -f",
    "git push origin --delete old",
    "git merge main",
    "gh pr merge 12 --squash",
    "git reset --hard",
    "git reset --hard HEAD~1",
    "git clean -fd",
    "git clean -xfd",
    "git clean --force",
    "git commit --no-verify -m x",
    "git commit -n -m x",
    "git rebase --no-verify main",
    "git add -A",
    "git add --all",
    "git add .",
    "git add -Av",
    "git add .env",
    "git add -- .env",
    "git add src/.env.local",
    r"git add C:\projects\x\.env",
    "git add results/e1/heldout/run1.json",
    "git rm PENDING.md",
    "git status && git push",
    "cd src; git push",
    "git add a.py | git push",
    "git -C other push",
    "bash -c 'git push'",
    'powershell -Command "git push --force"',
    "echo SECRET > .env",
    "echo SECRET >> .env",
    "Set-Content .env x",
    "cp template .env",
    "tee .env",
    "echo x > results/e1/heldout/r.json",
    r"Copy-Item a.json results\e1\heldout\r.json",
    "[IO.File]::WriteAllText('.env', 'x')",
    "rm PENDING.md",
    "rm -f PENDING.md",
    "Remove-Item PENDING.md",
    "del PENDING.md",
    "mv PENDING.md old.md",
    "> PENDING.md",
    ": > PENDING.md",
    "truncate -s 0 PENDING.md",
    "Clear-Content PENDING.md",
]

ASK_COMMANDS = [
    "git branch -d feat/x",
    "git branch -D feat/x",
    "git branch --delete feat/x",
    "git worktree remove ../wt",
    "git worktree remove --force ../wt",
    "git rebase main",
    "git rebase -i HEAD~3",
    "git commit --amend",
    "git commit --amend --no-edit",
    "git status && git rebase main",
]

ALLOW_COMMANDS = [
    "git status",
    "git log --oneline -5",
    "git diff --staged",
    "git add src/waggle/tasks.py",
    "git add .env.example",
    "git add -- README.md PENDING.md",
    'git commit -m "docs: mention git push and git reset --hard in the guide"',
    "git branch feat/x",
    "git checkout -b feat/x",
    "git worktree add ../wt feat/x",
    "git worktree list",
    "git reset --soft HEAD~1",
    "git reset HEAD file.py",
    "git clean -n",
    "git stash",
    'echo "git push"',
    "uv run ci",
    "ls -la",
    "cat PENDING.md",
    "cat .env.example",
    "echo hi > notes.txt",
    "Get-Content PENDING.md",
    "gh pr view 3",
    "git log --format=%H > hashes.txt",
]


@pytest.mark.parametrize("command", DENY_COMMANDS)
@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_dangerous_commands_are_denied(command: str, tool: str) -> None:
    decision, reason, _ = run_guard(json.dumps(bash(command, tool)))
    assert decision == "deny", command
    assert reason, "a denial must say what to do instead"


@pytest.mark.parametrize("command", ASK_COMMANDS)
def test_risky_commands_ask_first(command: str) -> None:
    assert decide(bash(command)) == "ask", command


@pytest.mark.parametrize("command", ALLOW_COMMANDS)
def test_benign_commands_pass(command: str) -> None:
    assert decide(bash(command)) == "allow", command


def test_deny_wins_over_ask_in_one_command() -> None:
    assert decide(bash("git rebase main && git push")) == "deny"
    assert decide(bash("git commit --amend --no-verify")) == "deny"


def test_commit_with_staged_env_is_denied() -> None:
    assert decide(bash("git commit -m x"), staged=lambda: ["src/a.py", ".env"]) == "deny"


def test_commit_with_staged_heldout_result_is_denied() -> None:
    staged = lambda: ["results/e1/heldout/run1.json"]  # noqa: E731
    assert decide(bash("git commit -m x"), staged=staged) == "deny"


def test_commit_with_clean_stage_passes() -> None:
    staged = lambda: ["src/a.py", ".env.example", "results/e1/dev/run1.json"]  # noqa: E731
    assert decide(bash("git commit -m x"), staged=staged) == "allow"


def test_commit_asks_when_staged_files_cannot_be_read() -> None:
    def broken() -> list[str]:
        raise OSError("git not available")

    assert decide(bash("git commit -m x"), staged=broken) == "ask"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "src/.env",
        r"C:\projects\x\.env",
        str(ROOT / ".env"),
        "results/e1/heldout/run1.json",
        str(ROOT / "results" / "e1" / "heldout" / "run1.json"),
        r"results\e1\heldout\run1.json",
    ],
)
@pytest.mark.parametrize("builder", [write, edit])
def test_secret_and_heldout_writes_are_denied(path: str, builder: Callable[[str], Any]) -> None:
    assert decide(builder(path)) == "deny", path


def test_writing_empty_pending_is_denied() -> None:
    assert decide(write("PENDING.md", "")) == "deny"
    assert decide(write(str(ROOT / "PENDING.md"), "  \n ")) == "deny"


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        "results/e1/dev/run1.json",
        "src/waggle/sim/world.py",
        "src/waggle/control_extra.py",
        "README.md",
        "docs/GOTCHAS.md",
    ],
)
def test_ordinary_writes_pass(path: str) -> None:
    assert decide(write(path)) == "allow", path
    assert decide(edit(path)) == "allow", path


def test_pending_with_content_passes() -> None:
    assert decide(write("PENDING.md", "# Pending\n| 1 | P1 | task |")) == "allow"


@pytest.mark.parametrize(
    "path",
    [
        "src/waggle/control/envelope.py",
        "src/waggle/coordination/leases.py",
        "src/waggle/mcp_server/auth.py",
        "tests/importlint_fixtures/.importlinter",
        ".github/workflows/ci.yml",
        "AGENTS.md",
        "CODEOWNERS",
        ".claude/settings.json",
        "tools/hooks/safety_guard.py",
        str(ROOT / "src" / "waggle" / "control" / "x.py"),
        r"src\waggle\control\x.py",
    ],
)
@pytest.mark.parametrize("builder", [write, edit])
def test_protected_paths_ask_first(path: str, builder: Callable[[str], Any]) -> None:
    assert decide(builder(path)) == "ask", path


def test_unrelated_tool_passes() -> None:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "x"}}
    assert decide(event) == "allow"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        "null",
        '{"tool_input": {"command": "ls"}}',
        '{"tool_name": "Bash"}',
        '{"tool_name": "Bash", "tool_input": "ls"}',
        '{"tool_name": "Bash", "tool_input": {"command": 123}}',
        '{"tool_name": "Write", "tool_input": {"content": "x"}}',
        '{"tool_name": "Edit", "tool_input": {"file_path": 5}}',
    ],
)
def test_malformed_event_asks_never_allows(raw: str) -> None:
    decision, reason, _ = run_guard(raw)
    assert decision == "ask", raw
    assert reason


def test_crash_in_the_guard_asks_and_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: object, **__: object) -> object:
        raise RuntimeError("bug")

    monkeypatch.setattr(safety_guard, "evaluate", boom)
    decision, reason, stderr = run_guard(json.dumps(bash("ls")))
    assert decision == "ask"
    assert "crashed" in reason
    assert "bug" in stderr


def _cli(raw: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
        check=False,
    )


def test_cli_denies_with_documented_json_and_exit_zero() -> None:
    result = _cli(json.dumps(bash("git push --force")))
    assert result.returncode == 0
    spec = json.loads(result.stdout)["hookSpecificOutput"]
    assert spec == {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": spec["permissionDecisionReason"],
    }
    assert spec["permissionDecisionReason"]


def test_cli_is_silent_for_benign_input() -> None:
    result = _cli(json.dumps(bash("git status")))
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_cli_malformed_input_asks() -> None:
    result = _cli("{not json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"
