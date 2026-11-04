# Waggle Hive: Last context

Updated: 2026-11-04. PR 178 (`exp/e4-live-runner`, ADR-096) incorporates
main 54aa19e, including merged PRs 175, 176 and 177. Resolved documentation
conflicts, preserving the main audit, live E4 status, README and rollout task
records, and both warning entries. The maintainer reviews and merges PRs.

Code progress of the project (estimate by eye, code only): 88% on 2026-11-04,
margin about 4 points, as reviewed in the previous main audit. Live E4 code
is estimated at 95% on PR 178;
real evaluation remains pending. This documentation resolution adds no code
and does not change the project estimate; task Code % is -. Experiments,
calibration, documents and delivery are excluded.
G-GLOBAL and other unmerged worktrees remain outside the estimate.

## Current state

- PR 178 implements live E4 A/B/C through build_client with fallbacks disabled
  (ADR-096). Live mode refuses baseline and D until a verified non-Muse route
  exists. Caps/model IDs are checked before calls. Results record provider mode,
  realized model IDs and fallback labels. Local tests use mocks with no spend.

- Main includes PRs 163 to 174: viewer gallery and overlays, CourtRuntime and
  CrisisRuntime, organizer E5 C2/C3, SDK fake-backed client test, E8 export,
  E1 diagnosis, scripted E4 CLI and Meta Wonder planning-role routes.
- Merged PR 176 corrects a false acceptance in validation/plan_rollout.py:
  robot contact flags do not include robot-pair separation. The rollout now
  reuses the independent detector's swept robot_robot_gap and existing margin,
  reporting SEPARATION_VIOLATION once per pair. No simulator experiment counters,
  fast-layer threshold, fencing, audit, MCP rule or trajectory was modified.

## Done last

- Resolved PR 178 conflicts against main 54aa19e. Only documentation was edited.
  Focused E4, CLI, style and documentation consistency checks passed: 55 tests
  in 8.91s using the existing environment after a new environment hit disk
  capacity. No paid call or result change. Full regression runs in cloud CI.
- PR 178 previously reported 36 focused E4/CLI/style tests passing, with failure
  coverage for missing caps/model IDs, provider outages, rejected configurations,
  held-out refusal, escalation and result labels. This is mock-backed evidence.

- Rewrote README in PR 177 with the project workflow, implementation status,
  model roles, development results and hackathon requirement/evidence matrix.
  Accepted participant rules and final delivery checks are not claimed complete.
- Preserved the main rollout fix and audit below while resolving PR 177 conflicts.
  PENDING.md keeps rollout task 130 and README task 131. Both GOTCHAS entries remain.
- No further tests were run, as requested by the maintainer for this README task.
  Earlier documentation checks passed 181 tests; lint and strict types passed.
  Full local CI was interrupted. The historical demo replay passed digest-only
  verification but differed at tick 4 on full resimulation; its fixture is unchanged.

- Tests first: 3 failed and 2 passed on the new proximity cases before the fix.
  Afterwards the rollout test file passed 30 tests; focused strict Mypy passed.
  ADR-095 records semantics; GOTCHAS records the detector flag trap.
- Still pending: E1 residual failures, E2 full chaos evaluation/physical wiring,
  E4 real evaluation and Vertex, E10 harness/execution, live safety overlay data,
  E6 production, real voice/vision, package integrity and E9 mutation arm.
- No paid call, held-out run, migration, secret access or dependency addition.
  See the PR test plan for the full gate and publishing status.

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
status, branches and worktrees, and fetch origin. PR 178 (`exp/e4-live-runner`)
incorporates main 54aa19e, including merged PR 177, with documentation conflicts
resolved. Check mergeability and cloud CI before maintainer review. Live E4
A/B/C exists (ADR-096); D needs a verified non-Muse route. Real E4 evaluation,
E10 harness and production crisis wiring remain pending. Project code remains
about 88% plus/minus 4 points; court/E4 about 95%, estimated by eye. Preserve
ADR-095 rollout semantics, all pending tasks, warnings and unmerged worktrees.
Do not resume the stopped README tests. The replay fixture is historical and
not a current resimulation pass. Never merge docs/context-wave3. No paid call,
held-out run, migration, secret access or safety threshold change is authorized
by this handoff. Agents never merge PRs.
