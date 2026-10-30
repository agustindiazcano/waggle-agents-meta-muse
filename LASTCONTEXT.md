# Waggle Hive: Last context

Updated: 2026-10-30 (context sync after B10 merged, viewer mockup noted).

## Done last
- B11 `docs/phase2-design` merged (PR 23): ADR-026 perception and tracking, ADR-027 control interface and limit arbitration, ADR-028 E1 metrics and the eight configurations, control module layout in ARCHITECTURE.md, branches B11 to B17 in PLAN.md. Assumptions in the ADRs are not calibrated. Next: B12 `feat/control-envelope`.
- B10 `feat/sim-performance` (stacked on B9): contact episodes already counted as episodes (tests and ADR-021 text added, no result changed). `waggle.sim.hullgap` (batched exact detector), `fastlidar` (cached static ranges, exact dynamic hits), `rollout` (parallel variants). E1 no-control dev baseline identical on 90 runs (counts and final hashes). Speed 3.1x measured, below the 5x minimum: stopped, PENDING 31. Profiles and before/after in `results/e8/dev/`. Next: B11 `docs/phase2-design` after the maintainer decides.
- B9 `chore/guard-gaps-and-rules` (session brief 2, based on origin/main because the old stack is merged): guard denies git remote add, set-url and remove, gh api write methods, gh repo, secret, auth and release writes, and interpreter one-liners that spell out git push, git remote or gh api; 2>&1 and head or tail pipes no longer block an allowed push. AGENTS.md git rule 3 reworded (A3). `uv run ci` takes 1 min 46 s, so no test needed the heavy marker (A4, ADR-029). E9 defined (A5). Next: B10 `feat/sim-performance`, stop point after it.
- Phase 1 is on `main` (PR 16): push guard and pre-push check (B0), conventions and the crisis replanning design (B1, B2, ADR-021 to ADR-025), and the simulator: sim core, robots, humans, exact detector, lidar, scenarios S01 to S18, fixed seeds, replay by seed (B3 to B8). Details of each branch are in `docs/PHASE1_BRIEF.md` and the merged PRs 5 to 14.
- No-control baseline on development seeds, 90 runs (`results/e1/dev/no_control_20261030T022921Z.json`): 107 human collisions, 1027 robot collisions, 125 separation violations, 218 near misses, 0 unavoidable cases. Held-out seeds were not run.
- Measured on this machine (`results/e8/dev/`): a 10-robot, 4-human rollout of 45 s simulated costs 22.3 s with lidar (core and detector about 8.7 s, lidar about 10.5 s). This is the open STOP POINT (PENDING 31).
- Rules added: AGENTS.md section 18 (contingency order and gates), section 3 rules 8 to 11 (cloud first).

## Current state
- Maintainer decision 2026-10-30: continue with B11 to B17 first (contingency order, G2 is Oct 31), then MCP, guard, court and advisors. The viewer mockup waits for the real logic.
- `main` has B0 to B8. This handoff branch also carries the cloud-first rules of AGENTS.md section 3, which PR 17 merged into a stacked branch and never reached `main`. The trap is recorded in `docs/GOTCHAS.md` (merge a stacked chain from the top, or retarget each PR to `main`).
- The guard allows only `git push [-u] origin <type/short-description>` and gates push and `gh pr create` on the pre-push check, which still needs a local green `uv run ci` on HEAD (PENDING 30). A full local `uv run ci` takes 2 to 3 minutes.
- Open maintainer decisions: PENDING 31 (rollout cost), 30 (cloud gate and workflow), 29 (E9 undefined), 26 (viewer dependencies), 25 (gates G1 to G4).

## Prompt for the next session
```
Continue Waggle Hive, session brief 2, from B12. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/PHASE1_BRIEF.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-021 to ADR-029), docs/EXPERIMENTS.md. Run git fetch, git status, git branch -r, git worktree list, gh pr list.

State: B9 (PR 19) and B10 (PR 22, retarget of 20) are merged into main, with PR 21. Base B12 on origin/main. Never merge, never push to main, no force push. The viewer mockup `index (1).html` is untracked and stays as is (PENDING 33): do not commit it and do not work on the viewer.
Decision taken (ADR-025 addendum, PENDING 31): rollout cost accepted at about 5.7 s per 45 s rollout (K = 5, H = 45 s, lidar every 4 ticks), variants for E10 and held-out runs go to the cloud, live-demo reductions are labeled, no more optimization now.

Task, in order, tests first with the failing run shown, Conventional Commits, uv run ci green and gitleaks clean before each push, report every two branches in five lines (done, next, blockers):
B11 is done and merged (PR 23). The design to implement is in ADR-026 to ADR-028 and the control module layout of ARCHITECTURE.md.
B12 feat/control-envelope, B13 feat/control-tracking, B14 feat/control-occlusion, B15 feat/control-cpa, B16 feat/control-reflex, B17 feat/e1-harness (development seeds only, eight configurations, uv run report).
Stop after B17 and report the E1 development results with the tables. Do not start B18 until the maintainer says so.

Constraints: numpy and the standard library only. waggle.control reads only waggle.sim.observations and waggle.sim.params. Pure functions with explicit state, deterministic, fail closed on a missing or stale scan. Never loosen a safety check. Ask before touching the fencing check, the MCP boundary, the audit logic or the .env. No paid API call in this session.
Reminder: long or paid runs go to the cloud workflow. Rollout timings on this machine vary by 40 percent, so compare only alternating runs in one session.
```
