# Waggle Hive: Phase 1 session brief

Source: maintainer message of 2026-10-29, stored verbatim below so the project can change without losing it. It replaces every earlier maintainer prompt that was not completed. `LASTCONTEXT.md` holds the current state and points here. `PENDING.md` tracks the open items. If this brief and `AGENTS.md` conflict, stop and ask.

## Status notes (kept up to date by the agent)

| Item | State on 2026-10-29 | Note |
|---|---|---|
| B0 `chore/push-guard-hardening` | not started | The hook merged in PR 2 is looser than Part 4 B0. The maintainer emptied the local `.claude/settings.json` on purpose and restores it by hand when required. |
| B1 `docs/phase1-conventions` | partly done, PR 4 open | ADR-021 exists. Still to reconcile with B1: `waggle.sim.params` as a second leaf module, actuation delay ticks per class, footprint and kinematics defaults, stationary action durations, belief and ground truth sharing one state type, the `unavoidable_at_spawn` flag, `waggle.validation` in the determinism scan. |
| Import contract `control-no-ground-truth` | already added in PR 4 with stub modules | The brief says the contract arrives in B3. The existing contract forbids `world`, `entities`, `engine`, `detector`, `sensors`. B3 must widen it to "everything in `waggle.sim` except `observations` and `params`" and add the `params` leaf module. |
| Part 1.3 "do not push until B0 is in main" | already pushed before this brief | Branches of PR 1 to PR 4 were pushed under ADR-022 and the bootstrap exception. No push happens from now on until B0 is merged, unless the maintainer says otherwise. |
| ADR numbers | 021 used, 022 used | The brief reserves ADR-023, ADR-024 and ADR-025 for B2. |
| AGENTS.md | section 18 amended | Only section 18, as approved in 0.3. |

---

## PART 0. ORIENTATION AND RULES

0.1 Read first: AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/THREAT_MODEL.md, docs/EXPERIMENTS.md, docs/GOTCHAS.md. Run git status, git branch, git worktree list. If two documents conflict, stop and ask.

0.2 The Phase 1 plan (branches 0 to 6) is approved with the changes in this brief. Do not ask for approval again except at the stop points of Part 6.

0.3 AGENTS.md amendments approved now: section 18 (priority order and gates, in B2) and nothing else. Any other change to AGENTS.md needs maintainer approval.

0.4 Rules that stay: one branch per task, stacked on the previous one, tests first and the failing run is shown before implementing (docs included), Conventional Commits split by concern, uv run ci green before every push, no secrets, never print env values, no dependency beyond what is approved in Part 2, every measured figure labeled as code speed on this machine, no claim without a command and its output. Plain technical English, no em dash, no emoji, no filler adjectives (the style test enforces it). Hypothesis: a modest default profile for local and CI runs, and tests that need many examples carry the `heavy` marker.

0.5 LASTCONTEXT.md holds the current state and a pointer to this plan and the next branch, not a copy of this brief.

## PART 1. PUSH AND PR RULES (ADR-022 stands: agents push their task branches and open PRs)

1.1 Agents never merge, never run gh pr merge, never push to main or master, never force push. The maintainer merges.

1.2 Bootstrap state. Check with git fetch and git branch -r whether origin/main exists and whether chore/final-check, chore/agents-push-and-pr and docs/design-extensions are merged into it. If they are not, the maintainer pushes them once from their own terminal. Do not try to push them and never edit, bypass or disable a hook to do it. Keep working locally, stacked, and wait for the message "merged". When it arrives: git fetch, rebase the unpushed branches onto origin/main (allowed because they are unpushed), run uv run ci on each, then push each branch and open its PR with gh pr create. The first PR targets main and each next one targets the previous branch, in order.

1.3 Branch B0 (below) hardens the push guard. Until B0 is in main, do not push anything.

## PART 2. DEPENDENCIES

