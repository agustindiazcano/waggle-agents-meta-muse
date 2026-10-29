# Waggle Hive: Last context

Updated: 2026-10-29.

## Done last
- `docs/phase1-conventions` (branch 0 of Phase 1, stacked on `docs/design-extensions`): ADR-021 (dt = 0.025 s, lidar 10 Hz, seeded streams, determinism scan, canonical hash, detector conventions), PLAN moves telemetry generator and S19 to S36 to Phase 6, seed split in EXPERIMENTS, reproduction scope in README, import-linter contract `control-no-ground-truth` with fixture, stub modules in `waggle.sim`. `uv run ci`: 502 tests, 3 contracts kept.
- `docs/design-extensions` (cut from `chore/final-check`): ADR-018 sensing and predictive caution, ADR-019 missions and handoff, ADR-020 failure history and purchase orders (all proposed). ARCHITECTURE (new sections, data model, tool list, diagram), PLAN (Phases 1, 2, 3, 6), EXPERIMENTS (E1, E2, E6, S31 to S36), THREAT_MODEL (T14 to T16) and README updated. Every new element is marked "designed, not implemented". Test: `tests/unit/test_design_extensions_docs.py`.
- `chore/agents-push-and-pr` (cut from `chore/final-check`, separate branch): rule change ADR-022. Agents push task branches and open PRs with `gh pr create`. The guard still denies force push, ref deletion, push to `main` and merge.

## Current state
- Phase 1 stack so far: `docs/design-extensions` then `docs/phase1-conventions`. Next is `feat/sim-core`. Branches are local. The maintainer pushes `chore/final-check`, `chore/agents-push-and-pr` and `docs/design-extensions` from their own terminal (bootstrap exception). After they are merged into main and the maintainer says so: fetch, rebase the unpushed Phase 1 branches onto origin/main, run `uv run ci` on each, push each and open its PR (first against main, each next against the previous branch).
- Kinematics addendum (docs done in branch 0): `feat/sim-robots` must also test that a robot never exceeds its turning radius or angular speed, that stopping distance in a turn stays within the documented bound, that a forklift at full speed cannot clear a blind corner a carrier can, and `load_raised`. The detector (`feat/sim-detector`) uses the swept footprint along the curved path. The route planner is Phase 3.
- Push guard conditions to implement in a later chore branch: explicit `type/short-description` branch only, no bare push, no tags, no push from main, pre-push script (`uv run ci` green on HEAD plus gitleaks), deny diffs touching `results/**/heldout/`, same gate for `gh pr create`. The current hook on `chore/agents-push-and-pr` is looser than that.
- The maintainer pushes `main` and `chore/final-check`, merges that PR, and enables branch protection (steps in the maintainer message). Neither new branch is pushed yet.
- ADR numbers: ADR-021 is reserved for "Simulation conventions" (Phase 1 prompt below). The push rule is ADR-022.
- Open maintainer decisions: PENDING 22 (numpy). The maintainer approved numpy for `waggle.sim` in the Phase 1 prompt; record it in README and PENDING when it is added.

## Prompt for the next session
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
