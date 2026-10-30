# Waggle Hive: Last context

Updated: 2026-10-29 (rule change on chore/agents-push-and-pr).

## Done last
- B5 `feat/sim-humans`: `waggle.sim.humans` (scripted paths, seeded walkers that turn away from walls and racks, adversarial step-out, crossing and stop-in-aisle plans whose start tick comes only from the declared robot parameters and a fraction in [0.5, 1.5] drawn from the seed, hidden-human sampling with the ADR-023 rejection rule). Constants HUMAN_RADIUS 0.30 m and HUMAN_WALK_SPEED 1.4 m/s are assumptions in params.
- B4 `feat/sim-robots`: `waggle.sim.robots` (RobotFleet: actuation delay ring buffer, speed and turn limits, bicycle model for the forklift, differential drive for the others, load_raised, oriented footprints, swept footprint polygons). Stopping distance bound v*dt/2 + a*dt^2/2 derived in ADR-021; observed error reaches 98 percent of it, so the test is not vacuous. A 2.4 m aisle corner: forklift strays 0.73 m against 0.65 m allowed, carrier 0.375 m against 0.8 m.
- B3 `feat/sim-core`: waggle.sim.params and observations (leaf modules), world model with JSON loader, state arrays with snapshot, fork and canonical hash, seeded streams, tick engine, AST determinism scan (`tools/ci/determinism_scan.py`, found a real set iteration in world.py), contract `control-no-ground-truth` now lists every non-leaf module, numpy==2.5.4. Speed (code speed on this machine, toy system): empty loop about 1.87 M ticks/s, fork rollout of 10 entities about 14.4 k ticks/s (`results/e8/dev/`). The 10-robot rollout with lidar is measured in B8.
- B2 `docs/crisis-replanning-design`: ADR-023 (crisis replanning with counterexample-guided validation), ADR-024 (occlusion-aware speed cap), ADR-025 (state layout and rollout cost), ADR-017 amendment (E4 configurations A to E), plan schema, Phase 5C, Phase 7B viewer, E10, T17 and T18, prompt requirements, README layer marks. E9 is referenced by the brief and is not defined in the repo (PENDING 29).
- B1 reconciliation `docs/phase1-conventions-update`: ADR-021 now matches the brief (params leaf module, delay ticks per class, footprints, kinematics defaults, action durations, belief state type, unavoidable_at_spawn), ARCHITECTURE has the simulator module layout and footprints, EXPERIMENTS has the master seed rule.
- B0 `chore/push-guard-hardening`: the guard allows only `git push [-u] origin <type/short-description>`, denies main/master, flags, refspecs and tags, and gates push and `gh pr create` on `tools/ci/pre_push_check.py` (CI stamp on HEAD, clean tree, gitleaks, no .env or held-out files). `uv run ci` writes the stamp. gitleaks 8.30.1 installed with winget. Pushing is allowed from now on (brief Part 1.3 waived). Next: B1 reconciliation, then B2 to B8 per `docs/PHASE1_BRIEF.md`.
- `docs/phase1-conventions` (branch 0 of Phase 1, stacked on `docs/design-extensions`): ADR-021 (dt = 0.025 s, lidar 10 Hz, seeded streams, determinism scan, canonical hash, detector conventions), PLAN moves telemetry generator and S19 to S36 to Phase 6, seed split in EXPERIMENTS, reproduction scope in README, import-linter contract `control-no-ground-truth` with fixture, stub modules in `waggle.sim`. `uv run ci`: 502 tests, 3 contracts kept.
- `docs/design-extensions` (cut from `chore/final-check`): ADR-018 sensing and predictive caution, ADR-019 missions and handoff, ADR-020 failure history and purchase orders (all proposed). ARCHITECTURE (new sections, data model, tool list, diagram), PLAN (Phases 1, 2, 3, 6), EXPERIMENTS (E1, E2, E6, S31 to S36), THREAT_MODEL (T14 to T16) and README updated. Every new element is marked "designed, not implemented". Test: `tests/unit/test_design_extensions_docs.py`.
- `chore/agents-push-and-pr` (cut from `chore/final-check`, separate branch): rule change ADR-022. Agents push task branches and open PRs with `gh pr create`. The guard still denies force push, ref deletion, push to `main` and merge.

