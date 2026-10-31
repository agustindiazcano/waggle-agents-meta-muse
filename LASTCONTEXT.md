# Waggle Hive: Last context

Updated: 2026-10-31 (MCP chain and trusted state in stacked PRs 69 to 76).

## Done last
- Main is at `9ff7366`: PRs up to 68 merged (E3 approved labels, audit and rate limit with revision 4, MCP dispatcher). `index (1).html` remains untracked and untouched.
- PRs 69 to 76 are open and stacked, each verified by `uv run ci` and, where it adds SQL, by the cloud PostgreSQL workflow:

| PR | Branch | Adds | Cloud PostgreSQL |
|---|---|---|---|
| 69 | `feat/mcp-identity-store` | revision 5 `robot_identities`, `PostgresIdentityStore` (ADR-039) | 56 passed |
| 70 | `feat/mcp-forwarder` | `FencedForwarder` for `release_zone` and `get_task` (ADR-040) | none needed |
| 71 | `feat/trusted-occupancy` | revision 6 `trusted_tick`, `zone_occupancy`, `TrustedStateRepository` (ADR-041) | 66 passed |
| 72 | `feat/sim-occupancy-bridge` | `SimTrustedBridge` (ADR-042) | 68 passed |
| 73 | `feat/handoff-mission` | `HandoffFinisher`, `complete` argument in `run_once` and `serve_worker` (ADR-043) | 74 passed |
| 74 | `test/e2e-handoff-scenario` | simulator to handoff end-to-end test (ADR-044), not E2 | 76 passed |
| 75 | `feat/mcp-transport` | line transport, `tools/list`, `tools/call` (ADR-045) | none needed |
| 76 | `feat/mcp-handshake` | legacy `initialize` and per-request flow, `server/discover` (ADR-046) | none needed |

## Current state
- Estimated code progress about 34 percent by the equal-weight build order (30 before this batch); an estimate, not a measurement. Only E1 has run, on development seeds. E2 to E10, held-out seeds and paid calls have not run.
- The MCP server is not conformant until run against a real client. Eight of ten tools raise `ToolUnavailable`; the entry point `waggle.mcp_server.__main__` is still the placeholder. Nothing writes the trusted tick and occupancy tables in a running system except the simulator bridge in tests.
- `tools/pre_push_check.py` fails with a dirty tree because of the untracked `index (1).html`, so gitleaks has not run on the branches of PRs 67 to 76. The pushes were made after a green `uv run ci`.
- Local mock implementation, migrations, fencing, audit and MCP work were approved. Paid calls, secret or cap changes, held-out seeds and global implementation remain unauthorized.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees before touching a file. Main was at 9ff7366 (PRs up to 68 merged). PRs 69 to 76 are open and stacked in order (69 identity store on main, 70 forwarder, 71 trusted tick and occupancy, 72 simulator bridge, 73 handoff completion, 74 end-to-end scenario, 75 line transport, 76 handshake); check which merged and retarget or merge main into the next one; the maintainer merges. Update LASTCONTEXT.md and PENDING.md in one docs PR at the end of a batch, not on every branch, because that is where conflicts came from. Remaining work in this order: wire the MCP server entry point (database, token source, map extent, rate limit, trusted sources); real tool backends for the eight tools that raise ToolUnavailable; test the server against a real MCP client; the real guard and the E3 production entry points, preserving T11 structural scoring; then E2 only after explicit authorization. The handshake follows the 2025-11-25 and 2026-07-28 specification text but no real client was run, so do not call it conformant. Do not run E2/E3, held-out seeds, paid calls or global implementation without authorization. Migrations, fencing, audit and MCP work are authorized. Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review.
```
