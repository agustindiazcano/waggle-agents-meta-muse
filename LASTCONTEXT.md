# Waggle Hive: Last context

Updated: 2026-11-02. `main` is at `ad46065` (PRs 131 and 132 merged). Open: PR 140 (integration of seven branches, see below) and the PRs it replaces: 133, 134, 135, 136, 137, 138, 139.

Code progress of the project (estimate by eye, code only): 75% on 2026-11-02 counting code written with a green CI even if not merged; about 66% measured on `main` today; it reaches 75% when PR 140 merges. Experiments and runs are not code and do not count. A judgment, not a result.

| Block | Code % | What is missing |
|---|---|---|
| E2 chaos harness, incl. handoff chaos S31 to S35 | ~97 | running it as an experiment (the maintainer dispatches `e2_chaos.yml`) |
| LLM HTTP providers (Meta, Baseten, Modal) | ~85 | Vertex, the voice endpoint, wiring `build_providers` where `LlmClient` is built, verified prices, the first real smoke run |
| Court and E4 | ~50 | live mode, real providers, the review set (labels are the maintainer's) |
| Voice path (voice-intent, E7 voice mock runner) | ~75 | real transcription provider, vision pipeline, UI |
| Package model | ~60 | registry table and forwarder check (revision 12, approved), MCP wiring |
| Catalog compatibility | revision 10 done | revision 11 (technician lease, ticket close, reservation settlement) not started |
| Advisors | ~65 | advisor runtime and prompt, E5 runner, database persistence of the log |
| Predictive maintenance | ~40 | alert loop, `failure_history`, E6 runner, synthetic failure log generator |
| Rollout validator (E10) | ~25 | rollouts, human variants, planner loop |
| Viewer | ~50 | map and zone drawing (needs geometry in the replay file, a decision), overlays, GLB models, live connection, a browser test |
| Replay generator | 100 | none |

What is left is mostly large blocks that need the schema (revisions 11 and 12), the real providers, or maintainer data.

## Done last
- PR 131 (the integration of the stacked chains) and PR 132 (`tools/list` filtered by chassis) are merged. Before that, stacked PRs had been merged into their base branches and never reached `main`; PR 131 brought them. Rule: merge a stack from the bottom, then retarget the next PR to `main` before merging it, and after each merge check that nothing is left out (`git rev-list --count origin/main..origin/<branch>` must be 0 for a branch that was meant to be merged).
- PR 140 integrates, in one merge, the work that was still open: catalog compatibility revision 10 and `ticket_id` on two MCP tools (PR 137), `Reason.ADVISOR` and the advisor bridge (PR 134), E2 handoff chaos (PR 135), voice-intent and attachments (PR 138), the replay generator (PR 139), the stdlib HTTP providers (PR 133) and ADR-062 (PR 136). Only `docs/DECISIONS.md` conflicted (each branch appended an ADR); the ADRs are now 062 to 065 and 070 to 073 in numeric order, none repeated. Full `uv run ci` with its real exit code and the cloud `postgres.yml` run are recorded in that PR.
- The maintainer adopted the recommended option of every design decision table (ADR-062). It does not cover paid calls, caps, held-out seeds, real data and labels.

## Where each agent left off
- Main agent: integration branch, then this context. Next: revision 11 and the package registry (they touch `schema.py`, so they wait until PR 140 is in `main`), then the maintenance alert loop.
- Providers agent (PR 133): standard library only, fail closed on a missing or invalid cap, key or URL; every price in `prices.toml` is unverified so real calls are refused. Not confirmed in the vendor documentation: Meta base URL and usage field names, Baseten auth header on the direct endpoint (if the first smoke test returns 401 check this first), Modal endpoint shape, the Vertex URL and OAuth (not implemented, a route to it fails closed), the voice batch endpoint. `build_providers(os.environ)` has no caller yet. `LlmClient` has its own retry (default one attempt) and the HTTP provider retries 429 and 5xx: do not set both without thinking, the attempts multiply.
- Handoff chaos agent (PR 135): kills are in-process exceptions, not operating system kills; S32 and S34 are controls; the "double repair starts" metric was replaced by "dependents claimed after a stale handoff" (the original text stays in `EXPERIMENTS.md`). Never run as an experiment.
- Voice agent (PR 138): confidence threshold 0.6, attachment limits and scene ticks are its own assumptions; all E7 cases are pending review; the runner measures the rule, not a model; the baseline without read-back gives 3 false accepts (V-04, V-06, V-08), the full pipeline 0.
- Replay agent (PR 139): done.

## What only the maintainer can do
Verify balances, expiry and limits in the provider consoles and set the caps (PENDING rows 4, 5, 10); verify model ids (row 7); fill `prices.toml`; add the provider keys as GitHub Actions secrets (row 11); dispatch `e2_chaos.yml` (start with 3 seeds); open the viewer (`cd web && npm ci && npm run dev`, open `?demo=1`; nobody has seen it in a browser) and decide whether the replay file carries the map geometry; supply the real parts, machines, zones, compatibility rows and recordings; label the E4 and E5 cases; review the fixtures below; define held-out seeds for the chaos harness; remove the worktrees (`../waggle-*`) after their PRs merge.

## Current state
- Fixtures the maintainer has not reviewed: `ATTEMPTS` in `e3_mcp_layers.py` and `e3_readback.py`, `PART_FOR_CASE`, `SOURCES` in `e3_boundary.py`, `BASE_PLAN` and `CONTEXT` in `e3_plan.py`, `PLANS` in `e3_plan_validator.py`, `HAZARD_READING`, `ODOMETRY`, `REQUEST` in `e3_fast_layer.py`, `SCRIPTS` in `e3_court.py`, and the voice cases.
- Untuned or assumed values: predictor parameters (PR 128 values were adjusted on simulator seeds that are no longer clean for E6), package pick radius and capacities, E2 tick rate (1000 per second), lease (400 ticks) and timings, voice confidence 0.6.
- Configuration D of E4 has no real cross-family route in `routes.toml`.
- The MCP server is not claimed conformant; no real client has run (PENDING row 81). `tools/list` is now filtered by chassis.
- The viewer dev server may still be running on port 5174 (port 5173 belongs to another project of the maintainer).
- `uv run ci` takes 4 to 20 minutes. Never pipe it through `tail`: the exit code you see is the one of `tail`. Use `uv run ci > file 2>&1; echo EXIT=$?`, run it alone (two suites at once can fail `test_markers.py` on a shared temporary directory), and treat GitHub as the authority. Database tests run only in the cloud: `gh workflow run postgres.yml --ref <branch>`. The pre-push hook needs a green `uv run ci` for the exact HEAD.
- Heredocs with several files fail here; use the Write tool and `gh pr create --body-file`.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md. First inspect the remote (git fetch --prune, gh pr list, git worktree list) and see what the maintainer merged. Code progress is about 75% counting unmerged work and about 66% on main; the table in LASTCONTEXT.md says what each block still needs. Do not rebuild what is in a PR: check PR 140 and the PRs 133 to 139 first. If PR 140 is merged, work from main; if it is not, branch from origin/chore/merge-wave-2 and target that branch. Stacking rule: a PR stacked on another branch must be retargeted to main with gh pr edit <n> --base main as soon as its base merges, and after every merge run git rev-list --count origin/main..origin/<branch> to confirm nothing was left out. Work that needs no new maintainer decision, in this order: (1) schema revision 11: technician lease at dispatch for a named technician, ticket close, reservation release and consumption (docs/CATALOG_COMPATIBILITY_DESIGN.md Part B); (2) revision 12: package id registry table and its check in the forwarder, foreign key later (docs/PACKAGE_MODEL_DESIGN.md branch 5); (3) the maintenance alert loop with failure_history and the E6 runner on the mock (docs/PREDICTIVE_MAINTENANCE_DESIGN.md); (4) wire build_providers(os.environ) where LlmClient is built, plus the llm_calls table, without making any real call; (5) rollout validator stage with one deterministic rollout (docs/ROLLOUT_VALIDATOR_DESIGN.md, belief-state variants as ADR-023 says); (6) advisor runtime on the scripted provider and the E5 runner; (7) the Python SDK client test of the MCP server (docs/MCP_CLIENT_TEST_DESIGN.md, a dev dependency stated in the PR). All migrations and the ticket_id change are approved by ADR-062; check the current revision first and never drop anything. Revisions 11 and 12 both touch src/waggle/db/schema.py, so do them one after the other, not in parallel. Work in parallel only on areas that do not share files: up to 3 subagents, each in its own git worktree and branch, tests first, each ending with a commit and a report; you review each diff, run uv run ruff check . and uv run ruff format --check ., run the full CI alone with its real exit code, push, open the PR with a short body and check gh pr checks: fix a red check before reporting. Do not change ACK, retry, fencing or audit logic. No paid call, no real provider call, no held-out seeds, no global implementation, and do not dispatch e2_chaos.yml: the maintainer does. Do not call the MCP server conformant. Ask the maintainer before using Antigravity for a task unless PENDING row 105 says otherwise. At the end estimate code progress by eye per block and for the project (code only; running experiments does not count), record it in PENDING.md and LASTCONTEXT.md in one docs PR, and give the next prompt. Write files with the Write tool, not multi-file heredocs.
```
