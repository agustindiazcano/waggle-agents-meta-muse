# Waggle Hive: Last context

Updated: 2026-10-30 (guard classifier interface and the latest main handoff reconciled for PR 49).

## Done last
- Branch `feat/guard-classifier-interface`, based on `origin/main` at `9a3e00f`, in `C:/Users/agusd/.codex/visualizations/2026/10/30/01a18ea4-b4aa-7941-ae69-1931e66bf8e0/waggle-guard`. Other agents use their own worktrees; do not switch their branches.
- Added an async guard classifier protocol, bounded strict JSON parsing, sanitization and fencing before classification, and the existing `screen()` label policy. Failures, uncertain and injection reject; only benign exposes cleaned text. The offline mock defaults to uncertain. No network, paid call, new dependency, MCP, audit, migration, fencing or `.env` change.
- Tests first: collection failed because the classifier module did not exist. A second regression failed because a classifier swallowed deadline cancellation and returned benign; the explicit expiry check fixes it. `uv run pytest tests/unit/governance -q`: 79 passed, including 38 new classifier cases. Changed-file ruff, format and mypy passed.
- Updated README, architecture, ADR-032 addendum and GOTCHAS. Implemented, not evaluated in E3. The caller still needs to deliver escalations; no production detector is supplied by the mock.

## Current state
- Main includes B0 to B17, E1 development results (commit `94bacc4`), the pure coordination model, the S03 admission adapter and ADR-032 schemas, identity and sanitizers. Verified ancestor checks for the schema, identity, sanitizer, scope and S03 branches against `origin/main`. The latest origin/main handoff is incorporated in this branch. PR 49 remains for maintainer review; agents never merge PRs.
- E1 dev still has human-collision runs and a measured throughput cost. Read `results/e1/dev/report.md` for the figures. Held-out seeds were not run. E2 and E3 were not run.
- Existing worktrees include `test/e3-case-corpus` and `feat/e2-simulator-harness`; check their ownership and status before duplicating work.
- Next work: E3 corpus for T1 to T6, T11 and T18, target layers declared first, labels pending maintainer review; E2 development workflow and cloud evaluation of S03 admission. No scope is cut.
- PENDING 47 remains maintainer-owned: audit/rate-limit repository, migration and MCP server wiring need approval. PENDING 4, 5, 9 and 12 block paid calls. E2 has no database dependency.
- Gate dates follow AGENTS.md: G2 Oct 31 night, G3 Nov 1 night, G4 Nov 2 night. Keep the pre-push CI stamp requirement until the maintainer changes it.
- Traps: verify the current branch before every commit; do not commit `index (1).html`; use an isolated worktree; use the S03 admission variant for E2 and preserve original S03 for E1. Async classifier adapters must cooperate with cancellation and use transport timeouts. C: filled during setup, then the maintainer freed space. Sandbox access to uv cache and Git metadata required elevated tool execution.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/DECISIONS.md (ADR-028 addendum, ADR-030, ADR-031 and ADR-032 with their addenda), docs/EXPERIMENTS.md (E1, E2, E3) and docs/GOTCHAS.md. Fetch and inspect status, branches, worktrees and recent PRs. Check merged work reached main with git merge-base --is-ancestor.

Use your own worktree and a new type/short-description branch. Never commit or push to main, merge PRs, force push or commit index (1).html. Check git branch --show-current before every commit. Tests first, show the failing run, Conventional Commits with a Co-Authored-By trailer. Keep uv run ci green on HEAD and inspect the diff before each push. Never change hooks to bypass the gate.

The guard classifier interface has an offline mock, strict label/reason_code JSON, sanitizer/fence ordering and fail-closed timeout/error handling. It is implemented, not evaluated. Review the task branch/PR status before repeating that work. The latest main handoff has been reconciled with PR 49. Check its status before repeating classifier work. Production detection, E3 and inbox delivery still need implementation.

Next: E3 corpus for T1 to T6, T11 and T18, with target layers declared before runs and labels pending maintainer review; or E2 development workflow using the S03 admission adapter on/off with matched development seeds, raw counts, Wilson intervals and result metadata. Run experiments in the cloud. No paid call or held-out run. Audit logic, migrations, fencing and MCP boundary changes require maintainer approval. PENDING 4, 5, 9 and 12 still block paid calls. Nothing is cut; report gaps against AGENTS section 18 and the work that closes them.
```