## Current state
- PR 1 (`chore/final-check`) and PR 2 (`chore/agents-push-and-pr`) are merged. PR 3 (`docs/design-extensions`) and PR 4 (`docs/phase1-conventions`, stacked on 3) are open and the maintainer merges them. Agents push their task branches and open PRs (ADR-022). Next is `feat/sim-core`, stacked on `docs/phase1-conventions`. If a base branch is merged into main, fetch and merge origin/main into the stacked branch instead of rewriting published history. The local `.claude/settings.json` is emptied by the maintainer on purpose; they restore it by hand when required.
- Kinematics addendum (docs done in branch 0): `feat/sim-robots` must also test that a robot never exceeds its turning radius or angular speed, that stopping distance in a turn stays within the documented bound, that a forklift at full speed cannot clear a blind corner a carrier can, and `load_raised`. The detector (`feat/sim-detector`) uses the swept footprint along the curved path. The route planner is Phase 3.
- Push guard conditions to implement in a later chore branch: explicit `type/short-description` branch only, no bare push, no tags, no push from main, pre-push script (`uv run ci` green on HEAD plus gitleaks), deny diffs touching `results/**/heldout/`, same gate for `gh pr create`. The current hook on `chore/agents-push-and-pr` is looser than that.
- The maintainer pushes `main` and `chore/final-check`, merges that PR, and enables branch protection (steps in the maintainer message). Neither new branch is pushed yet.
- ADR numbers: ADR-021 is reserved for "Simulation conventions" (Phase 1 prompt below). The push rule is ADR-022.
- Open maintainer decisions: PENDING 22 (numpy). The maintainer approved numpy for `waggle.sim` in the Phase 1 prompt; record it in README and PENDING when it is added.

## Prompt for the next session
The maintainer brief is stored in `docs/PHASE1_BRIEF.md` and replaces the prompt below. Follow its branch order B0 to B8 and its stop points. Its status notes list what already exists.

### Superseded prompt (kept for reference)
```
Phase 1 (simulator and ground truth), part 1 of 2. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-002, 013, 018, 019, 020), docs/EXPERIMENTS.md first. If two documents conflict, stop and ask.

Prerequisite: branch docs/design-extensions exists and is closed. If not, stop and tell me.

Approvals
- numpy is approved as a runtime dependency of waggle.sim. Check the current numpy documentation (Generator, SeedSequence, typing) before using it. Pin it through uv. Record it in the README and in PENDING.md.
- Not approved: any WebSocket or web server dependency, any JS tooling, any other runtime dependency.

Give me a short plan (branches, order, risks) and wait for my approval before writing code.

Move the machine telemetry generator and scenarios S19 to S36 from Phase 1 to the phases that need them (Phase 6 and later) in PLAN.md, in the first branch.

ADR-021 "Simulation conventions", status proposed, written first:
- SI units: meters, seconds, radians. 2D plane. Fixed step dt = 0.02 s (50 Hz), one constant that every layer reads, never a wall clock.
- One root seed per run. Spawn independent streams per entity and per subsystem with numpy SeedSequence.spawn. No global random, time, datetime, network or os.urandom inside waggle.sim and waggle.control, enforced by a test that parses the sources.
- Ground truth versus observation: waggle.control never reads ground truth. It reads only the observation types defined in waggle.sim.observations. Add an import-linter contract for this (control must not import the ground-truth modules or the detector), with a fixture and one test per contract, as in Phase 0.
- Every tick can be hashed with a stable serialization, for replay and determinism tests.

Branches, in order, stacked on docs/design-extensions, tests first (Hypothesis where an invariant exists). After each: uv run ci, update LASTCONTEXT.md and PENDING.md.
1. feat/sim-core: tick loop, seeded streams, world model, JSON world format.
2. feat/sim-robots: four classes with the ARCHITECTURE.md parameters, oriented footprints, actuation delay, limits enforced.
3. feat/sim-humans: scripted paths, seeded walkers, adversarial humans.
4. feat/sim-detector: exact swept collision and separation detector, independent of control code.
5. feat/sim-sensors: simulated 2D lidar and the optional beacon variant, output types in waggle.sim.observations.
6. feat/sim-scenarios: scenario format, generators for S01 to S18, data/seeds.json with disjoint development and held-out seeds, replay runner with per-tick state hash, no-control baseline on development seeds to results/e1/dev/<run_id>.json. Do not run held-out seeds.

After branch 6, stop and report: done, not done, risks, measured numbers (ticks per second, labeled as code speed on this machine), and the push order. Pushing task branches and opening PRs is allowed once chore/agents-push-and-pr is merged (ADR-022). The 2D debug viewer comes in a separate session after the WebSocket dependency decision.
```
