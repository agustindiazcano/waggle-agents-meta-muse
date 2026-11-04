# Waggle Hive: Last context

Updated: 2026-11-04. This branch (`exp/e4-live-runner`, ADR-096) adds the live E4
court runner on real routes with fallbacks disabled, wiring `build_client` to
configurations A, B and C on the development split. Configuration D (cross-family)
and baseline are refused in live mode with `LiveConfigurationError`. Live runs verify
caps and model IDs fail-closed before any call, record realized model IDs and
fallback labels, and label result JSON as `provider_mode: "live"`. Tests first in
`tests/unit/experiments/test_e4_live.py` run in mock mode with zero network and
zero spend. The maintainer merges the PR, not the agent.

Code progress of the project (estimate by eye, code only): 88% on 2026-11-04,
margin about 3 points. Main now includes PR 163 to PR 174 (viewer gallery and overlays,
CourtRuntime and CrisisRuntime, organizer E5 C2/C3, SDK fake-backed client test, E8 export,
E1 diagnosis, scripted E4 CLI and Meta Wonder planning-role routes) and rollout separation check
(ADR-095). This branch (`exp/e4-live-runner`, ADR-096) implements the live E4 runner, raising
court/E4 code from 50% to about 95%. Measurements, calibration, documents and delivery do not
count. No new published number or README result changed.

## Current state

- E4 live runner is implemented on branch `exp/e4-live-runner` (ADR-096).
  Supports configurations A, B and C. Refuses D (until a non-Muse route exists)
  and baseline. Validates environment caps and model IDs before calling. Records
  live warning, realized model IDs and call log records. Fallbacks are disabled.
  Local unit tests pass in mock mode.
- Crisis planner adapter (ADR-090, PR 165), organizer E5 (ADR-091, PR 166) and
  Meta Wonder planning routes (ADR-094, PR 174) are in main. E10 harness and
  production crisis caller remain.
- Viewer map geometry, overlays and live stream parser are on `feat/viewer-overlays`
  (ADR-093).
- LLM provider/logging code is about 93%; court/E4 95%; voice/vision 75%; package
  model 75%; catalog/technician lease 90%; advisors/E5 95%; maintenance/E6 80%;
  rollout/crisis 90%; E2 harness 97%; replay generator 100%. Estimates by eye only.
- Provider balances, caps, secrets, labels, catalog, zones and recordings still
  require the maintainer. G-GLOBAL remains unauthorized, outside the denominator.

## Done last

- Live E4 court runner (ADR-096, this branch `exp/e4-live-runner`):
  Failing unit tests first in `tests/unit/experiments/test_e4_live.py` covering
  live result labeling, realized model IDs, rejection escalation, refusal of
  cross-family D and baseline, unauthorized held-out refusal, CLI `--live` execution,
  fail-closed missing caps and missing model IDs, and fallbacks disabled on provider
  outage.
  Implemented `run_case_live` and `run_e4_live` in `src/waggle/experiments/e4_harness.py`,
  `LIVE_PROVIDER_MODE` and live warning in `e4_result.py`, `--live` mutually exclusive
  CLI mode and `run_live` in `e4_run.py`.
  All 13 live and CLI unit tests pass in under 2 seconds. `test_style.py`, ruff,
  mypy --strict, and import-linter pass cleanly.

## Preserved work and assets

- Preserve dirty global-custody, Meshy and GLB worktrees and all unmerged work.
  Preserve C:/Users/agusd/.codex/artifacts/waggle-viewer-models-20261104.zip;
  binaries are ignored and imported using web/models.json. Viewer port is 5174,
  gallery URL uses ?gallery=1. Port 5173 belongs to another project.
- Never merge docs/context-wave3: its endpoint diff deletes thousands of lines.
  Remote branch deletion is the maintainer's. Ticket race patch d11c7c5 is
  already represented by 8ae51e3 on main; feat/maintenance-tickets needs no PR.
- Earlier viewer local browser validation lacked Chromium 1248; do not describe
  that local run as passed. Earlier validation notes remain in
  ../waggle-validation-156-163. No asset worktree or unmerged branch was removed.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md first, inspect
git status, branches and worktrees, and fetch origin. The live E4 court runner is
complete on branch exp/e4-live-runner (ADR-096) with 13 unit tests passing in mock
mode without spending. Review the PR and its CI. The next priority is E10 live harness
and production crisis caller, or running the live E4 cloud workflow once the smoke run
reports green on declared routes. Project code is about 88% plus/minus 3 points,
court/E4 about 95%. No paid call, held-out run, migration or safety change is authorized
without explicit maintainer authorization. Never merge docs/context-wave3 or delete
another agent's work.
