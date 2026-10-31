# Waggle Hive: Last context

Updated: 2026-10-31 (worker polling loop prepared; handoff cloud verification passed).

## Done last
- Main is at `ab90268` after PR 63 merged, including PostgreSQL coordination, task recovery and the multi-warehouse planning document. `index (1).html` remains untracked and untouched.
- The maintainer approved all 25 E3 labels. They are recorded on local branch `test/e3-approved-main`, not yet pushed. T11 needs separate structural scoring; E3 production entry points and evaluation remain incomplete.
- Branch `feat/physical-handoff` adds a task handoff requirement, migration revision 3 and transactional completion with live task and zone credentials and current trusted occupancy. Ordinary task completion denies required handoffs. Cloud PostgreSQL run 41235442937 on 15d505f passed all 36 tests, including ten new handoff cases. No physical robot effect, authenticated caller or trusted occupancy ingestion is implemented.

- Branch `feat/worker-daemon`, based on `feat/physical-handoff`, adds a recovery-first cooperative worker polling loop and a service adapter around run_once with fresh claim ids and interruptible waits. It is not a process entry point and has no production handler.

- Branch `feat/mcp-audit-ratelimit` adds schema revision 4 (`mcp_audit`) and `McpAuditRepository` (ADR-037). Unit tests and `uv run ci` pass (1678 passed); the twelve PostgreSQL cases have not run in the cloud yet.

## Current state
- Handoff correctness passed its cloud tests; it is not an E2 evaluation. Complete the worker loop integration with trusted adapters and process supervision. Complete trusted mission construction, occupancy ingestion, physical effects and worker integration. The repository cannot infer physical intent when an ordinary task is created. Follow `docs/MOCK_IMPLEMENTATION.md`.
- Local mock implementation, migrations, fencing, audit and MCP work were approved. Paid calls, secret or cap changes, held-out seeds and global implementation remain unauthorized.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees. Branch feat/mcp-audit-ratelimit (revision 4, ADR-037) needs its cloud PostgreSQL run, then the MCP server wiring (ADR-032 branch e). Main was at ab90268. Branch feat/physical-handoff prepares a transactional handoff and revision 3. Its cloud PostgreSQL run 41235442937 passed all 36 tests; complete trusted mission construction, occupancy ingestion, physical effects and worker integration. Branch feat/worker-daemon adds the polling loop and service adapter but still needs process integration and cloud verification. Ordinary completion denies declared handoff tasks; unmarked tasks remain ordinary. Branch test/e3-approved-main contains the maintainer-approved corpus labels but has not been pushed. Preserve T11 structural scoring semantics. Do not run E2/E3, held-out seeds, paid calls or global implementation without authorization. Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review.
```
