"""PreToolUse safety guard for Bash, PowerShell, Write and Edit (standard library only).

Reads the hook event JSON on stdin and prints the documented decision JSON on stdout.
No output means no objection. A malformed event or a crash in this script asks, never
allows. Rules come from AGENTS.md (git rules, hard rules) and the maintainer.
"""

import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

import guard_common as gc

logger = logging.getLogger("safety_guard")

SHELLS = {"bash", "sh", "zsh", "powershell", "pwsh", "cmd"}
SHELL_FLAGS = {"-c", "-command", "/c"}
WRAPPERS = {"sudo", "env", "command", "time", "nohup", "exec"}
WRITE_COMMANDS = {
    "tee", "cp", "mv", "touch", "install", "ln", "truncate", "dd", "set-content",
    "add-content", "out-file", "new-item", "clear-content", "copy-item", "move-item",
    "copy", "move", "rename-item", "ren",
}  # fmt: skip
DELETE_COMMANDS = {
    "rm", "del", "erase", "rmdir", "remove-item", "ri", "unlink", "mv", "move", "move-item",
    "clear-content", "truncate",
}  # fmt: skip
DOTNET_WRITES = ("writealltext", "writealllines", "writeallbytes", "appendalltext")
EMPTY_WORDS = {":", "true", "echo", "-n", "cat", "/dev/null", "printf", ""}
STAGED_UNREADABLE = "could not read the staged files, so the commit cannot be checked"
MAX_SHELL_DEPTH = 3
PRE_PUSH_TIMEOUT = 240
PROTECTED_BRANCHES = frozenset({"main", "master"})
TASK_BRANCH = re.compile(r"(feat|fix|test|docs|exp|chore|ci)/[a-z0-9]+(-[a-z0-9]+)*")
PUSH_FLAGS = frozenset({"-u", "--set-upstream"})
REMOTE_WRITES = frozenset({"add", "set-url", "remove", "rm", "rename", "set-head", "set-branches"})
GH_READS = {
    "repo": frozenset({"view", "list", "clone"}),
    "secret": frozenset({"list"}),
    "auth": frozenset({"status"}),
    "release": frozenset({"list", "view", "download"}),
}
GH_API_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
GH_API_BODY_FLAGS = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})
INTERPRETERS = frozenset({"python", "python3", "py", "node", "perl", "ruby", "deno", "bun"})
INTERPRETER_FLAGS = frozenset({"-c", "-e", "-r", "--eval", "-command"})
GUARDED_TEXT = ("git push", "git remote", "gh api")


class MalformedEventError(ValueError):
    """The hook event is not shaped as documented."""


@dataclass(frozen=True)
class Verdict:
    """A decision with the reason shown to the user or to Claude."""

    kind: str
    reason: str = ""


ALLOW = Verdict("allow")
_RANK = {"allow": 0, "ask": 1, "deny": 2}


def worst(verdicts: list[Verdict]) -> Verdict:
    """The most restrictive verdict. Deny beats ask beats allow."""
    result = ALLOW
    for v in verdicts:
        if _RANK[v.kind] > _RANK[result.kind]:
            result = v
    return result


@dataclass(frozen=True)
class Context:
    """Everything a rule needs besides the event itself."""

    root: Path
    protected: list[str]
    staged_files: Callable[[], list[str]]
    current_branch: Callable[[], str]
    pre_push: Callable[[], list[str]]


def git_staged_files(root: Path) -> list[str]:
    """Names of staged files, from ``git diff --cached``. Raises OSError on failure."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "git diff --cached failed")
    return [n for n in result.stdout.split("\0") if n]


def git_current_branch(root: Path) -> str:
    """Name of the checked out branch, or ``HEAD`` when detached. Raises OSError on failure."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "git rev-parse failed")
    return result.stdout.strip()


def run_pre_push_check(root: Path) -> list[str]:
    """Run tools/ci/pre_push_check.py. Returns the problems it printed, empty when it passed."""
    script = root / "tools" / "ci" / "pre_push_check.py"
    if not script.is_file():
        return ["tools/ci/pre_push_check.py is missing, so the push cannot be checked"]
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=PRE_PUSH_TIMEOUT,
        check=False,
    )
    if result.returncode == 0:
        return []
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    return lines or [f"the pre-push check failed with exit code {result.returncode}"]


# ---------------------------------------------------------------- git and gh rules


def _flags(args: list[str]) -> tuple[set[str], set[str]]:
    """Return (long flags without values, short flag letters) from an argument list."""
    long_flags: set[str] = set()
    short: set[str] = set()
    for arg in args:
        if arg.startswith("--") and len(arg) > 2:
            long_flags.add(arg.split("=", 1)[0])
        elif arg.startswith("-") and len(arg) > 1 and not arg.startswith("--"):
            short.update(arg[1:])
    return long_flags, short