Approved: numpy as a runtime dependency of waggle.sim, waggle.control and waggle.validation (standard library and numpy only there). Check the current numpy documentation (Generator, SeedSequence, BitGenerator state, typing) before using it. Pin it through uv, record it in README and PENDING.md.

Not approved: FastAPI, uvicorn, any web server or WebSocket library, any JavaScript tooling, pydantic, psycopg, any other runtime dependency. Validation of schemas is hand-written on frozen dataclasses. Ask at the stop point.

## PART 3. BRANCH ORDER

All stacked. Each: tests first, uv run ci, update LASTCONTEXT.md and PENDING.md.

| Id | Branch |
|---|---|
| B0 | chore/push-guard-hardening |
| B1 | docs/phase1-conventions |
| B2 | docs/crisis-replanning-design |
| B3 | feat/sim-core |
| B4 | feat/sim-robots |
| B5 | feat/sim-humans |
| B6 | feat/sim-detector |
| B7 | feat/sim-sensors |
| B8 | feat/sim-scenarios |

## PART 4. BRANCH SPECIFICATIONS

### B0 chore/push-guard-hardening

Protected paths: tools/hooks/ and .claude/ will ask for maintainer approval on each edit. Read the current hooks documentation before editing.

1. Safety guard: allow only `git push -u origin <branch>` or `git push origin <branch>` with an explicit branch name matching type/short-description (types: feat, fix, test, docs, exp, chore, ci) that is not main or master. Deny a bare `git push`, --force, --force-with-lease, -f, --delete, :ref refspecs, --tags and any tag push. Deny any push while the current branch is main. Deny any push whose diff against the remote touches results/**/heldout/. gh pr create is gated by the same checks. gh pr merge is denied.
2. Pre-push check script, tools/ci/pre_push_check.py, stdlib only, called by the guard before it allows a push: (a) a stamp written by `uv run ci` on success, stored under .git/, must contain the current HEAD sha and the working tree must be clean; (b) gitleaks must find nothing in the commits that would be pushed (check the current gitleaks documentation for the right subcommand and log-opts; if gitleaks is not installed, fail closed with a clear message); (c) no staged or committed .env or held-out result file in those commits. Make `uv run ci` write the stamp only on a fully green run.
3. Tests first, one stdin event per rule, a benign command for each family that must pass, malformed event gives ask, plus tests for the pre-push script using a temporary git repository.
4. If another hole in the guard is found, report it, do not widen it.

### B1 docs/phase1-conventions (docs only)

1. ADR-021 "Simulation conventions", proposed:
   - 2D simulation on the floor plane. Height is not modeled. Rendering is 3D and the FPV vision check renders the 3D scene. State this in README Scope and limits.
   - SI units: meters, seconds, radians. Fixed step dt = 0.025 s (40 Hz), one constant read by every layer, never a wall clock. Every actuation delay must be an integer multiple of dt, rejected at load otherwise (carrier, parts_runner and tech_repair 0.10 s are 4 ticks, forklift 0.15 s is 6 ticks). Lidar rate 10 Hz (every 4 ticks).
   - One root seed per run. Independent streams per entity and per subsystem with numpy SeedSequence.spawn so adding an entity does not change other streams.
   - Determinism scan by AST over waggle.sim, waggle.control and waggle.validation: forbid time, datetime, random, uuid, secrets, os.urandom, network access, numpy global random functions, np.random.seed, default_rng without a SeedSequence child, builtin hash() on strings, and iteration over a set when building state or hashes. Comments and strings must not cause false positives.
   - Canonical state hash: serialization with sorted keys and floats rounded to a fixed number of decimals (document it). Never commit golden hash values. Determinism tests compare two runs in the same process. Every result file records numpy version and platform. README: exact reproduction holds on the same platform and numpy version, and published results come from the cloud run (Linux).
   - Ground truth versus observation. Control never reads ground truth. Leaf modules that control may import: waggle.sim.observations (observation types) and waggle.sim.params (frozen dataclasses with robot class parameters, which a robot knows about itself). Everything else in waggle.sim is forbidden to waggle.control, including world, detector, sensors, humans and robots. Leaf modules import nothing from the forbidden side and waggle/sim/__init__.py imports nothing, or import-linter flags indirect imports. The contract is added in B3 together with its fixture and one test.
   - Detector conventions: closed sets, so exact touch is contact and contact is a collision. Separation below the declared margin is a violation. Human footprint: disc of radius 0.30 m by default (assumption). Robot footprints: oriented rectangles per class (length and width are assumptions to calibrate).
   - Robot kinematics are non-holonomic. Forklift: bicycle model with wheelbase and maximum steering angle giving a minimum turning radius. Carrier, parts_runner and tech_repair: differential drive with a maximum angular speed. Pick documented default values and mark them as assumptions to calibrate (starting ranges: forklift minimum turning radius 1.5 to 2.5 m, differential maximum angular speed around 1.5 rad/s). Optional parameter load_raised for the forklift lowers maximum speed and the deceleration limit by documented factors (assumption).
   - Stationary actions PICK, HANDOFF, DELIVER and DISPATCH_REPAIR have durations that are simulation parameters recorded in the scenario config (assumptions).
   - The simulation state type is the same for ground truth and for belief states. The difference is what populates it.
