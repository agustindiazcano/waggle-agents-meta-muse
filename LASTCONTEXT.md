# Waggle Hive: Last context

Updated: 2026-11-02 (`main` at `7633f68`, PRs 90 to 108 merged; PRs 109 to 130 open, none of the code below is on `main`).

Code progress of the project (estimate by eye, code only): 65% on 2026-11-02, counting code written with a green CI even if not merged. Measured on `main` it is still 49%. Experiments and runs are not code and do not count. A judgment, not a result. Per block: E2 chaos harness about 95%, court (E4) about 50% (scripted court, E3 runner, E4 harness; live mode and real providers missing), package model about 60%, viewer about 45% (frame export, replay-verify, API stream, web viewer v0; overlays, map drawing and models missing), rollout validator about 25% (counterexamples and path compiler; rollouts, human variants and planner loop missing), advisors about 40% (everything that needs no fast-layer change), predictive maintenance about 40% (degradation, telemetry, predictor, scoring; alert loop, tables and E6 runner missing). What is left is large blocks plus everything that waits for maintainer decisions (PENDING rows 103 to 106).

## Done last
- PRs 106 to 108 merged (fault schedule, package model design, catalog and technician lease design). Since then, 22 PRs opened: the E2 chaos harness is complete and passed its cloud check (112 and 113 tests in `postgres.yml` runs 41374769611 and 41377834274); scripted court with the E3 `court_unanimity` runner and the E4 harness; package model core; frame export, `replay-verify`, web viewer v0 and the read-only API stream; validator counterexamples and path compiler; advisors core; predictive maintenance model and predictor; eight design documents.
- Antigravity worked for web research and for one code draft (PR 115, reviewed and lint-fixed by the main agent). Subagents wrote the rest in separate worktrees, tests first; the main agent reviewed each diff and ran a clean `uv run ci` before each push.

## Open PRs and the order to merge them
Stacked PRs target the branch below them; after a base merges and its branch is deleted GitHub retargets the child to `main`.

| Chain | Merge in this order |
|---|---|
| E2 chaos harness | 115 (hooks), 117 (baseline, import contract), 119 (worker loop), 120 (runner; carries 117), 121 (sweep and `e2_chaos.yml`) |
| Court and E3/E4 | 109 (design), 123 (scripted court and E3 `court_unanimity`), 129 (E4 harness) |
| Viewer | 114 (design), 122 (frame export, `replay-verify`), 126 (web viewer v0), 130 (read-only API stream) |
| Validator | 110 (design), 125 (counterexamples, path compiler) |
| Advisors | 112 (design), 127 (caution vocabulary, input, log, limits) |
| Maintenance | 113 (design), 128 (degradation, telemetry, predictor) |
| Alone | 124 (package model core), 116 (MCP client test design), 111 (Antigravity headless notes), 118 (this context, merge last) |

Expect one-line conflicts in `pyproject.toml` (the `control-no-ground-truth` list and the contracts) and in `tests/unit/test_sim_package_layout.py` between 122, 124 and 128, and in `pyproject.toml` between 128 and 130. Resolve by keeping both additions.

## Things to read before trusting the code
- PR 126 (web viewer): nobody opened it in a browser. Run `cd web && npm ci && npm run dev` and open `?demo=1`.
- PR 128 (predictor): the predictor values were adjusted while looking at simulator runs on a few seeds. They are untuned placeholders and those simulator seeds are not clean evaluation seeds for E6.
- PR 129 (E4 harness): configuration D has no real non-Muse route in `routes.toml`, so a scripted run of D measures nothing across families.
- PR 125 (validator): the feedback names a node by its position in the plan, not by its label, to keep attacker text out of the planner message. Confirm or revert.
- PR 123: fixtures `SCRIPTS` and the task in `e3_court.py` are the author's assumptions, not reviewed.
- PR 120 and 121: the E2 runner passed its cloud check on a small case (12 tasks, 2 processes). No development sweep has run; the maintainer dispatches `e2_chaos.yml`.
- PR 124 (packages): pick radius 1.0 m, speed bound 0.1 m/s and capacities are assumptions.

