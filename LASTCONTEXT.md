# Waggle Hive: Last context

Updated: 2026-11-01 (MCP backends, motion queue, guard adapter and first E3 runners).

## Done last
- `main` is at `6da4fef`: the chain of PRs 69 to 77 is in, but PRs 78 to 82 are not (they were merged into their stacked bases). Open PRs:

| PR | Branch | Base | Adds |
|---|---|---|---|
| 83 | `fix/ticket-insert-race` | `main` | everything of PRs 78 to 82 (entry point ADR-047, inventory ADR-048 revision 7, tickets and purchase orders ADR-049 revision 8, motion orders ADR-050 revision 9) plus a fix for a concurrent `open_ticket` race. Cloud PostgreSQL 102 passed, twice |
| 84 | `feat/sim-motion-consumer` | `fix/ticket-insert-race` | `MotionExecutor` (ADR-051): the simulator executes queued `move_waypoint` orders. Cloud 104 passed |
| 85 | `feat/guard-production` | `main` | `INCIDENT_TEXT` source, `LlmGuardClassifier` (`guard-v1`), `e3_eval`, runners for `mcp_identity` and `mcp_schema_bounds` (ADR-052, ADR-053) |

- All ten MCP tools have a backend. `dispatch_tech` records a request only. Motion tools queue orders; the server executes nothing. `pick_package` and `deliver_package` resolve `failed` in the simulator because it has no package model.
- The cloud run found a real race in `open_ticket` (ON CONFLICT on one index does not cover a second unique index). Fixed, with a ten-round race test, and recorded in `docs/GOTCHAS.md`.

## Current state
- Estimated progress about 26 percent on `main` and about 29 percent once PRs 83 to 85 merge, by the equal-weight build order in AGENTS.md section 18. An estimate, not a measurement. Only E1 has run, on development seeds. E2 to E10, held-out seeds and paid calls have not run.
- The MCP server follows the 2025-11-25 and 2026-07-28 specification text but no real client was run, so it is not claimed conformant.
- The guard prompt has been tested only with scripted providers. E3 has not run as an experiment; 7 of 25 cases have a runner, so a full run still raises `MissingLayer`.
- Nothing runs the MCP server and the simulator together, and no script provisions the catalog, machines, zones or identities.
- `index (1).html` is excluded locally through `.git/info/exclude`, so `pre_push_check` runs and gitleaks works. It did not run on the branches of PRs 67 to 77.
- Heredocs with several files in one Bash call failed twice in this environment; write files with the Write tool.
- Local mock implementation, migrations, fencing, audit and MCP work are authorized. Paid calls, secret or cap changes, held-out seeds, global implementation and E2 (see PENDING row 83) are not confirmed.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees before touching a file. Main was at 6da4fef. PR 83 (fix/ticket-insert-race, brings PRs 78 to 82 and a ticket race fix to main), PR 84 (feat/sim-motion-consumer, base fix/ticket-insert-race) and PR 85 (feat/guard-production, base main) are open; check which merged, retarget PR 84 to main after 83, and after the last merge verify git rev-list --count origin/main..origin/fix/ticket-insert-race is 0 (docs/GOTCHAS.md, stacked merges). The maintainer merges. Update LASTCONTEXT.md and PENDING.md in one docs PR at the end of a batch. Remaining work in this order: E3 runner for catalog_check on PostgreSQL in the cloud (E3-T3-02 is expected to be accepted because the catalog has no compatibility check; report it); the other E3 layers and production pieces (message schema, read-back, court prompt, planner schema and validator, untrusted-data boundary, fast layer), preserving T11 structural scoring; provisioning scripts for catalog, machines, zones and identities; a package model for pick_package and deliver_package after a design decision; a real MCP client test once the maintainer names the client. Do not call the MCP server conformant until a real client ran. Do not run E2/E3 as experiments, held-out seeds, paid calls (including a real run of the `guard-v1` prompt) or global implementation without explicit authorization; the maintainer wrote "estas autorizado y avanza" on 2026-11-01 and E2 stays unconfirmed (PENDING row 83), so ask in plain words. Migrations, fencing, audit and MCP work are authorized. Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review. Write files with the Write tool, not multi-file heredocs.
```
