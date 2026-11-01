# Waggle Hive: Last context

Updated: 2026-11-01 (PRs 83 to 88 merged; E3 catalog check runner; progress re-measured).

## Done last
- `main` is at `e783a94`. PRs 83, 85, 86, 87 and 88 are merged. PR 84 first went into `fix/ticket-insert-race` after PR 83, so its three commits were stranded; PR 87 carried them to `main`, and `git rev-list --count origin/main..origin/fix/ticket-insert-race` is 0.
- In `main` now: all ten MCP tools with a backend (ADR-047 to ADR-050), the `MotionExecutor` (ADR-051), the guard adapter and E3 evaluator pieces (ADR-052), runners for `mcp_identity` and `mcp_schema_bounds` (ADR-053), and the runner for `catalog_check` (ADR-054, PR 88).
- ADR-054: 10 of 25 E3 cases have a runner. Cloud PostgreSQL run 41264796674 passed 104 tests. E3-T3-02 (existing but incompatible part) is accepted by the catalog, which stores no compatibility; the runner reports it as a missed injection. Closing it needs a compatibility table and a design decision. `PART_FOR_CASE` is a fixture the maintainer has not reviewed.
- `dispatch_tech` records a request only. Motion tools queue orders. `pick_package` and `deliver_package` resolve `failed` in the simulator because it has no package model.

## Current state
- Progress measured on 2026-11-01 by phase of `PLAN.md`, weighted by effort (the weights are a judgment, not data): about 43 percent of the code implemented, about 31 percent by equal weight of the 7 blocks of AGENTS.md section 18, about 5 percent verified by experiments (only E1 ran, on development seeds, without held-out). The largest gaps are everything that needs an LLM (director, court E4, advisors E5, crisis planner E10), `waggle.validation` (does not exist), predictive maintenance physics and predictor, the viewer and multimodal.
- The MCP server follows the 2025-11-25 and 2026-07-28 specification text but no real client was run, so it is not claimed conformant.
- The guard prompt has been tested only with scripted providers. E3 has not run as an experiment; a full run still raises `MissingLayer` for the layers without a runner.
- Nothing runs the MCP server and the simulator together, and no script provisions the catalog, machines, zones or identities.
- `index (1).html` is excluded locally through `.git/info/exclude`, so `pre_push_check` runs and gitleaks works.
- Heredocs with several files, and heredocs inside `gh pr create`, failed in this environment; write files with the Write tool and use `--body-file`.
- Merging `main` into a stacked branch conflicts in `docs/DECISIONS.md` when ADR numbers overlap; keep both sides and order by number. Pull the remote tip of a branch before merging into it.
- Local mock implementation, migrations, fencing, audit and MCP work are authorized. Paid calls, secret or cap changes, held-out seeds, global implementation and E2 (PENDING row 83) are not confirmed. Two messages of the maintainer ("estas autorizado y avanza", "estas autorizado, hace lo recomendado") did not name E2 or the paid run, so they were read as permission to continue the build order only.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees before touching a file. Main was at e783a94 with PRs 83 to 88 merged. Remaining work in this order: the other E3 layers and production pieces (message schema, read-back, court prompt, planner schema and validator, untrusted-data boundary, fast layer), preserving T11 structural scoring and reporting any case a layer lets through; provisioning scripts for catalog, machines, zones and identities (data by scripts, never by migration); a package model for pick_package and deliver_package after a design decision; a compatibility table for the catalog only after a design decision (E3-T3-02); a real MCP client test once the maintainer names the client. Do not call the MCP server conformant until a real client ran. Do not run E2/E3 as experiments, held-out seeds, paid calls (including a real run of the `guard-v1` prompt) or global implementation without explicit authorization; E2 stays unconfirmed (PENDING row 83) and the maintainer did not name it, so ask in plain words. Migrations, fencing, audit and MCP work are authorized. Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review. For stacked PRs verify git rev-list --count origin/main..origin/<base-branch> is 0 after the last merge (docs/GOTCHAS.md). The maintainer merges. Update LASTCONTEXT.md and PENDING.md in one docs PR at the end of a batch. Write files with the Write tool, not multi-file heredocs, and use gh pr create --body-file.
```
