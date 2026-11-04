# Waggle Hive: Last context

Updated: 2026-11-04. PR 177 (`docs/readme-project`) incorporates origin/main
`a264b5b`, including PR 175 and PR 176. Resolved conflicts in LASTCONTEXT.md,
PENDING.md and docs/GOTCHAS.md by retaining the newer main audit, both task
records and both gotchas. Only documentation conflicts were edited. The
maintainer reviews and merges PRs.

Code progress of the project (estimate by eye, code only): 88% on 2026-11-04,
margin about 4 points, as reviewed in the previous main audit. This bounded
correctness fix is 100% written with tests; it does not justify a whole-point
increase. Experiments, calibration, documents and delivery are excluded.
G-GLOBAL and other unmerged worktrees remain outside the estimate.

## Current state

- Main includes PRs 163 to 174: viewer gallery and overlays, CourtRuntime and
  CrisisRuntime, organizer E5 C2/C3, SDK fake-backed client test, E8 export,
  E1 diagnosis, scripted E4 CLI and Meta Wonder planning-role routes.
- This branch corrects a false acceptance in validation/plan_rollout.py:
  robot contact flags do not include robot-pair separation. The rollout now
  reuses the independent detector's swept robot_robot_gap and existing margin,
  reporting SEPARATION_VIOLATION once per pair. No simulator experiment counters,
  fast-layer threshold, fencing, audit, MCP rule or trajectory was modified.

## Done last

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
status, branches and worktrees, and fetch origin. PR 177 (`docs/readme-project`)
now incorporates main a264b5b and resolves all three documentation conflicts.
Check its mergeability and cloud CI before the maintainer merges. Do not run
more tests for the README task; the maintainer explicitly stopped that work.
Project code remains about 88% plus/minus 4 points from the main audit; this
README task adds no product code. Preserve ADR-095 rollout separation semantics,
all pending tasks, both gotchas and all unmerged worktrees/assets. Do not duplicate
merged CourtRuntime, CrisisRuntime, SDK fake-backed test, E8 export or scripted
E4 runner. The example replay is historical and not a current resimulation pass.
Never merge docs/context-wave3. No paid call, held-out run, migration, secret access
or safety-threshold change is authorized by this handoff. Agents never merge PRs.
