# Waggle Hive: Last context

Updated: 2026-10-31 (task queue and recovery verified in cloud; PR 57 open).

## Done last
- Main remains at `04fba9d`; PRs 54, 55 and 56 are open. PR 56 contains corridor persistence, verified by 10 cloud PostgreSQL tests in run 41217047545. The principal checkout and untracked `index (1).html` are untouched.
- PR 57, branch `feat/postgres-task-recovery`, is based on PR 56. It adds the pure task model, schema revision 2, immutable dependency metadata, SKIP LOCKED claims/recovery, transition event snapshots and a fenced worker iteration. Revision targets are explicit and forward-only. No runtime dependency was added.
- Tests first failed on missing modules and unsupported migration targets. An additional regression showed an untyped handler result completing a task; the worker now requires the exact HandlerOutcome.DONE enum. The local coordination/database/worker selection has 92 passing tests; changed-source lint and strict types pass.

## Current state
- Cloud run 41225808111 on `085f8ff` passed all 26 PostgreSQL tests (JUnit: zero failures, errors or skips). Full CI passed 1626 tests with 4 existing skips, 26 deselected and 92 percent fast-tier coverage. Heavy tests cover upgrade preservation/rollback, competing workers and sweepers, skip-locked rows, stale completion after reassignment, dependency gating, event rollback, handler transaction boundaries and an actual process exiting after its durable claim. Do not run these tests locally; no local database or migration was used.
- A worker commits claim and start before its handler and never repeats a handler for a replayed claim. Invalid results and exceptions fail closed. Expiry recovery retains tokens, respects the attempt cap and never releases occupied zones. These are queue/iteration APIs, not a production worker daemon or physical robot executor. Full E2 remains pending.
- Maintainer approval already covers the remaining mock plan, database migrations, fencing, audit and MCP wiring. Psycopg 3.3.6 is explicitly approved. Paid calls, cap/secret changes and held-out runs remain unauthorized. E3 labels stay pending and unscored.
- Next: atomic physical handoff with task and zone fencing, worker daemon and production MCP audit/rate-limit/tool wiring. Keep all remaining scope in docs/MOCK_IMPLEMENTATION.md.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/MOCK_IMPLEMENTATION.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-028 through ADR-034), docs/THREAT_MODEL.md, docs/EXPERIMENTS.md and docs/GOTCHAS.md. Check remote PRs, status, branches and worktrees before acting.

Main was last at 04fba9d. PRs 54 to 56 are stacked; PR 56 has the verified PostgreSQL corridor foundation. Inspect feat/postgres-task-recovery and its PR before duplicating the task model, migration revision 2, SKIP LOCKED queue/recovery and worker iteration. This branch depends on PR 56. Cloud run 41225808111 passed all 26 PostgreSQL tests on 085f8ff; verify final PR checks before acting; no local database was used. Preserve dependency order and retarget after each merge.

The remaining mock implementation, migrations, fencing, audit and MCP wiring are approved; psycopg 3.3.6 is approved and installed. Do not ask again for that scope. Next are physical handoff with both task and zone credentials, worker daemon and MCP wiring. Queue completion is not physical handoff, and arbitrary handler returns are not success. Inspect actual migration revision before applying a migration. No paid calls, cap/secret changes or held-out runs without specific authorization. Pending E3 labels and missing layers must block evaluation. Nothing is cut.

Use isolated worktrees, task branches, tests first and Conventional Commits with Co-Authored-By trailers. Before push require uv run ci on HEAD, gitleaks and reviewed diffs. Never commit to main, force push, merge PRs or commit index (1).html. The maintainer reviews and merges.
```