## Current state
- E2: decisions of `docs/E2_CHAOS_DESIGN.md` accepted on 2026-11-01 ("hace lo recomendado"). Tick rate (1000 per second), lease (400 ticks) and timings are assumptions to calibrate. Held-out seeds of this harness are not defined.
- Not approved, so not built (PENDING rows 103 to 106): any migration (catalog compatibility, technician lease, ticket close, package registry, failure history), the `ticket_id` change on two MCP tools, filtering `tools/list` by chassis, the fast-layer interface change for advisors (`Reason.ADVISOR`), the real MCP client choice (row 81), provider caps and balances (rows 4 and 5), the HTTP client dependency (row 9).
- Missing and blocked by those: the maintenance alert loop and E6 runner, the advisor bridge to the fast layer and the E5 runner, the live court and E4 on real providers, the package registry and MCP wiring, voice and vision, the full rollout validator with humans.
- Fixtures the maintainer has not reviewed: `ATTEMPTS` in `e3_mcp_layers.py` and `e3_readback.py`, `PART_FOR_CASE`, `SOURCES` in `e3_boundary.py`, `BASE_PLAN` and `CONTEXT` in `e3_plan.py`, `PLANS` in `e3_plan_validator.py`, `HAZARD_READING`, `ODOMETRY`, `REQUEST` in `e3_fast_layer.py`, and `SCRIPTS` in `e3_court.py`.
- The MCP server is not claimed conformant. `tools/list` returns every tool to every chassis.
- `index (1).html` is excluded locally through `.git/info/exclude`. Many worktrees exist beside the repository (`../waggle-*`); remove each with `git worktree remove` after its PR merges and check for unmerged work first.
- Running several `uv run ci` at once on this machine can cause a spurious failure (a shared temporary directory in `test_markers.py`). Rerun it alone before believing it. Database tests run only in the cloud: `gh workflow run postgres.yml --ref <branch>`.
- Antigravity (`agy`) works for web research with the wording "use only your web search tool" and for write-only drafts; check `finished_reason`. Headless runs cannot run commands. CEGIS stays unconfirmed (PENDING row 28).
- Heredocs with several files fail here; use the Write tool and `gh pr create --body-file`. `uv run ci` takes 6 to 9 minutes; run it in the background.

## Prompt for the next session
```
Continue Waggle Hive. Time is short (delivery from Nov 3 morning). Read AGENTS.md, LASTCONTEXT.md and PENDING.md. Inspect remote PRs, status, branches and worktrees first (git fetch, gh pr list, git worktree list) and see which of the PRs 109 to 130 the maintainer merged. If some were merged, resolve the expected one-line conflicts in pyproject.toml and tests/unit/test_sim_package_layout.py on the open branches (keep both additions), then continue. Work that needs no maintainer approval and is not yet done: (1) E2 handoff chaos S31 to S35 with its own no-fencing baseline (docs/E2_CHAOS_DESIGN.md branch 6, cloud tests via gh workflow run postgres.yml --ref <branch>); (2) rollout validator stage with one deterministic rollout, only the parts that do not need the ground-truth-versus-belief-state decision of docs/ROLLOUT_VALIDATOR_DESIGN.md; (3) web viewer: draw the map and zones once the maintainer decides to put geometry in the replay file, otherwise the overlays that need no new data; (4) multimodal: the closed voice-intent schema and pipeline on the mock provider (docs/MULTIMODAL_AND_VIEWER_DESIGN.md branches 6 to 8), which needs image and audio fields in the LLM request type; (5) a replay-file generator script and a decision note (docs/DECISIONS.md) for waggle.replay and waggle.api. If the maintainer answered the decisions tables or PENDING row 106, take the matching blocks first: catalog compatibility and technician lease, package registry, tools/list filtering, the advisor-to-fast-layer bridge, the maintenance alert loop. Work in parallel: up to 3 subagents per round, each in its own git worktree and branch (stack on the unmerged branch it depends on), tests first, mock providers only, each ends with a commit and a short report; you review each diff, run uv run ruff check . and uv run ruff format --check ., run uv run ci once per round in the background and alone, then push and open PRs with short bodies (gh pr create --base <previous-branch> --body-file). Do not change ACK, retry, fencing or audit logic. A migration, the ticket_id change, tools/list filtering and the fast-layer interface change need explicit maintainer approval (AGENTS.md section 15). No held-out seeds, paid calls or global implementation without explicit authorization. Do not call the MCP server conformant. Ask the maintainer before using Antigravity for a task unless PENDING row 105 says otherwise. At the end estimate code progress by eye per task and for the project, code only (experiments and runs do not count), record it in PENDING.md and LASTCONTEXT.md in one docs PR, and give the next prompt. Write files with the Write tool, not multi-file heredocs.
```
