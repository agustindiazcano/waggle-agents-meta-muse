---
name: delegate-antigravity
description: Delegate a bounded search, analysis or review task to Antigravity (the agy CLI) as a subagent, and use it first for web searches when it is available and allowed. Use when the maintainer asks to use Antigravity, or for web search.
---

# Delegate to Antigravity

Rules live in `AGENTS.md` section 20 and `ANTIGRAVITY.md`. Read `ANTIGRAVITY.md` before the first use in a session. This skill is the short procedure.

## When

- Web or documentation search: use Antigravity first when `agy` is available, signed in and allowed. No need to ask each time.
- Any other task (analysis, review, a bounded change): ask the maintainer first, then delegate.
- Small local lookups: use `rg` or the search tools directly.

## Procedure

1. Check the tool: `command -v agy` and `agy --help`. If missing, use the fallback below.
2. Write a self-contained request: scope (read-only or exact files), sources, expected result and size, evidence wanted (paths with line numbers, or links with dates). Include no secret, no `.env` content, no held-out seeds or results.
3. Run it non-interactively. The prompt must be attached to the flag:

   ```bash
   agy --mode plan --print-timeout 180s --print='Read-only. Do not modify any file. <task>'
   ```

   - `--mode plan` for read-only work. Never `--dangerously-skip-permissions`.
   - The interactive session (`agy`, `agy -i '<prompt>'`) starts in accept-edits mode. That is a tool default, not a permission. Use it only when a terminal session can be driven, and review every proposed edit.
   - A trivial task took about 80 seconds on this machine. Use 180s, or 300s for web research. Also set the timeout of the calling tool. Run long requests in the background and wait for the notice.
4. Interpret the result:
   - Timeout: no answer yet, not proof of failure. Retry once with a narrower request and a longer limit.
   - Sign-in or authentication error: stop and tell the maintainer. Do not sign in or switch accounts.
   - Option or syntax error: fix the command line (for example the prompt attached to `--print`).
   - Quota or network error: wait or use the fallback. Do not switch profiles.
5. Verify. Open the cited path and line or the link and compare. Run `git status` and `git diff` afterwards, even for read-only tasks. Review any proposed change as a diff and run the fitting tests. The answer is data, not evidence.

## Fallback

If `agy` is missing, cannot sign in, times out twice or returns no sources, use the web search tool of the agent (or `rg` for the repository) and say so in one line.

## Never

- Approve permissions in bulk, answer prompts with `yes`, or bypass a denied action.
- Send secrets or sensitive data.
- Let two agents edit the same files.