def _git_subcommand(args: list[str]) -> tuple[str, list[str]]:
    """Skip git global options and return (subcommand, remaining args)."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            i += 2
        elif arg.startswith("-"):
            i += 1
        else:
            return arg.lower(), args[i + 1 :]
    return "", []


def _paths_in(args: list[str], ctx: Context) -> list[str]:
    return [gc.normalize_path(a, ctx.root) for a in args if not a.startswith("-") or a == "-"]


def _git_rules(args: list[str], ctx: Context) -> Verdict:
    sub, rest = _git_subcommand(args)
    long_flags, short = _flags(args)
    if "--no-verify" in long_flags or (sub == "commit" and "n" in short):
        return Verdict(
            "deny", "Hooks and CI are never skipped. Run the commit without --no-verify."
        )
    if sub == "push":
        return _git_push(rest, ctx)
    if sub == "remote" and rest[:1] and rest[0].lower() in REMOTE_WRITES:
        return Verdict(
            "deny", "Remotes are not changed by agents. Only git remote -v and get-url are allowed."
        )
    if sub == "merge":
        return Verdict("deny", "Agents never merge. Ask the maintainer to merge the pull request.")
    if sub == "reset" and "--hard" in long_flags:
        return Verdict(
            "deny", "git reset --hard is not allowed. Use git reset --soft or git stash."
        )
    if sub == "clean" and ("--force" in long_flags or "f" in short):
        return Verdict("deny", "git clean -f is not allowed. Use git clean -n and delete by name.")
    if sub == "add":
        return _git_add(rest, ctx)
    if sub == "rm":
        paths = _paths_in(rest, ctx)
        if any(gc.is_pending_file(p) for p in paths):
            return Verdict("deny", "PENDING.md may be edited, never deleted. Edit its contents.")
        return ALLOW
    if sub == "commit":
        return _git_commit(long_flags, ctx)
    if sub == "branch" and ({"--delete", "-d"} & long_flags or "d" in short or "D" in short):
        return Verdict("ask", "Deleting a branch can lose unmerged work.")
    if sub == "worktree" and rest[:1] == ["remove"]:
        return Verdict("ask", "Removing a worktree can lose uncommitted work.")
    if sub == "rebase":
        return Verdict("ask", "Rebase rewrites history. Confirm it is local and unpushed.")
    return ALLOW


def _gh_api_method(args: list[str]) -> str:
    """The HTTP method a ``gh api`` call asks for. A body flag makes it POST unless set."""
    method = ""
    for i, arg in enumerate(args):
        low = arg.lower()
        if low in ("-x", "--method") and i + 1 < len(args):
            method = args[i + 1].upper()
        elif low.startswith("--method="):
            method = arg.split("=", 1)[1].upper()
        elif arg.startswith("-X") and len(arg) > 2:
            method = arg[2:].upper()
    if not method and any(a.split("=", 1)[0] in GH_API_BODY_FLAGS for a in args):
        return "POST"
    return method


def _gh_rules(args: list[str], ctx: Context) -> Verdict:
    words = [a.lower() for a in args]
    group = words[0] if words else ""
    if group == "pr" and words[1:2] == ["merge"]:
        return Verdict("deny", "Agents never merge. Ask the maintainer to merge.")
    if group == "pr" and words[1:2] == ["create"]:
        return _push_gate(ctx)
    if group == "api" and _gh_api_method(args[1:]) in GH_API_WRITE_METHODS:
        return Verdict("deny", "gh api writes are not allowed. Read with GET or use gh pr create.")
    if group in GH_READS:
        action = next((w for w in words[1:] if not w.startswith("-")), "")
        if action not in GH_READS[group]:
            return Verdict("deny", f"gh {group} {action} is not read-only. Ask the maintainer.")
    return ALLOW


def _interpreter_rules(args: list[str]) -> Verdict:
    """Best effort: an interpreter one-liner that spells out a guarded command is denied."""
    if not INTERPRETER_FLAGS & {a.lower() for a in args}:
        return ALLOW
    text = " ".join(args).lower()
    if any(marker in text for marker in GUARDED_TEXT):
        return Verdict(
            "deny", "Do not run git push, git remote or gh api through an interpreter one-liner."
        )
    return ALLOW


def _push_gate(ctx: Context) -> Verdict:
    """Checks shared by git push and gh pr create. Any failure to check denies."""
    try:
        branch = ctx.current_branch()
    except (OSError, subprocess.SubprocessError):
        return Verdict("deny", "could not read the current branch, so the push is denied")
    if branch in PROTECTED_BRANCHES or branch == "HEAD":
        return Verdict(
            "deny",
            f"Never push or open a PR from {branch}. Work on a type/short-description branch.",
        )
    try:
        problems = ctx.pre_push()
    except (OSError, subprocess.SubprocessError) as err:
        return Verdict("deny", f"the pre-push check could not run, so the push is denied: {err}")
    if problems:
        return Verdict("deny", "Pre-push check failed: " + "; ".join(problems))
    return ALLOW


def _git_push(rest: list[str], ctx: Context) -> Verdict:
    """Allow only ``git push [-u] origin <type/short-description>`` that passes the gate."""
    flags = [a for a in rest if a.startswith("-")]
    if any(f not in PUSH_FLAGS for f in flags):
        return Verdict(
            "deny",
            "Only -u or --set-upstream are allowed. Force, delete, tags and other flags are not.",
        )
    positional = [a for a in rest if not a.startswith("-")]
    if len(positional) != 2 or positional[0] != "origin":
        return Verdict("deny", "Use exactly: git push [-u] origin <type/short-description>.")
    branch = positional[1]
    if branch in PROTECTED_BRANCHES:
        return Verdict("deny", "Never push to main. Push the task branch and open a PR.")
    if TASK_BRANCH.fullmatch(branch) is None:
        return Verdict(
            "deny",
            "The branch must be an explicit name like feat/short-description. "
            "Refspecs, HEAD and tags are not allowed.",
        )
    return _push_gate(ctx)


def _forces(long_flags: set[str], short: set[str]) -> bool:
    return bool({"--force", "--force-with-lease"} & long_flags) or "f" in short


def _git_add(rest: list[str], ctx: Context) -> Verdict:
    long_flags, short = _flags(rest)
    if "--all" in long_flags or "A" in short:
        return Verdict("deny", "Stage files by name. Do not use git add -A.")
    paths = _paths_in(rest, ctx)
    if any(p in (".", "") for p in paths):
        return Verdict("deny", "Stage files by name. Do not use git add .")
    for p in paths:
        if gc.is_env_file(p):
            return Verdict("deny", ".env files are never staged. Use .env.example for names.")
        if gc.is_heldout_path(p):
            return Verdict("deny", "Held-out results are committed only by the maintainer.")
    return ALLOW


def _git_commit(long_flags: set[str], ctx: Context) -> Verdict:
    try:
        staged = [gc.normalize_path(s, ctx.root) for s in ctx.staged_files()]
    except (OSError, subprocess.SubprocessError):
        return Verdict("ask", STAGED_UNREADABLE)
    for path in staged:
        if gc.is_env_file(path):
            return Verdict("deny", f"{path} is staged. Unstage it with git restore --staged.")
        if gc.is_heldout_path(path):
            return Verdict("deny", f"{path} is a held-out result. Only the maintainer commits it.")
    if "--amend" in long_flags:
        return Verdict("ask", "Amend only an unpushed local commit.")
    return ALLOW


# ---------------------------------------------------------------- file write rules


def _write_target_rules(paths: list[str], ctx: Context) -> Verdict:
    for raw in paths:
        p = gc.normalize_path(raw, ctx.root)
        if gc.is_env_file(p):
            return Verdict("deny", ".env files are edited by the maintainer only.")
        if gc.is_heldout_path(p):
            return Verdict("deny", "Held-out results are written by the maintainer only.")
    return ALLOW


def _segment_rules(words: list[str], redirects: list[str], ctx: Context, depth: int) -> Verdict:
    verdicts: list[Verdict] = []
    index = 0
    while index < len(words) and (words[index].lower() in WRAPPERS or "=" in words[index][:-1]):
        index += 1
    words = words[index:]
    name = _command_name(words[0]) if words else ""
    args = words[1:]
    verdicts.append(_write_target_rules(redirects, ctx))
    if not words:
        if any(gc.is_pending_file(gc.normalize_path(r, ctx.root)) for r in redirects):
            verdicts.append(Verdict("deny", "PENDING.md may be edited, never emptied."))
        return worst(verdicts)
    if name == "git":
        verdicts.append(_git_rules(args, ctx))
    elif name == "gh":
        verdicts.append(_gh_rules(args, ctx))
    elif name in SHELLS and depth < MAX_SHELL_DEPTH:
        verdicts.append(_nested_shell(args, ctx, depth))
    if name in INTERPRETERS or name in SHELLS:
        verdicts.append(_interpreter_rules(args))
    arg_paths = [a.split("=", 1)[-1] if a.startswith("of=") else a for a in args]
    if _is_write(name, args):
        verdicts.append(_write_target_rules(arg_paths, ctx))
    if name in DELETE_COMMANDS and any(
        gc.is_pending_file(gc.normalize_path(a, ctx.root)) for a in arg_paths
    ):
        verdicts.append(Verdict("deny", "PENDING.md may be edited, never deleted or moved."))
    emptying = bool(redirects) and {w.lower() for w in words} <= EMPTY_WORDS
    if emptying and any(gc.is_pending_file(gc.normalize_path(r, ctx.root)) for r in redirects):
        verdicts.append(Verdict("deny", "PENDING.md may be edited, never emptied."))
    return worst(verdicts)


def _command_name(word: str) -> str:
    base = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _is_write(name: str, args: list[str]) -> bool:
    if name in WRITE_COMMANDS:
        return True
    return name == "sed" and any(a == "--in-place" or a.startswith("-i") for a in args)


def _nested_shell(args: list[str], ctx: Context, depth: int) -> Verdict:
    for i, arg in enumerate(args[:-1]):
        if arg.lower() in SHELL_FLAGS:
            return analyze_command(args[i + 1], ctx, depth + 1)
    return ALLOW


def analyze_command(command: str, ctx: Context, depth: int = 0) -> Verdict:
    """Check every simple command in a command line. The most restrictive verdict wins."""
    segments = gc.tokenize(command)
    verdicts = [_segment_rules(seg.words, seg.redirects, ctx, depth) for seg in segments]
    if any(marker in command.lower() for marker in DOTNET_WRITES):
        words = [w.strip(",;") for seg in segments for w in seg.words]
        verdicts.append(_write_target_rules(words, ctx))
    return worst(verdicts)


# ---------------------------------------------------------------- tools


def _require(mapping: dict[str, Any], key: str, kind: type) -> Any:
    value = mapping.get(key)
    if not isinstance(value, kind):
        raise MalformedEventError(f"{key} is missing or not a {kind.__name__}")
    return value


def _file_rules(tool: str, tool_input: dict[str, Any], ctx: Context) -> Verdict:
    raw = _require(tool_input, "file_path", str)
    path = gc.normalize_path(raw, ctx.root)
    deny = _write_target_rules([raw], ctx)
    if deny.kind != "allow":
        return deny
    if tool == "Write":
        content = _require(tool_input, "content", str)
        if gc.is_pending_file(path) and not content.strip():
            return Verdict("deny", "PENDING.md may be edited, never emptied.")
    if gc.is_protected(path, ctx.protected):
        return Verdict("ask", f"{path} is a protected path (see tools/hooks/protected_paths.txt).")
    return ALLOW


def evaluate(event: object, ctx: Context) -> Verdict:
    """Decide for one hook event. Raises MalformedEventError when the event is unusable."""
    if not isinstance(event, dict):
        raise MalformedEventError("event is not a JSON object")
    tool = _require(event, "tool_name", str)
    tool_input = _require(event, "tool_input", dict)
    if tool in ("Bash", "PowerShell"):
        return analyze_command(_require(tool_input, "command", str), ctx)
    if tool in ("Write", "Edit"):
        return _file_rules(tool, tool_input, ctx)
    return ALLOW


def _emit(stdout: TextIO, verdict: Verdict) -> None:
    if verdict.kind != "allow":
        stdout.write(json.dumps(gc.decision_output(verdict.kind, verdict.reason)) + "\n")


def main(
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    *,
    protected: list[str] | None = None,
    root: Path | None = None,
    staged_files: Callable[[], list[str]] | None = None,
    current_branch: Callable[[], str] | None = None,
    pre_push: Callable[[], list[str]] | None = None,
) -> int:
    """Run the guard. Always exits 0 and reports ask or deny in JSON."""
    project = root or Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    ctx = Context(
        root=project,
        protected=protected if protected is not None else gc.load_protected(),
        staged_files=staged_files or (lambda: git_staged_files(project)),
        current_branch=current_branch or (lambda: git_current_branch(project)),
        pre_push=pre_push or (lambda: run_pre_push_check(project)),
    )
    try:
        event = json.loads(stdin.read().lstrip(chr(0xFEFF)))
        verdict = evaluate(event, ctx)
    except (json.JSONDecodeError, MalformedEventError) as err:
        verdict = Verdict("ask", f"safety guard could not read the event: {err}")
    except Exception as err:  # the guard must never allow because it crashed
        logger.exception("safety guard crashed")
        stderr.write(f"safety_guard crashed: {err!r}\n")
        verdict = Verdict("ask", "safety guard crashed, so this action needs your approval")
    _emit(stdout, verdict)
    return 0


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    sys.exit(main(sys.stdin, sys.stdout, sys.stderr))
