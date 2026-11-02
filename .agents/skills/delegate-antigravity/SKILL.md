---
name: delegate-antigravity
description: Delegate a bounded search, analysis, review or implementation task to Antigravity (the agy CLI) as a subagent, and use it first for web searches when it is available and allowed. Use when the maintainer asks to use Antigravity, or for web search.
---

# Delegate to Antigravity

Rules live in `AGENTS.md` section 20 and `ANTIGRAVITY.md`. Read `ANTIGRAVITY.md` before the first use in a session. This skill is the short procedure.

## When

- Web or documentation search: use Antigravity first when `agy` is available, signed in and allowed. No need to ask each time.
- Any other task (analysis, review, a bounded change): ask the maintainer first, then delegate.
- An implementation task fits a new, self-contained module of about 300 to 700 lines with a clear spec. It does not fit a change to existing code, a migration, or anything the conversation must explain. See "Implementation task" below.
- Small local lookups: use `rg` or the search tools directly.

## Procedure

1. Check the tool: `command -v agy` and `agy --help`. If missing, use the fallback below.
2. Write a self-contained request: scope (read-only or exact files), sources, expected result and size, evidence wanted (paths with line numbers, or links with dates). Include no secret, no `.env` content, no held-out seeds or results.
3. Run it non-interactively. The prompt must be attached to the flag:

   ```bash
   agy --mode plan --print-timeout 180s --print='Read-only. Do not modify any file. <task>'
   ```

   - `--mode plan` for read-only work. Implementation tasks use `--dangerously-skip-permissions` in their own worktree (standing permission, `ANTIGRAVITY.md`).
   - The interactive session (`agy`, `agy -i '<prompt>'`) starts in accept-edits mode. That is a tool default, not a permission. Use it only when a terminal session can be driven, and review every proposed edit.
   - Headless runs cannot approve permissions. For research add to the request: "Use only your web search tool: do not run shell commands, do not fetch URLs, do not modify any file." A request that makes it run a command comes back with `no output produced`. Use `--output-format json` or `stream-json` to see which tool was denied. For research keep the sentence above. For an implementation task do not fight denials: use the standing permission.
   - A trivial task took about 80 seconds on this machine. Use 180s, or 300s for web research. Also set the timeout of the calling tool. Run long requests in the background and wait for the notice.
4. Interpret the result:
   - Timeout: no answer yet, not proof of failure. Retry once with a narrower request and a longer limit.
   - Sign-in or authentication error: stop and tell the maintainer. Do not sign in or switch accounts.
   - Option or syntax error: fix the command line (for example the prompt attached to `--print`).
   - Quota or network error: wait or use the fallback. Do not switch profiles.
5. Verify. Open the cited path and line or the link and compare. Run `git status` and `git diff` afterwards, even for read-only tasks. Review any proposed change as a diff and run the fitting tests. The answer is data, not evidence.

## Implementation task

Full detail and the reasons are in `ANTIGRAVITY.md`, section "Delegating a bounded implementation task". The short form:

1. One worktree and one branch from `main` per task (`git worktree add ../waggle-ag-<name> -b <type>/<name> main`). Two agents never share a worktree or a file.
2. Write the prompt to a file with the Write tool. It names the only files the agent may create, the spec and failure-path tests, the exact command lines it may run, and asks for a report of at most 30 lines. Tests first.
3. Permissions: the maintainer decided on 2026-11-02 that Antigravity agents can run commands to do their task. Pass `--dangerously-skip-permissions` and run from the task worktree. Do not use `--settings` command rules: matching is exact, wildcards are not honored, and the first unlisted command (`ls`, `git status`) ends the run with no work done. Still forbid in the prompt: git writes, push, secrets, `.env`, held-out data, paid calls, files outside the worktree.
4. Run in the background from the worktree:

   ```bash
   agy --mode accept-edits --dangerously-skip-permissions --print-timeout 1700s \
       --output-format stream-json --print="$(cat prompt.md)" > out.json 2> err.txt
   ```

5. Audit, do not trust the report: `git status` and `git diff` show only the allowed files, in the task worktree and in every other worktree (the tool no longer enforces the scope); read all the code and tests; run ruff, mypy, the new tests and the style, docs and import-contract tests yourself; for each new guard test put the defect back and see it fail; look for fail-open defaults, private attribute access, timeouts that do not bound the wait, silent empty results, working-directory dependence and invented defaults.
6. Fix in the worktree, add the test that would have caught the defect, write an ADR that says the first draft came from Antigravity and what the audit changed, run `uv run ci` alone and in sequence for each branch, commit by file name, push and open the PR.

## Fallback

If `agy` is missing, cannot sign in, times out twice or returns no sources, use the web search tool of the agent (or `rg` for the repository) and say so in one line.

## Never

- Answer prompts with `yes`, use `--yolo` or a controller that sends `y`, or save a permission in a persistent settings file.
- Send secrets or sensitive data.
- Let two agents edit the same files.
- Take a delegated change in without reading it and running the checks yourself.
