# Waggle Hive: Last context

Updated: 2026-11-01 (PR 89 merged; PRs 90 to 94 open: five E3 layer runners and the provisioning script).

## Done last
- `main` is at `4143771` (PR 89 merged). Five PRs are open against `main`, each from `main`, none merged yet. Merge in order 90, 91, 92, 93, 94 and merge `main` into each remaining branch after the one before it; `docs/DECISIONS.md` (ADR-055 to ADR-059) and `RUNNABLE_LAYERS` in `e3_eval.py` conflict, keep both sides ordered by number.

| PR | Branch | ADR | What |
|---|---|---|---|
| 90 | `feat/robot-message-schema` | 055 | `parse_robot_message` and the `message_schema` runner (E3-T5-02) |
| 91 | `feat/provision-scripts` | 056 | `uv run provision SPEC TOKENS_OUT` for catalog, machines, zones, identities. Cloud run 41324222263: 107 passed |
| 92 | `feat/voice-readback` | 057 | read-back and item resolution, runner for E3-T4-01 to 03 |
| 93 | `test/e3-untrusted-boundary` | 058 | runner for E3-T18-03 over `sanitize` and `fence` |
| 94 | `feat/plan-schema` | 059 | new package `waggle.validation`, `parse_plan`, runner for E3-T18-02, import contract `validation-no-llm-side` (touches `pyproject.toml`) |

- With all five merged, 16 of 25 E3 cases have a runner. Missing: `plan_validator` (T18-01, T18-04), `court_unanimity` (E3-T6-01, E3-T6-02, E3-T6-03; needs the production court prompt), `fast_layer` (E3-T2-02). A full E3 run still raises `MissingLayer` for them. E3 has not run as an experiment.
- New fixtures the maintainer has not reviewed: `ATTEMPTS` in `e3_readback.py`, `SOURCES` in `e3_boundary.py`, `BASE_PLAN` and `CONTEXT` in `e3_plan.py`, plus the older `ATTEMPTS` and `PART_FOR_CASE`.

## Current state
- The maintainer answered "todo autorizado" to the plain-words question about E2, and "segui avanzando, estas autorizado" after. E2 is therefore treated as authorized, but it was NOT run: the permission classifier of the session denied `gh workflow run e2.yml --ref main` (a shared resource). The only E2 part implemented is the S03 admission ablation on development seeds (`.github/workflows/e2.yml`). The full protocol (500 tasks, killed workers, database delay) has no harness yet.
- A real run of `guard-v1` is covered by "todo autorizado" in words but was not run: provider caps and balances (PENDING rows 4 and 5) are not verified, and a missing cap fails closed.
- The MCP server follows the 2025-11-25 and 2026-07-28 text but no real client ran, so it is not claimed conformant.
- Nothing runs the MCP server and the simulator together. Provisioning exists in PR 91 but the demo catalog, machines and zones come from the maintainer.
- `index (1).html` is excluded locally through `.git/info/exclude`.
- Heredocs with several files, and heredocs inside `gh pr create`, fail in this environment; write files with the Write tool and use `--body-file`.
- `uv run ci` takes longer than 400 s in the foreground on this machine now; run it in the background and wait.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md and relevant design documents. Inspect remote PRs, status, branches and worktrees before touching a file. Main was at 4143771 with PR 89 merged and PRs 90 to 94 open (message schema, provisioning, read-back, untrusted-data boundary runner, plan schema). If they are merged, check git rev-list --count origin/main..origin/<base> is 0 for any stacked branch and merge main into branches that remain, keeping both sides of docs/DECISIONS.md ordered by ADR number. Remaining work: dispatch the E2 admission workflow once the maintainer allows the action (authorized in words, denied by the session classifier) and report the result file; the plan validator (E3-T18-01 and 04) after a design decision between a minimal geofence validator and the full rollout validator; the court prompt and its E3 runner only after provider caps and balances are verified (PENDING rows 4 and 5); the fast layer runner; a package model for pick_package and deliver_package and a catalog compatibility table after design decisions (rows 92 and 95); a real MCP client test once the maintainer names the client (row 81). Do not call the MCP server conformant until a real client ran. Do not run held-out seeds, paid calls or global implementation without explicit authorization. Use tests first, task branches, reviewed diffs, required pre-push checks and human PR review. The maintainer merges. Update LASTCONTEXT.md and PENDING.md in one docs PR at the end of a batch. Write files with the Write tool, not multi-file heredocs, and use gh pr create --body-file.
```