2. docs/ARCHITECTURE.md: add the kinematic parameters to the robot class table and the module layout of waggle.sim (world, params, observations, robots, humans, detector, sensors, scenarios, scripted).
3. PLAN.md: Phase 1 keeps the simulator, robots with non-holonomic kinematics, humans, exact detector, lidar, beacon variant, scenarios S01 to S18, seeds and the no-control baseline. Move the machine telemetry generator and scenarios S19 to S36 to the phases that need them. Phase 3 adds a deterministic route planner (A* on the aisle graph, one-lane aisles as zones of capacity one reserved through leases, a deadlock counter reported in E2).
4. Seeds policy in docs/EXPERIMENTS.md: S01 to S18, 5 development seeds and 12 held-out seeds per scenario (90 and 216 runs per configuration), disjoint, generated once from a fixed master seed and never regenerated. With 216 runs and zero collisions the Wilson 95 percent upper bound is about 1.7 percent, with 100 runs it would be 3.7 percent. Scenarios carry a flag unavoidable_at_spawn, computed from geometry (a human spawns inside the minimum possible stopping distance of a robot at its speed cap). E1 reports unavoidable cases separately and never hides them.

### B2 docs/crisis-replanning-design (docs only)

Scope rule: do not shrink any existing module or experiment. E1 to E9 keep their full specifications, baselines and ablations. E4 stays a standalone experiment. E6 keeps the online first-order thermal predictor, manual sheet validation, pgvector retrieval, failure history, and the idempotent reservation and purchase order. E10 is added. The order in item 8 is the build order. Nothing is cut.

