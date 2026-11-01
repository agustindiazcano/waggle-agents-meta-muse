# Waggle Hive: Last context

Updated: 2026-11-01 (PRs 90 to 97 merged into `main`; PR 97 carried the stranded PR 96).

Code progress of the project (estimate by eye, code only): 46% on 2026-11-01. Unchanged since the last record; this batch only merged work. A judgment, not a result. The E3 corpus has 19 of 25 cases with a runner in code, all on `main` (PR 99 added the fast layer). E2 is 25% (S03 admission component only). Verified by experiments is still about 5%: E1 on development seeds is the only experiment that ran.

## Done last
- `main` is at `6065690` (PR 95 merged). PRs 90, 91, 92, 93, 94 and 95 are merged. `main` was merged into each branch before it merged; conflicts were in `docs/DECISIONS.md` (ADR-055 to ADR-060), `RUNNABLE_LAYERS` in `e3_eval.py` and `test_e3_mcp_layers.py`.
- PR 95 failed `ruff` once (E501 in `tests/unit/test_docs_content.py`); fixed in `724a943`. Run `uv run ruff check .` and `uv run ruff format --check .` before each push.
- PR 96 (geofence check, ADR-060, runner `plan_validator`) was merged into its base `feat/plan-schema` after PR 94 had merged, so it missed `main`. PR 97 (`feat/plan-schema` to `main`) fixed it; `git rev-list --count origin/main..origin/feat/plan-schema` is 0. This is the stacked-merge trap in `docs/GOTCHAS.md`.
- The five temporary worktrees (`waggle-provision`, `waggle-readback`, `waggle-boundary`, `waggle-plan`, `waggle-geofence`) and their local branches were removed. Other old worktrees remain (19 listed); check each for unmerged work before removing.

## Current state
- The maintainer answered "todo autorizado" to the plain-words question about E2, and "segui avanzando, estas autorizado" after. E2 is treated as authorized, but it was NOT run: the permission classifier of the session denied `gh workflow run e2.yml --ref main` (a shared resource). The maintainer can run it with `! gh workflow run e2.yml --ref main`. The only E2 part implemented is the S03 admission ablation on development seeds (`.github/workflows/e2.yml`). The full protocol (500 tasks, killed workers, database delay) has no harness yet.
- A real run of `guard-v1` is covered by "todo autorizado" in words but was not run: provider caps and balances (PENDING rows 4 and 5) are not verified, and a missing cap fails closed.
- Missing E3 runner: `court_unanimity` (E3-T6-01 to 03, needs the production court prompt). A full E3 run still raises `MissingLayer` for it. The `fast_layer` runner (ADR-061) is on `main`; its fixture needs maintainer review.
- The full E2 chaos harness is designed in `docs/E2_CHAOS_DESIGN.md` (proposed, nothing implemented). Five decisions wait on the maintainer; the build order is six branches. E3 has not run as an experiment.
- The maintainer has not reviewed the new fixtures: `ATTEMPTS` in `e3_readback.py`, `SOURCES` in `e3_boundary.py`, `BASE_PLAN` and `CONTEXT` in `e3_plan.py`, `PLANS` in `e3_plan_validator.py`, plus the older `ATTEMPTS` and `PART_FOR_CASE`.
- The MCP server follows the 2025-11-25 and 2026-07-28 text but no real client ran, so it is not claimed conformant.
- Nothing runs the MCP server and the simulator together. The demo catalog, machines and zones come from the maintainer (provisioning exists).
- `index (1).html` is excluded locally through `.git/info/exclude`.
- Heredocs with several files, and heredocs inside `gh pr create`, fail in this environment; write files with the Write tool and use `--body-file`.
- `uv run ci` takes longer than 400 s in the foreground on this machine; run it in the background and wait.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees before touching a file. Main was at cd12dc3 with PRs 90 to 97 merged (PR 97 carried the geofence check, PR 96). Remaining work: dispatch the E2 admission workflow once the maintainer runs or allows it (authorized in words, denied by the session classifier) and report the result file, then design the full E2 chaos harness; the court prompt and its E3 runner only after provider caps and balances are verified (PENDING rows 4 and 5); the full rollout validator of Phase 5C after a design decision (row 99); a package model for pick_package and deliver_package and a catalog compatibility table after design decisions (rows 92 and 95); a real MCP client test once the maintainer names the client (row 81). Do not call the MCP server conformant until a real client ran. Do not run held-out seeds, paid calls or global implementation (docs/MULTI_WAREHOUSE_PLAN.md, gated by G-GLOBAL) without explicit authorization. Before each push run uv run ruff check . and uv run ruff format --check . plus the tests you touched; run uv run ci in the background and wait. At the end of each task estimate code progress by eye as a percent per task and for the whole project (code only), and record it in PENDING.md (Code % column and the total at the top) and in LASTCONTEXT.md (AGENTS.md section 17). Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review. The maintainer merges. Update LASTCONTEXT.md and PENDING.md in one docs PR at the end of a batch. Write files with the Write tool, not multi-file heredocs, and use gh pr create --body-file.
```
