# Waggle Hive: Last context

Updated: 2026-10-31 (handoff and worker loop merged; E3 labels in PR 66).

## Done last
- Main is at `77f2ce0` after PR 65 merged, on top of PR 64 (handoff, revision 3) and PostgreSQL coordination, task recovery and the multi-warehouse planning document. `index (1).html` remains untracked and untouched.
- The maintainer approved all 25 E3 labels. They are recorded on `test/e3-approved-main`, PR 66 open. T11 needs separate structural scoring; E3 production entry points and evaluation remain incomplete.
- PR 64 (`feat/physical-handoff`) added a task handoff requirement, migration revision 3 and transactional completion with live task and zone credentials and current trusted occupancy. Ordinary task completion denies required handoffs. Cloud PostgreSQL run 41235442937 on 15d505f passed all 36 tests, including ten new handoff cases. No physical robot effect, authenticated caller or trusted occupancy ingestion is implemented.

- PR 65 (`feat/worker-daemon`) added a recovery-first cooperative worker polling loop and a service adapter around run_once with fresh claim ids and interruptible waits. It is not a process entry point and has no production handler.

- Branch `feat/mcp-audit-ratelimit` (PR 67) adds schema revision 4 (`mcp_audit`) and `McpAuditRepository` (ADR-037). `uv run ci` passes; cloud run 41239557152 passed all 48 PostgreSQL tests (12 new).

- Branch `feat/mcp-identity-store` adds schema revision 5 (`robot_identities`) and `PostgresIdentityStore` (ADR-039). Unit tests and `uv run ci` pass; the eight PostgreSQL cases await the cloud run.

## Current state
- Handoff correctness passed its cloud tests; it is not an E2 evaluation. Complete the worker loop integration with trusted adapters and process supervision. Complete trusted mission construction, occupancy ingestion, physical effects and worker integration. The repository cannot infer physical intent when an ordinary task is created. Follow `docs/MOCK_IMPLEMENTATION.md`.
- Local mock implementation, migrations, fencing, audit and MCP work were approved. Paid calls, secret or cap changes, held-out seeds and global implementation remain unauthorized.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees. PR 67 (revision 4, ADR-037) passed its cloud run; next is the MCP server wiring (ADR-032 branch e). Main was at 77f2ce0 with PRs 64 and 65 merged. The handoff cloud PostgreSQL run 41235442937 passed all 36 tests; complete trusted mission construction, occupancy ingestion, physical effects and worker integration. The worker daemon adds the polling loop and service adapter but still needs process integration and cloud verification. Ordinary completion denies declared handoff tasks; unmarked tasks remain ordinary. Branch test/e3-approved-main (PR 66) contains the maintainer-approved corpus labels. Preserve T11 structural scoring semantics. Do not run E2/E3, held-out seeds, paid calls or global implementation without authorization. Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review.
```