1. ADR-023 "Crisis replanning with counterexample-guided validation", proposed.
   - Muse Spark receives a structured world summary, retrieved SOP excerpts (fenced as untrusted data), an optional obstacle class from vision, and the operator request or a text incident report. It proposes a plan in the schema of item 2.
   - The validator builds a belief state from what the control layer may know at t = 0: static map, entities currently tracked from lidar, and K seeded human variants (default K = 5, streams spawned from the snapshot RNG state), including humans spawned inside initially occluded regions consistent with the scenario's declared density. A sampled variant is rejected at sampling when it puts a human inside the minimum stopping distance of a robot at t = 0, because no plan can fix it. The validator does not fork ground truth. Snapshot and fork of the true state exist for determinism tests and replay only.
   - The rollout runs the same dynamics, simulated 10 Hz lidar raycasting against the belief state, dynamic occlusion-boundary speed capping, the fast reflex layer and in-memory lease logic as execution, over H simulated seconds (default 45, configurable). Occlusion boundaries are recomputed from the simulated robot pose at every lidar tick of the rollout. They are never frozen as static phantom entities from t = 0.
   - Acceptance. A plan is accepted only if, in every one of the K rollouts over [0, H]: zero collisions, zero separation violations, zero hazard geofence intrusions, zero deadlocks (acyclic wait-for graph), no lease conflict, route feasible; and progress: every robot with an active node either completes a node, strictly reduces its remaining geodesic route length, strictly decrements its stationary action timer (PICK, HANDOFF, DELIVER, DISPATCH_REPAIR), or waits legitimately on an acyclic dependency edge or on a lease whose holder makes strict progress toward releasing it; and at t = H the state is recoverable: each robot is either stopped outside shared capacity-1 zones or holds valid leases for its occupied and next committed segments. Mission completion within H is reported as a metric, not required.
   - Receding horizon: execute at most H/2 simulated seconds, then revalidate from the new belief state.
   - Counterexample types: COLLISION, SEPARATION_VIOLATION, GEOFENCE_INTRUSION, CORRIDOR_DEADLOCK, LEASE_CONFLICT, ROUTE_INFEASIBLE, NO_PROGRESS, UNSAFE_TERMINAL_STATE. Fields in SI units: time, place, entities, minimum clearance, violated rule. ROUTE_INFEASIBLE names the undeclared capacity-1 corridor that the route needs, or the avoided zone that cannot be avoided. Maximum 3 iterations. If none passes, escalate to the operator and the affected robots hold safely.
   - Naming: simulation-based plan validation with counterexample feedback. It is not formal verification and not a safety proof. State the assumptions (hidden human prior, K variants, horizon). Safety against humans stays in the reflex layer, which runs inside the rollout. Cite CEGIS and LLM-Modulo as prior art to verify, and do not claim novelty of the pattern.
   - Lidar gives free-space geometry. Vision, when present, gives only an obstacle class and a label check mapped through SOP text. Every crisis scenario has a text incident report as fallback.
2. Plan schema, the contract between the LLM and the validator (in ADR-023 and ARCHITECTURE.md).
   - Plan: mission_id (set by code), nodes (at most 20), rationale (free text), escalate (bool), escalation_reason (enum or null).
   - Node: label (unique in the plan, for example "n1"), robot_id, action (MOVE, PICK, HANDOFF, DELIVER, DISPATCH_REPAIR), target_zone_id, corridor_zone_ids (ordered list of the capacity-1 corridor zones to traverse, empty only if the path uses open transit zones only), avoid_zone_ids, wait_for (labels), item_id or null, speed_cap_mps or null.
   - Rules: unknown fields rejected. Zone, robot and item ids validated against the map, the fleet and the inventory in code. wait_for references existing labels and is acyclic. speed_cap_mps can only reduce: effective speed is the minimum of the deterministic limit and the cap, the cap is greater than zero and not above the class maximum. avoid_zone_ids can only add avoidance, and reflex-layer geofences always win. Idempotency keys and global task ids are derived by code from the mission id and the node index and content, never produced by the model. Each node maps to MCP tool calls under that robot's chassis identity. The validator plans geometry with A* on the aisle graph, free through open transit zones, excluding avoid_zone_ids, and restricted from entering any capacity-1 corridor not listed in corridor_zone_ids. When no valid path exists under those constraints it returns ROUTE_INFEASIBLE with the offending zone. The rationale field is logged for the operator and never forwarded to another model. Validation is hand-written on frozen dataclasses.
