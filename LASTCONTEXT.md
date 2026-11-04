# Waggle Hive: Last context

Updated: 2026-11-04. Branch fix/rollout-separation-check in
../waggle-rollout-fast-control, based on origin/main 7b99bbf (PR 174).

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
git status, branches and worktrees, and fetch origin. Review
fix/rollout-separation-check in ../waggle-rollout-fast-control, based on main
7b99bbf. It fixes robot-pair proximity false accepts using the existing swept
geometry and unchanged separation margin (ADR-095). Tests reproduced the false
acceptance first; 30 rollout tests then passed. Check full CI and publishing
status before pushing or opening the PR. Project code remains about 88% plus/minus
4 points, a judgment; the bounded fix is 100%. Do not duplicate already merged
CourtRuntime, CrisisRuntime, SDK fake-backed test, E8 export or scripted E4 runner.
Preserve all unmerged worktrees and assets. Never merge docs/context-wave3.
No paid call, held-out run, migration or safety-threshold change is authorized
by this handoff. The maintainer reviews and merges PRs.
