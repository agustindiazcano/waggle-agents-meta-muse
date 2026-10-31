# Waggle Hive: Last context

Updated: 2026-10-31 (PostgreSQL corridor foundation implemented; cloud verification pending).

## Done last
- Main remains at `04fba9d`. PR 54 (map binding) and PR 55 (mapped S03 routes) are open and green; PR 55 targets PR 54. The principal checkout and untracked `index (1).html` are untouched.
- Maintainer approval covers the remaining mock implementation, including database migrations, fencing, audit and MCP wiring. The maintainer separately approved `psycopg[binary]==3.3.6`; it is installed and documented. No real provider client, paid call, secret or cap change was made.
- Branch `feat/postgres-coordination`, based on PR 55, adds separate bounded database connections, explicit revision 1, durable corridor transitions and an idempotent fenced event insert under the same row locks as its token check. It does not dispatch robot tools or implement MCP audit.
- Tests first failed for the missing modules and workflow, and for the old heavy-workflow zero-selection allowance. The local configuration/unit/workflow selection has 25 passes; strict types and changed-file lint pass. Real database tests are heavy and cloud-only. No database migration was run locally; the CLI correctly failed on missing DATABASE_URL.

## Current state
- Migration checks the expected current revision under a transaction lock, never provisions sample data and never runs automatically. Resource registration does not reset counters. All zone rows are locked in canonical order; this is a coarse reference implementation without a throughput claim. See ADR-033 and docs/MOCK_IMPLEMENTATION.md.
- Cloud correctness tests still need execution before claiming persistence works. They cover revision and DDL rollback, Hypothesis parity, concurrency, occupied expiry/restart, idempotency, bigint exhaustion and a row-lock race. The manual postgres.yml workflow has no provider keys; the existing heavy.yml can run the same tests with heavy/dev on this branch.
- Task state/queue, workers, SKIP LOCKED recovery, mission handoff and production MCP remain pending. Those implementations are authorized. Keep mock providers; E3 labels remain pending and must not be scored. No E2 sweep, paid call or held-out run has executed.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/MOCK_IMPLEMENTATION.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-028 through ADR-033), docs/THREAT_MODEL.md, docs/EXPERIMENTS.md and docs/GOTCHAS.md. Check remote PRs, branches, status and worktrees before acting.

Main was last at 04fba9d. PR 54 contains map binding and PR 55 mapped S03 routes. Inspect feat/postgres-coordination and its PR before duplicating revision 1 and the durable corridor repository. This branch is based on PR 55; maintain dependency order and retarget after each merge. Verify cloud PostgreSQL test results before claiming the implementation works. No local database was used.

The remaining mock implementation, database migrations, fencing, audit and MCP wiring are approved. Psycopg 3.3.6 is explicitly approved and installed. Do not ask again for that scope. Next are task queue/state events, workers/recovery and mission handoff, then MCP audit/rate-limit repositories and tools. Read the actual migration revision before any migration. Do not treat the fenced event proof as a robot tool or MCP audit. Do not make paid calls, change secrets or caps, or run held-out seeds without specific authorization. Pending E3 labels and missing layers must block evaluation. No scope is cut.

Use isolated worktrees, task branches, tests first and Conventional Commits with Co-Authored-By trailers. Before pushing require uv run ci on HEAD, gitleaks and a reviewed diff. Never commit to main, force push, merge PRs or commit index (1).html. The maintainer reviews and merges.
```