3. ADR-024 "Occlusion-aware speed cap", proposed. For each occlusion boundary derived from the lidar scan, assume a phantom human at the nearest possible point approaching at v_h. Cap speed at the largest v such that S_sep(v) is at most the distance to that boundary along the swept curvilinear path. Edge cases: no non-negative root (v_h*t_r + C at least the distance) means the cap is zero; curvature near zero speed uses a minimum speed floor; every discontinuity threshold is a documented parameter with its rationale. No other new parameters. The cost is throughput, reported in E1.
4. ADR-025 "Simulator state layout and rollout cost", proposed. State is a structure of contiguous numpy arrays (poses, velocities, zone tokens and expiries) plus a small dict of RNG states, with snapshot() and from_snapshot(). No deepcopy and no JSON in the hot path. Do not write any timing figure in the documents. Rollout cost is measured in Phase 1 and reported as code speed on this machine. Optimizations to consider only if the measurement demands them, each documented as a deviation: lower lidar rate inside rollouts, cached static visibility, process-level parallelism across the K variants. The lidar model is a pure function over geometry arrays (static map, dynamic footprints, pose, params, rng) so the validator can reuse it on a belief state.
5. ADR-017 amendment. E4 stays unanimity at full standalone scope, with configurations: A single Muse Spark; B two Muse members; C three Muse members with identical prompts; D three Muse members with role-specialized checklists (SOP compliance, provenance and injection, operational conflict); E two Muse members plus a non-Muse member on Vertex. An LLM never checks inventory, chassis capability or zone invariants: code does. Report false approvals first, false blocks, escalation and pairwise correlation.
6. New package waggle.validation, to be created in Phase 5C: rollout, belief state and counterexample types as frozen dataclasses. It may import waggle.sim and waggle.control, never waggle.llm, waggle.governance or waggle.mcp_server. waggle.sim and waggle.control must not import it. The import-linter contract is added when the package exists. Runtime dependencies there: numpy and the standard library. Add to Phase 3 exit criteria: a Hypothesis property test that the in-memory lease model used by the rollout and the PostgreSQL implementation accept and reject the same sequences of acquire, release, expire and stale-token operations. Lease expiry is stored in simulation ticks supplied by the caller. Audit timestamps keep clock_timestamp().
7. Docs.
   - ARCHITECTURE: planner, validator, belief state, occlusion cap, plan schema, consistent mermaid diagrams.
   - THREAT_MODEL: T17 a plan passes the rollout and meets an unmodeled human behavior in execution (mitigation: the reflex layer stays active and the receding horizon revalidates); T18 indirect injection through SOP text, package label text or incident text into the planner.
   - EXPERIMENTS: E1 configurations (no control, radial 1D distance, swept footprint, swept footprint plus occlusion cap, plus CPA prediction). E2 to E9 keep their full specifications. Add E10: compound-fault templates combining the thermal fault that triggers the geofence, blocked aisles, a robot dead mid hand-off, and urgent orders by text or voice, with an optional vision input and an always available text incident report, held-out seeds. Configurations: strong deterministic recovery baseline (A* routing, reassignment, lease release, the same repair moves that the planner prompt describes), Muse open loop, Muse with validator feedback, Muse with validator feedback and the role-specialized court. Metrics: violations in validation and in execution, deadlocks, recovery time, iterations, calls, cost, escalations, and the fraction of accepted plans that produce a violation in an extended 120 s rollout or in execution. Add a sensitivity run with H in 30, 45 and 60 seconds. Report what the LLM adds beyond the deterministic baseline per template.
   - PLAN.md: add phase 5C with its exit criterion, keep every other phase.
   - README layer table: mark each unimplemented layer "designed, not implemented".
8. AGENTS.md section 18, replace the list with:
   Build order, nothing is cut:
   1. simulator with snapshot and fork, exact detector, fast layer with occlusion cap, E1, end-to-end slice
   2. leases, atomic corridor locking, fencing, hand-off, E2
   3. MCP boundary, guard, injection matrix E3, full court E4
   4. crisis replanning loop and E10
   5. technical viewer with overlays (envelopes, lidar shadows, rollout ghost paths)
   6. predictive maintenance full pipeline E6, per-robot advisors E5, vision and voice E7
   7. E8 extended, E9, GLB models

   Reserved time: delivery (README tables, demo video, live VM, submission) from Nov 3 morning.

   Gates, decided by the maintainer: G1 Oct 30 night, Phase 1 closed. G2 Oct 31 night, fast layer and E1 on development seeds. G3 Nov 1 night, leases, MCP, E2 and E3. G4 Nov 2 night, court E4, crisis loop and E10 on development seeds, viewer with overlays. At each gate report actual progress against this list. Nothing is cut. Update PLAN.md to match.
