# Waggle Hive: Last context

Updated: 2026-10-30 (session handoff after Phase 1).

## Done last
- Phase 1 is on `main` (PR 16): push guard and pre-push check (B0), conventions and the crisis replanning design (B1, B2, ADR-021 to ADR-025), and the simulator: sim core, robots, humans, exact detector, lidar, scenarios S01 to S18, fixed seeds, replay by seed (B3 to B8). Details of each branch are in `docs/PHASE1_BRIEF.md` and the merged PRs 5 to 14.
- No-control baseline on development seeds, 90 runs (`results/e1/dev/no_control_20261030T022921Z.json`): 107 human collisions, 1027 robot collisions, 125 separation violations, 218 near misses, 0 unavoidable cases. Held-out seeds were not run.
- Measured on this machine (`results/e8/dev/`): a 10-robot, 4-human rollout of 45 s simulated costs 22.3 s with lidar (core and detector about 8.7 s, lidar about 10.5 s). This is the open STOP POINT (PENDING 31).
- Rules added: AGENTS.md section 18 (contingency order and gates), section 3 rules 8 to 11 (cloud first).

## Current state
- `main` has B0 to B8. This handoff branch also carries the cloud-first rules of AGENTS.md section 3, which PR 17 merged into a stacked branch and never reached `main`. The trap is recorded in `docs/GOTCHAS.md` (merge a stacked chain from the top, or retarget each PR to `main`).
- The guard allows only `git push [-u] origin <type/short-description>` and gates push and `gh pr create` on the pre-push check, which still needs a local green `uv run ci` on HEAD (PENDING 30). A full local `uv run ci` takes 2 to 3 minutes.
- Open maintainer decisions: PENDING 31 (rollout cost), 30 (cloud gate and workflow), 29 (E9 undefined), 26 (viewer dependencies), 25 (gates G1 to G4).

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md (note section 3: cloud first), then LASTCONTEXT.md and PENDING.md, then PLAN.md Phase 2, docs/ARCHITECTURE.md (Fast layer, Sensing and prediction, Occlusion-aware speed cap), docs/DECISIONS.md (ADR-018, ADR-021, ADR-024, ADR-025), docs/EXPERIMENTS.md E1. Run git status, git branch and git worktree list. If two documents conflict, stop and ask.

State: Phase 1 (simulator, detector, lidar, scenarios S01 to S18, fixed seeds, no-control baseline on development seeds) is on main. Pushing a task branch and opening a PR is allowed. Never merge. Merge order matters: PRs stacked on a branch must be retargeted to main before they are merged, otherwise the work does not reach main.

Task, Phase 2 part 1 (stacked branches, tests first, show the failing run before implementing, Conventional Commits split by concern):
1. chore/e1-cloud-workflow: a workflow_dispatch workflow that runs the E1 development baseline and the speed measurement in the cloud and uploads the result JSON as an artifact (PENDING 30). From now on, long runs go there. Do not edit tools/hooks/.
2. feat/control-envelope: waggle.control, which reads only waggle.sim.observations and waggle.sim.params (the import contract enforces it). Stopping distance S_stop = v*t_r + v^2/(2a) and separation S_sep from ADR-024 for the swept curvilinear footprint, speed cap that can only reduce motion, e-stop, heartbeat watchdog, hazard geofence. Pure functions of their inputs. Fail closed on a missing or stale scan.
3. feat/control-occlusion-cap: the occlusion-aware speed cap from the lidar scan (ADR-024), edge cases as documented (no non-negative root gives zero, minimum speed floor).
4. feat/control-cpa-prediction: constant-velocity closest-point-of-approach predictor on lidar detections, can only restrict (ADR-018).
5. E1 on development seeds only, configurations: no control (already done), radial 1D distance, swept footprint, swept footprint plus occlusion cap, plus CPA prediction. Counts with Wilson 95 percent intervals, near misses, false stops, throughput, loop latency as code latency. Run it in the cloud workflow. Do not run held-out seeds.

Constraints: numpy and the standard library only, no new runtime dependency. Do not touch the fencing check, MCP boundary or audit logic. Never loosen a safety check to make a result pass. If a layer does not help, the README says so. Keep control deterministic (the determinism scan covers waggle.control).

Do not start Phase 5C or the viewer: they wait for the maintainer decisions PENDING 31 (rollout cost) and 26 (viewer dependencies). Ask before choosing between the rollout cost options. After each branch: uv run ci, update LASTCONTEXT.md and PENDING.md, push, open the PR. Report every two branches in five lines: done, next, blockers.
```