9. Design notes for later phases (ARCHITECTURE and PLAN).
   - Phase 2: swept curvilinear footprint envelope for S_stop and S_sep along the current arc; occlusion cap from the lidar scan; the control layer reads only waggle.sim.observations and waggle.sim.params.
   - Phase 3: control keeps a local lease view (zone, token, expiry_tick) pushed by the coordination layer. It clamps speed before a zone with no valid grant and fails closed when the view is stale. The authoritative token check stays inside the tool (ADR-004). Control never reads the database. Multi-zone corridors are acquired in one transaction with rows locked in canonical order. Zone state FAULT_OCCUPIED: the sweeper never releases a zone while the last known odometry puts a chassis in it, it marks the zone FAULT_OCCUPIED and triggers replanning. Add it to S31 to S36.
   - Phase 4: the MCP rate limit serializes per chassis with a transaction-scoped advisory lock on a 64-bit key (for example hashtextextended), taken before counting and held until the intent row is inserted. Test: 30 simultaneous calls from one chassis.
   - Viewer: sources in web/, WebSocket bridge in src/waggle/api. Viewer v0 (primitives, top-down camera, envelope, lidar and ghost overlays, one-click chaos buttons that call the scenario format with seeds, deterministic replay with a state hash bar) starts after B8. Add it to PLAN.md.
10. Model prompt requirements (ARCHITECTURE). Prompts are versioned files under src/waggle/llm/prompts/ and the version is recorded in every result file. Code escapes closing tags before text enters a prompt. Free text derived from untrusted input is never forwarded to another model. Self-reported confidence is not a gate until calibrated in E7. Every prompt that reads untrusted text, the critics included, has the same untrusted-data boundary. The planner never produces ids, keys or physical parameters beyond the schema.

### B3 feat/sim-core

Tests first: same seed gives the same state hash at every tick (compare two runs in the same process); different seeds differ; adding an entity does not change the streams of the others; the AST determinism scan passes on the sources and fails on fixture sources that use each forbidden construct (including constructs inside comments and strings, which must not trigger it); the loader rejects malformed maps and any actuation delay that is not a multiple of dt.

Implement: tick loop with the fixed dt constant; seeded stream manager; world model (polygon or grid map with walls, racks, aisles, one-lane aisles, blind corners, stations, depots) in a JSON format; state as contiguous numpy arrays plus the RNG state dict, with snapshot() and from_snapshot(); the canonical hash; waggle.sim.params and waggle.sim.observations as leaf modules (observation types: LidarScan, RobotOdometry, BeaconReport as frozen dataclasses, no logic yet).

Snapshot tests: forking at tick t and running n ticks gives the same canonical state hash as the original run at t+n; a fork never mutates the original; all RNG streams are copied and isolated.

Add the import-linter contract from ADR-021 (control must not import anything in waggle.sim except observations and params) with a fixture under tests/ and one test, as in Phase 0. Also measure and record ticks per second of the empty loop and of a fork rollout (see B8 for the file).

### B4 feat/sim-robots

Tests first. Property tests with Hypothesis: the simulated stopping distance matches v*t_r + v^2/(2a) within a bound that is derived analytically (quantization of the delay to ticks and discretization of the deceleration) and documented with its derivation in ADR-021; speed, deceleration, turning radius and angular speed limits are never exceeded; a forklift cannot follow a curve tighter than its turning radius; a forklift at full speed cannot clear a blind corner that a carrier can in the same map.

Implement: four classes with the ARCHITECTURE.md parameters, oriented footprints, velocity commands applied after the actuation delay, bicycle model for the forklift, differential drive for the others, optional load_raised. The footprint swept along a curved path must be exposed as a polygon for the detector.

### B5 feat/sim-humans

Tests first: determinism by seed; humans respect walls; scripted paths reproduce exactly; adversarial timing is computed from the declared robot parameters and independent of any control implementation.

Implement: scripted paths, seeded random walkers, adversarial humans: step out at a blind corner, cross at the worst moment, stop in an aisle. Adversarial timing is parameterized as a fraction of the stopping distance at the robot's declared maximum speed, with the fraction drawn from the seed. Sampling of hidden-human variants (for the later validator) is a separate pure function with the rejection rule of ADR-023.

### B6 feat/sim-detector

Tests first, on hand-built cases: collision, near miss, exact touch (counts as contact), tunneling at high speed (a fast robot crossing a thin human footprint between ticks must still be detected), rotating and curved-path footprints, separation violation below the margin. A Hypothesis property test against a brute-force fine-substep check on random cases: no false negatives (if the brute force finds contact, the exact detector does), and exact detections are confirmed by the fine check within a documented tolerance, except documented grazing cases.

Implement: exact collision and separation-violation detector with swept oriented geometry, independent of control code, operating on the state arrays.

### B7 feat/sim-sensors

Tests first: known-geometry hits, occlusion at a blind corner (a human behind a rack is not in the scan), range noise within bounds, dropout rate within a tolerance fixed in advance (4 standard deviations of the nominal rate over N rays), determinism by seed, the beacon variant.

Implement: simulated 2D lidar as a pure function over geometry arrays (static map, dynamic footprints, pose, params, rng): ray casting against walls, racks and moving entities, with range, angular resolution, noise, dropout and occlusion. Default assumptions to document: 10 Hz, 360 rays, 12 m maximum range, range noise sigma 0.02 m, dropout probability 0.01. Output the LidarScan type. Optional human beacon variant (BeaconReport with position noise and delay, behind a config flag). Odometry output with noise.

### B8 feat/sim-scenarios

Tests first: the split is disjoint and unchanged after generation (the seeds file is data, a stored hash of it is allowed); replay reproduces the per-tick hash; the result file has every required field; unavoidable_at_spawn is computed correctly on hand-built cases.

Implement: scenario format (seed, map, entities, scripted events, declared target layer, expected outcome, unavoidable_at_spawn, and a reserved schema for compound crisis templates); generators for S01 to S18 of docs/EXPERIMENTS.md (S13 to S15 density 3, 10 and 30 robots on map A, S16 to S18 on map B); data/seeds.json with 5 development and 12 held-out seeds per scenario, generated once from a fixed master seed, never regenerated; a replay-by-seed runner; a minimal waypoint-following driver in waggle.sim.scripted for the no-control baseline and for scripted entities (it has no safety logic and is not the control layer); and the no-control baseline run on development seeds only, writing results/e1/dev/<run_id>.json with the result schema (commit, date, seed set, numpy version, platform, configuration, counts of human collisions, robot collisions and separation violations, separation-violation and near-miss definitions, unavoidable cases reported separately, tasks per simulated hour, failing seeds). Do not run held-out seeds. Write the speed measurements (ticks per second of the loop and of a fork rollout with 10 robots, lidar included, labeled as code speed on this machine) to results/e8/dev/.

## PART 5. AFTER EACH BRANCH

Run uv run ci and show the output. Update LASTCONTEXT.md and PENDING.md. Push and open the PR following Part 1 once pushing is allowed.

## PART 6. STOP POINTS

Stop and ask the maintainer: (a) after B0, so that the hooks diff is reviewed and the settings change approved; (b) after B8, with a report of what is done, what is not, risks, the measured speeds, and the exact PR order; at that point the maintainer decides whether to approve FastAPI, uvicorn and the JavaScript toolchain (Node, Vite, TypeScript, three) for viewer v0.

Stop and ask at any time if: a measured rollout cost makes the design in B2 doubtful, a test of the determinism scan keeps failing for a reason that cannot be resolved, or a rule in this brief conflicts with AGENTS.md.
