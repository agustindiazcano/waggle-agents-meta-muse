# Waggle Hive: Architecture Decision Records

Format: context, decision, consequences. Status: accepted unless noted.

## ADR-001: LLMs propose, deterministic code disposes

Context: robots share space with humans. LLM latency is seconds and output is not guaranteed stable.
Decision: stopping, separation, geofences, leases and tool authorization are deterministic. LLMs produce structured proposals only.
Consequences: the system stays safe with LLMs down. LLM contribution is measured separately from safety.

## ADR-002: Simulator owns ground truth, Three.js only renders

Context: metrics must be reproducible by seed. A browser physics engine is not.
Decision: Python simulator with fixed-step tick and seeded RNG. Frontend receives state over WebSocket.
Consequences: Meshy assets add no risk to the measurements. The 3D scene can be built late.

## ADR-003: PostgreSQL for queue and leases

Context: leases and fencing need transactions with row locks. A separate broker adds a failure mode.
Decision: tasks queue with `FOR UPDATE SKIP LOCKED`, leases and tokens in the same database. RabbitMQ is not used unless a measured need appears.
Consequences: one fewer component. Revisit if queue throughput limits E2 or E8.

## ADR-004: Fencing check inside the tool

Context: a check outside the tool followed by the action is check-then-act and races.
Decision: the tool receives `(zone, token)` and verifies within one transaction with the zone row locked.
Consequences: stale writers are rejected at the resource. A baseline without this is kept to show the failure.

## ADR-005: Unanimous court, never approve over a rejection

Context: a tie-break that can approve over rejections can reintroduce the error the extra reviewers remove.
Decision: execute only if all members approve with valid output. Any reject, split, timeout or parse failure goes to the operator.
Consequences: more escalations and false blocks. Both are measured in E4.

## ADR-006: Court diversity is measured, not assumed

Status: Superseded by ADR-017 (the diversity part: the court is no longer three families). The requirement to measure error correlation stays.

Context: same-family models can share blind spots, and different families can still agree on a mistake.
Decision: three families. Report pairwise correlation of errors for same-family and cross-family pairs.
Consequences: diversity is presented as a measured property with its limits.

## ADR-007: Third model family

Status: Superseded by ADR-015 (provider plan) and ADR-017 (court composition). The text below is kept as written.

Decision: Gemini via its API, with a hard spending cap, as the third court member. Alternatives considered: another open-weight family on Modal. Revisit after Phase 0 credit checks.
Consequences: adds an external dependency and cost. Replaceable behind the same interface.

## ADR-008: Untrusted input fails closed

Context: earlier designs in related work let the screening layer fail open.
Decision: if screening cannot score an input, the input is rejected and escalated.
Consequences: more escalations during provider outages. Acceptable for a safety system.

## ADR-009: Telemetry thresholds act without retrieval

Decision: threshold crossing sets the geofence and severity in the fast layer. RAG runs in parallel for procedure, part and ticket text only.
Consequences: stopping never depends on retrieval quality.

## ADR-010: Manual facts are extracted once into a validated sheet

Decision: limits and part numbers come from a structured sheet validated by schema, produced once from the manual. Live retrieval supplies text, not limits. Part numbers are verified against the catalog in code.
Consequences: a bad retrieval cannot change a limit or order a nonexistent part.

## ADR-011: Per-robot LLM advisors are bounded

Decision: the safety advisor can only add caution. The organizer acts through the MCP with its own identity. Both have turn and budget limits, and their messages are untrusted input.
Consequences: more calls and cost per task, measured in E5. Removing them must leave the system safe.

## ADR-012: Single VM with Docker Compose for the demo

Decision: no managed cloud orchestration. Terraform only if time remains and it adds reproducibility.
Consequences: simpler live demo with a WebSocket simulator. A recorded fallback is kept.

## ADR-013: Separation formula is inspired by SSM, no compliance claim

Decision: use stopping distance and human approach speed terms with documented assumptions. Do not cite standards as satisfied.
Consequences: claims stay within what is validated.

## ADR-014: Results are reported with baselines and intervals

Decision: every metric has a baseline, counts and intervals, failing seeds and a declared target layer where relevant.
Consequences: negative results appear in the README.

## ADR-015: Provider plan and credits

Status: proposed.

Context: the maintainer reports partner credits of $150 on the Meta Model API, $100 on Baseten and $101 on Modal. These amounts must be verified in each console, together with expiry dates and rate limits. The design depends on these credits being used first. All data in this project is synthetic.

Decision:
- Meta Model API: Muse Spark (director, fleet planner, diagnosis, court member 1), Muse Voice Transcribe, and vision with Muse Spark image input (Muse Wonder only if its docs and pricing favor it). Model ids are read from the API model list (`GET /v1/models`) and stored in environment variables, never hardcoded. The docs list a cheaper contributor id whose traffic is used to improve Meta's products. It is allowed only because all data is synthetic, and it is switched by `META_USE_CONTRIBUTOR_TIER`.
- Baseten: `meta-models/muse-spark-open-1026` as court member 2, per-robot advisors and organizer.
- Modal: Muse Glimmer 30B (Apache 2.0, Hugging Face `meta-models/Muse-Glimmer-30B`) as court member 3 and as the guard, as two separate deployments or configs. Before writing any serving script, check whether Modal or Baseten already offers a ready endpoint. A first search found hosted endpoints elsewhere and no Modal or Baseten listing, and this is still to verify. GPU time stays bounded: short scale-down, run only for experiments and the demo. Modal is also the declared fallback host for Muse Spark Open when Baseten fails.
- Vertex AI (Gemini): secondary backup only, and the non-Muse member of E4 configuration D. It authenticates with a service account, never a key in the repository.
- Spend rules: Partner credits first. Cap per provider is the balance minus a 10 percent reserve. Planning split, as assumptions to calibrate: 40 percent development, 40 percent held-out runs, 10 percent demo and video, 10 percent reserve. No personal card without maintainer approval. Fallbacks are declared in the routing table, logged and labeled in the call log, and disabled in held-out runs.

Consequences: Meta, Baseten and Modal credits carry the whole project. A cap that is missing or invalid blocks calls. Exhausting a provider never moves calls to another provider except through a declared fallback. The budget guard and routing table in `waggle.llm` implement this.

## ADR-016: Model tiers and roles

Status: proposed.

Context: LLM latency is seconds, so no LLM can sit in the control loop.

Decision:
- Reflex tier: deterministic code, every tick, no LLM (fast layer, fencing).
- Fast LLM tier: Muse Spark Open 1026 on Baseten. Roles: per-robot safety advisor (can only add caution) and per-robot organizer (escalates to the planning tier only on ambiguity or inter-robot conflict). The guard classifier (Muse Glimmer) is also a fast, small call.
- Planning LLM tier: Muse Spark on the Meta API, and Muse Glimmer on Modal as court member 3. Roles: director, fleet planner, diagnosis, court.
- Fleet planner (new, optional): event-driven and low frequency. It proposes assignments, batching and reroutes. A deterministic validator checks feasibility, leases and bounds before anything is applied. If the planner fails or times out, the deterministic assigner is used. It is an extra configuration in E5, not a replacement for the code-only baseline.
- Calls are triggered by a change of context or every N seconds, never per tick, with a per-task call and cost cap and a cache.

Consequences: more calls and cost per task, measured in E5. Removing every LLM tier must leave the system safe.

## ADR-017: Court composition and guard

Status: proposed. It supersedes the diversity part of ADR-006.

Context: every model role uses a Meta Muse model. These models are related: Muse Spark Open is the open-weight release of Muse Spark, and Muse Glimmer is distilled from Muse Spark. Correlated errors are expected.

Decision:
- Default court: Muse Spark, Muse Spark Open 1026, Muse Glimmer. Execute only on unanimous approve. Any reject, split, timeout or parse failure goes to the operator (ADR-005 unchanged). These are not three independent families and the documents do not call them that.
- E4 configurations: A single Muse Spark; B two Muse members; C default Muse court; D Muse Spark, Muse Spark Open and a non-Muse member on Vertex. Report false approvals first, then pairwise correlation and cost. Run D once on the held-out set within the Vertex cap. The default for the live demo is whatever the held-out results support.
- Guard: an LLM classifier with strict structured output (label benign, injection or uncertain, plus a reason code), Muse Glimmer on Modal, behind the provider interface. Input is fenced as untrusted data. Deterministic sanitizers run first (length, charset, delimiter escaping). Fail closed: a parse failure, a timeout or uncertain rejects and escalates.
- Known weakness: an LLM guard can be talked into answering benign. It is the first screen and not the boundary. Identity and schemas are the boundary. E3 measures misses and false rejections on benign near-lookalikes, and the label policy is fixed before the run.
- There is no rule that guard and court use different providers. Everything fails closed, so an outage of one provider degrades to escalation, never to approval. This is tested for each provider with the mock provider.

Consequences: a correlated court may agree on a mistake, and E4 reports how often. A guard outage raises the escalation rate.

### Amendment (crisis replanning session): E4 configurations

E4 stays a standalone experiment with unanimity at full scope. Configurations: A single Muse Spark; B two Muse members; C three Muse members with identical prompts; D three Muse members with role-specialized checklists (SOP compliance, provenance and injection, operational conflict); E two Muse members plus a non-Muse member on Vertex. An LLM never checks inventory, chassis capability or zone invariants: code does. Report false approvals first, then false blocks, escalation rate and pairwise correlation. The earlier configuration list above is replaced by this one.

## ADR-018: Sensing model and predictive caution

Status: proposed. The lidar (waggle.sim) and tracking (B13) are implemented; the CPA in B15, see the end of this record.

Context: a fast layer that reads ground truth hides what a real robot cannot see around a blind corner. The detector that scores E1 must stay exact.

Decision:
- Robots perceive through a simulated 2D lidar: ray casting against walls, racks and moving entities, with range, angular resolution, noise, dropout and occlusion, all seeded. The fast layer reads only what the lidar detects. The exact detector keeps using ground truth and never feeds the control code.
- Optional variant: human beacons that are visible around corners.
- Prediction: constant velocity extrapolation of each detected object, then the closest point of approach (time and distance) compared with the robot's stopping distance. Prediction can only add restrictions earlier. The worst-case separation envelope of the fast layer stays the floor.
- No learned model. Camera and vision stay out of the control loop.
- Lidar dropout or a stale scan makes the layer assume the worst case (conservative default, watchdog).

Consequences: E1 compares ground truth, lidar only and lidar with beacons, and envelope only against envelope with prediction. The lidar needs array math, so numpy as a runtime dependency of `waggle.sim` was approved by the maintainer (PENDING 22).

Implementation in B15 (`waggle.control.cpa`), with the choices the first text left open:
- Each track with a velocity estimate is walked forward for `horizon` (3.0 s, assumption) in steps of `step` (0.1 s) at constant velocity, while the robot follows the arc of its requested command at the requested speed. The meeting is the first step at which the person is inside the footprint widened by the body radius and the lateral margin.
- The cap is the structure rule applied to the room before the meeting: the largest speed with `S_stop(v)` plus the structure margin at most `requested speed * meeting time`. The person's own motion is already in the prediction, so the human reaction term of the envelope is not added. It only restricts, and the envelope stays the floor: the CPA limit is one more item in the arbiter, reason `CPA`.
- A person already inside the widened footprint gives zero. A track that is not finite gives zero.
- A track adds no limit when it has no velocity estimate or was not seen within `max_scan_age_ticks`. Unknown is not treated as safe by the CPA, it is left to the envelope ring and the occlusion cap.
- The velocity is a least squares slope over the track trail (`trail_ticks` 40, at least `velocity_min_ticks` 10, assumptions), clipped to `v_h_max`. Beacon positions arrive every tick with noise, so the two-detection velocity of ADR-026 is not used by the CPA.
- A speed below the request is not re-predicted: the meeting is computed at the requested speed every tick. A person who would cross after a slower robot is therefore covered by the envelope, not by the CPA. The prediction is not monotone in speed, which is why it is not searched.
- Switched on by `ControlInputs.use_cpa` (configurations 6 and 7 of ADR-028).

## ADR-019: Missions and handoff

Status: proposed. Designed, not implemented.

Context: a repair needs a part carried by one robot to a technician robot. Two robots and two tasks must agree on one delivery.

Decision:
- A mission is a small task graph with dependency edges. A task is eligible only when its dependencies are done.
- A handoff is an event with an idempotency key at a rendezvous zone (capacity one, lease with fencing token). The dependent task becomes eligible exactly once, however many times the delivery is reported.
- If the carrier dies, its lease expires, the task is reassigned, and the fencing check blocks the stale carrier.
- Inter-robot messages stay schema-validated, screened as untrusted and bounded by turns and budget.

Consequences: E2 gains a handoff chaos test with a no-fencing baseline. Threat T14 covers spoofed or duplicated handoffs.

## ADR-020: Failure history and purchase orders

Status: proposed. Designed, not implemented.

Context: diagnosis improves with similar past cases, and a zero-stock part needs an order.

Decision:
- A synthetic failure log (`failure_history`), generated separately from the simulator's degradation dynamics. The two never share parameters. It serves retrieval of similar cases in diagnosis and offline calibration of the predictor.
- MCP tool `create_purchase_order` writes to a simulated procurement table (`purchase_orders`) when stock is zero. It is idempotent per failure event. The part number is verified against the catalog in code before any order.
- Retrieved cases are untrusted text. They inform the ticket and never widen access.

Consequences: E6 reports diagnosis accuracy with and without the history, wrong part orders and duplicate purchase orders. Threat T16 covers duplicates.

## ADR-021: Simulation conventions

Status: proposed.

Context: Phase 1 builds the simulator that every experiment depends on. Reproducible runs and a clean split between ground truth and what control sees are the base of E1.

Decision:
- Units and step: SI units (meters, seconds, radians). The simulation is 2D on the floor plane. Height is not modeled. Rendering is 3D (Three.js) and the FPV vision check renders the 3D scene. Fixed step dt = 0.025 s (40 Hz), one constant that every layer reads, never a wall clock. Every actuation delay must be an integer multiple of dt (carrier, parts_runner and tech_repair 0.10 s are 4 ticks, the forklift 0.15 s is 6 ticks). The loader rejects a config that breaks this. The lidar runs at 10 Hz, every 4 ticks.
- Seeds: one root seed per run. Independent streams per entity and per subsystem come from numpy `SeedSequence.spawn`, so adding an entity does not change the other streams. A generator is built only from a spawned child, with `default_rng(child)`.
- Determinism scan: a test parses the sources of `waggle.sim`, `waggle.control` and `waggle.validation` with `ast` and rejects global `random`, `time`, `datetime`, network, `os.urandom`, `uuid`, `secrets`, global numpy random functions, `np.random.seed`, `default_rng` without a `SeedSequence` child, builtin `hash()` on strings, and iteration over a set when building state or the hash. Comments and strings must not cause false positives, and fixture sources check each forbidden construct.
- State hash: a canonical serialization with sorted keys and floats rounded to a fixed number of decimals (documented next to the code). No golden hash values are committed. Determinism tests compare two runs in the same process. Every result file records the numpy version and the platform.
- Reproduction scope: exact reproduction holds on the same platform and numpy version. Published results come from the cloud run (Linux).
- Ground truth versus observation: `waggle.control` never reads ground truth. It may import only two leaf modules of `waggle.sim`: `waggle.sim.observations` (observation types) and `waggle.sim.params` (frozen dataclasses with the robot class parameters, which a robot knows about itself). Everything else in `waggle.sim` is forbidden to control, including world, detector, sensors, humans and robots. Leaf modules import nothing from the forbidden side, and `waggle/sim/__init__.py` imports nothing, because import-linter also flags indirect chains. The contract `control-no-ground-truth` lists every other module of `waggle.sim`, and a test fails when a module is added without being listed. Streams are built with `SeedSequence(root_seed, spawn_key=(subsystem_index,)).spawn(count)`, so the i-th stream of a subsystem does not depend on how many are spawned.
- Detector conventions: closed sets, so an exact touch counts as contact. Contact is a collision. Separation below the declared margin is a violation. The human footprint is a disc with a radius of 0.30 m by default (assumption), or an oriented rectangle declared per scenario (a disc or an oriented rectangle). Robot footprints are oriented rectangles per class (length and width are assumptions to calibrate, see ARCHITECTURE.md).
- Kinematics are non-holonomic. Forklift: bicycle model with a wheelbase and a maximum steering angle that give the minimum turning radius (default 1.6 m and 0.569 rad, which give 2.5 m, an assumption inside the 1.5 to 2.5 m range). Carrier, parts_runner and tech_repair: differential drive with a maximum angular speed (about 1.5 rad/s, per class in ARCHITECTURE.md). Optional forklift parameter `load_raised` lowers maximum speed and the deceleration limit by documented factors (assumption).
- Stationary actions PICK, HANDOFF, DELIVER and DISPATCH_REPAIR have durations that are simulation parameters recorded in the scenario config (assumptions).
- The simulation state type is the same for ground truth and for belief states. The difference is what populates it.
- Scenarios carry a flag `unavoidable_at_spawn`, computed from geometry. E1 reports those cases separately (EXPERIMENTS.md).
- Stopping distance bound (B4). Integration is explicit Euler: position and heading advance with the speed and heading at the start of the tick, then the speed moves toward the command by at most `a*dt`. A stop command issued at a steady speed `v` becomes active after `delay_ticks` ticks, so the quantization of the delay to ticks adds no error: the robot covers exactly `v*t_r` with `t_r = delay_ticks*dt`. During braking the speeds at the start of the ticks are `v - k*a*dt`, for `k = 0` to `n - 1`, with `n = ceil(v/(a*dt))`. With `m = v/(a*dt)` the covered distance is `a*dt^2*(m*n - n*(n-1)/2)`, and the continuous distance is `v^2/(2a) = a*dt^2*m^2/2`. Their difference is `a*dt^2*(n - (n-m)^2)/2`, and since `0 <= n - m < 1` this lies in `(a*dt^2*(m-1)/2, a*dt^2*(m+1)/2]`. So the simulated stopping distance differs from `v*t_r + v^2/(2a)` by at most `v*dt/2 + a*dt^2/2`. Path length is the sum of the step lengths, so the bound also holds in a turn. The B4 property test uses this bound, and on the four classes at full speed the observed error is 98 percent of it (measured, so the bound is tight).
- Detector tolerance (B6). A step is checked as a continuous interval in the frame of the second body and cut into pieces that turn at most 0.005 rad; each piece is the convex hull of two footprints, reduced by the rotation sagitta. A Hypothesis property test compares it with a brute-force fine-substep check (400 substeps): there are no false negatives, and the exact gap is smaller than the fine one only by a documented bound. In a measurement over 1500 random cases the largest difference was 1.58 mm, which is 70 percent of the bound. Grazing cases within that bound can be reported as contact when the fine check sees a gap of a few millimeters.
- Metric unit (Phase 2). A collision, a separation violation and a near miss are counted as distinct contact episodes: a contiguous run of ticks in that condition between the same two entities counts once, and a new episode starts only after at least one tick outside the condition. The detector keeps one flag per pair and kind in a state array, so a fork and a replay count the same. Checked on 2026-10-30: the Phase 1 baseline file already counts episodes (hand-built tests: a 40-tick stay counts once, a second contact counts again, two overlapping robots count once), so no result needed regeneration. `unavoidable_at_spawn` is true when a human starts inside the stopping distance of a robot at its speed cap plus half its length plus the human radius, and tests cover both the true and the false side.
- Corners (B4). A forklift follows a bicycle model, so its turning radius never falls below `wheelbase / tan(max_steer)`, at any speed. A differential drive turns with a radius of `v / max_angular_speed`. In a 90 degree corner of an aisle 2.4 m wide, the reference point may stray from the centerline by `(aisle width - robot width) / 2`. The measured sharpest left turn strays 0.73 m for the forklift against 0.65 m allowed, and 0.375 m for the carrier at full speed against 0.8 m allowed. This is a centerline check. The swept-footprint check with the detector comes in B6.

Consequences: results are comparable run to run on one platform and are not claimed bit-identical across platforms. The lidar rate and the delay rule are checked at load time, not at run time.

## ADR-022: Agents push task branches and open pull requests

Status: accepted (maintainer decision, 2026-10-29). It supersedes the "the maintainer pushes" part of AGENTS.md section 2.

Context: this is a hackathon with a fixed deadline, and waiting for the maintainer to push each branch and open each PR slows delivery.

Decision:
- Agents push their own task branch and open the PR with `gh pr create`, using the PR text from AGENTS.md section 2.
- Unchanged: agents never merge, never push to `main` or `master`, never force push, never delete remote refs, never create or change remote repositories. The maintainer reviews and merges.
- The PreToolUse guard (`tools/hooks/safety_guard.py`) allows only `git push [-u|--set-upstream] origin <branch>` with an explicit branch named type/short-description (types feat, fix, test, docs, exp, chore, ci) that is not main or master. It denies a bare push, any other flag (force, delete, tags, all, mirror), refspecs, `HEAD` and tag names, and any push or `gh pr create` while the current branch is main or master or the HEAD is detached. `gh pr merge` is denied.
- Before it allows a push or `gh pr create`, the guard runs `tools/ci/pre_push_check.py` (standard library only): `uv run ci` must have passed on the current HEAD (a stamp under `.git/`) with a clean working tree, gitleaks must find nothing in the commits not yet on the remote, and those commits must contain no `.env` file and nothing under `results/**/heldout/`. If gitleaks is missing or any check cannot run, the push is denied.
- Before each push the agent runs `uv run ci` and checks the diff for secrets and held-out results (AGENTS.md section 2, Git rule 11).

Consequences: a pushed secret cannot be taken back by deleting a later commit, so the pre-push check is mandatory. Branch protection (PENDING 19) is now the main control on `main`.

## ADR-023: Crisis replanning with counterexample-guided validation

Status: proposed. Designed, not implemented.

Context: a compound fault (a machine overheats and sets a geofence, an aisle is blocked, a robot dies mid hand-off, urgent orders arrive) needs a new plan. An LLM can propose one, but it cannot be trusted to know whether the plan is safe.

Decision:
- Muse Spark receives a structured world summary, retrieved SOP excerpts (fenced as untrusted data), an optional obstacle class from vision, and the operator request or a text incident report. It proposes a plan in the schema of ARCHITECTURE.md (Plan schema).
- The validator builds a belief state from what the control layer may know at t = 0: the static map, the entities currently tracked from lidar, and K seeded human variants (default K = 5, streams spawned from the snapshot RNG state). The variants include humans spawned inside initially occluded regions, consistent with the declared density of the scenario. A sampled variant is rejected at sampling when it puts a human inside the minimum stopping distance of a robot at t = 0, because no plan can fix that. The validator does not fork ground truth. Snapshot and fork of the true state exist for determinism tests and replay only.
- The rollout runs the same dynamics as execution: simulated 10 Hz lidar raycasting against the belief state, the dynamic occlusion-boundary speed cap (ADR-024), the fast reflex layer and the in-memory lease logic, over H simulated seconds (default 45, configurable). Occlusion boundaries are recomputed from the simulated robot pose at every lidar tick of the rollout. They are never frozen as static phantom entities from t = 0.
- Acceptance. A plan is accepted only if, in every one of the K rollouts over [0, H]: zero collisions, zero separation violations, zero hazard geofence intrusions, zero deadlocks (acyclic wait-for graph), no lease conflict, and the route is feasible. Progress is also required: every robot with an active node either completes a node, strictly reduces its remaining geodesic route length, strictly decrements its stationary action timer (PICK, HANDOFF, DELIVER, DISPATCH_REPAIR), or waits legitimately on an acyclic dependency edge or on a lease whose holder makes strict progress toward releasing it. At t = H the state must be recoverable: each robot is either stopped outside shared capacity-1 zones or holds valid leases for its occupied and next committed segments. Mission completion within H is reported as a metric and is not required.
- Receding horizon: execute at most H/2 simulated seconds, then revalidate from the new belief state.
- Counterexample types: COLLISION, SEPARATION_VIOLATION, GEOFENCE_INTRUSION, CORRIDOR_DEADLOCK, LEASE_CONFLICT, ROUTE_INFEASIBLE, NO_PROGRESS, UNSAFE_TERMINAL_STATE. Fields, in SI units: time, place, entities, minimum clearance, violated rule. ROUTE_INFEASIBLE names the undeclared capacity-1 corridor that the route needs, or the avoided zone that cannot be avoided. Maximum 3 iterations. If no plan passes, escalate to the operator and the affected robots hold safely.
- Naming: simulation-based plan validation with counterexample feedback. It is not formal verification and not a safety proof. The assumptions are the hidden human prior, the K variants and the horizon, and they are stated with every result. Safety against humans stays in the reflex layer, which runs inside the rollout. CEGIS and LLM-Modulo are prior art to verify and cite. The pattern is not claimed as new.
- Lidar gives free-space geometry. Vision, when present, gives only an obstacle class and a label check mapped through SOP text. Every crisis scenario has a text incident report as fallback.
- The rationale field of a plan is logged for the operator and never forwarded to another model.
- Plan schema (full table in ARCHITECTURE.md). A plan has `mission_id` (set by code), at most 20 nodes, a free-text rationale, `escalate` and an escalation reason. A node has a unique label, `robot_id`, an action (MOVE, PICK, HANDOFF, DELIVER, DISPATCH_REPAIR), `target_zone_id`, `corridor_zone_ids` (ordered capacity-1 corridors), `avoid_zone_ids` (can only add avoidance), `wait_for` (acyclic labels), `item_id` and `speed_cap_mps` (can only reduce speed). Unknown fields are rejected, and ids are validated against the map, the fleet and the inventory in code. Idempotency keys and task ids are derived by code from the mission id and the node, never produced by the model.

Consequences: a new package `waggle.validation` (Phase 5C), a rollout cost that is measured in Phase 1 (ADR-025), and the experiment E10. Threats T17 and T18 cover an unmodeled human and indirect injection into the planner.

## ADR-024: Occlusion-aware speed cap

Status: proposed. Implemented in B14, see the end of this record.

Context: a lidar cannot see behind a rack. A robot that follows only the detected objects can meet a human who steps out of the shadow.

Decision:
- For each occlusion boundary derived from the lidar scan, assume a phantom human at the nearest possible point approaching at v_h.
- Cap the speed at the largest v such that S_sep(v) is at most the distance to that boundary along the swept curvilinear path.
- Edge cases: if there is no non-negative root (v_h*t_r + C is at least the distance), the cap is zero. Near zero speed the curvature term uses a minimum speed floor. Every discontinuity threshold is a documented parameter with its rationale. There are no other new parameters.
- The cap can only reduce speed. The cost is throughput, reported in E1.

Consequences: E1 adds the configuration swept footprint plus occlusion cap. The same cap runs inside the rollout of ADR-023.

Implementation in B14 (`waggle.control.occlusion`), with the choices the first text left open:
- Boundary: for every pair of neighbouring rays whose ranges differ by at least `jump_min` (0.6 m, twice the human radius, assumption), the nearer return is a boundary point. A ray with no return reads `max_range`, so a rack edge next to open floor is a boundary. Dropped rays are filled as in perception and make no boundary. The phantom sits at the boundary point itself, the nearest place a person can be hidden, so the cap is conservative.
- Cap: the largest `v` with `interp_k * S_sep(v)` at most the swept path gap to the boundary points. The footprint is widened by `v_h * (t_r + v / a)`, the distance a person covers toward the path while the robot reacts and brakes from `v`. Without this a corner beside the lane would never bind. The widening uses existing quantities, no new parameter. The widened condition stays monotone in `v`, so the root is found by 40 bisections, which is deterministic.
- Boundaries farther than `interp_k * S_sep(v_max)` plus the widening and the footprint are dropped before the search.
- `speed_floor` (0.05 m/s, assumption) sizes the turning circle of a differential drive when the requested speed is near zero. A request that does not move (speed zero) is not limited, so a rotation in place is not blocked by this cap.
- The cap enters `limit_command` through `extra_limits`, the same arbiter, reason `OCCLUSION`. It is switched on by `ControlInputs.use_occlusion` (configurations 5 to 7 of ADR-028).
- Known cost: a single return at a wall end is also a human candidate for perception (extent zero), so the envelope can already slow the robot there. E1 reports both as false stops.

## ADR-025: Simulator state layout and rollout cost

Status: proposed. Designed, not implemented.

Context: the validator runs K rollouts of H seconds for every plan and every iteration. If a rollout is slow, the design fails.

Decision:
- The state is a structure of contiguous numpy arrays (poses, velocities, zone tokens and expiries) plus a small dict of RNG states, with `snapshot()` and `from_snapshot()`. No deepcopy and no JSON in the hot path.
- No timing figure is written in the documents. The rollout cost is measured in Phase 1 and reported as code speed on this machine.
- Optimizations are considered only if the measurement demands them, each documented as a deviation: a lower lidar rate inside rollouts, cached static visibility, process-level parallelism across the K variants.
- The lidar model is a pure function over geometry arrays (static map, dynamic footprints, pose, params, rng), so the validator can reuse it on a belief state.

Consequences: B3 (feat/sim-core) implements the state layout and measures the empty loop and a fork rollout. If the measured cost makes ADR-023 doubtful, work stops and the maintainer is asked.

Deviations applied in Phase 2 (B10), each measured:
1. Detector: the broad phase is vectorized over all robot-human and robot-robot pairs, and the exact narrow phase (swept pieces of at most 0.005 rad, closed sets, rotation sagitta) runs in numpy batches in `waggle.sim.hullgap` with pieces laid out without padding. A pair is first checked by the best separating hull edge, and the exact distance is computed only when that clearance is within the sagitta bound. The scalar functions stay as the reference in `waggle.sim.detector` and the tests compare both. Check: the no-control E1 baseline on the 90 development runs gives identical counts and identical final state hashes before and after.
2. Rollout lidar (`waggle.sim.fastlidar`): static ranges are cached per position cell (0.05 m) on a world-frame grid of 720 rays, and a scan is a rotation of the cached vector by the heading. Human discs and robot rectangles are resolved per scan with exact ray tests only inside the angular window of their bounding circle and combined by minimum; this part equals the reference to 1e-9. Quantization: the origin moves by at most 0.035 m and the heading by at most 0.25 degrees. Measured on S14 robot poses against the exact static ranges: median error 0, p90 below 5 cm, p99 below 15 cm, and about 0.1 percent of rays differ by over 1 m (a different surface at a rack corner). Grazing rays can exceed the first-order bound (shift + range times heading shift) divided by the cosine of the incidence angle. The cache is keyed by cell only, so results do not depend on scan history. The exact lidar stays the one used in execution.
3. Parallel variants (`waggle.sim.rollout`): `concurrent.futures.ProcessPoolExecutor`, each variant a pure function of its spec, results returned in spec order. Tests show parallel equals serial.
Not done: kinematics were already vectorized across robots; the human walkers and the waypoint driver are still per-entity Python (about 0.8 s of 5.7 s).
Outcome: 3.1x measured against a 5x minimum and 2.0 s per rollout target. Stopped for the maintainer. Options: accept 5.7 s per rollout, lower K, H or the lidar rate for the live demo only, vectorize the human walkers and driver (about 10 percent more), or run variants in the cloud on more cores.


## ADR-026: Perception and tracking

Status: proposed. Implemented in B13, with the deviations listed at the end of this record.

Context: `waggle.control` reads only `waggle.sim.observations` and `waggle.sim.params` (ADR-021). It has no map. Everything it knows about humans comes from a `LidarScan`, a `RobotOdometry`, and optionally `BeaconReport` items.

Decision:
- Input per robot and tick: the latest `LidarScan`, the `RobotOdometry`, the beacon reports, and the class parameters. Output: a list of tracks in the world frame, each with id, position, velocity estimate, an uncertainty radius, a size class and an age.
- Stale or missing scan: a scan is stale when `tick - scan.tick` exceeds `max_scan_age_ticks` (8 ticks, two lidar periods, assumption). A missing or stale scan, or a scan with more than 20 percent NaN rays, makes the perception result `INVALID`. The layer fails closed: the speed limit is zero and the reason is `SCAN_INVALID`.
- Dropped rays: a NaN ray takes the smaller of its two nearest valid neighbours within 2 rays. With a valid neighbour on one side only it takes that one. With none it takes range zero. This can only make an obstacle look closer.
- Points and clusters: each valid ray with a return below `max_range` becomes a world-frame point using the odometry pose. Consecutive points form a cluster while the gap is below `gap_base + gap_per_meter * range` (assumptions, declared in `waggle.control.params`). Rays with no return are not points, and their boundaries are the occlusion boundaries of ADR-024.
- Size class: a cluster whose extent is at most `human_max_extent` (1.0 m, assumption) is a human candidate. A larger cluster is a structure. The layer has no map, so a robot or a rack end can look like a human candidate. That costs throughput, never safety, and E1 reports it as false stops. A beacon report inside the gate of a cluster marks the cluster as a human.
- Tracking: nearest neighbour association with a gate of `v_h_max * dt_scan` plus the uncertainty radius (assumption), a constant velocity estimate from the last two associations with exponential smoothing, own motion removed with the odometry. A track that is not seen keeps coasting for `max_coast_scans` and its uncertainty radius grows by `v_h_max` times the time since seen. After that it is dropped and the area is covered by the occlusion cap, not by the track.
- `v_h_max` is the human speed bound used by the separation formula (1.6 m/s, assumption, to calibrate).
- Pure function with explicit state: `perceive(state, inputs) -> (state, tracks)`. No wall clock, no global random, deterministic.
- Static structures are never classified as safe: they stay in the point set and the swept footprint check stops the robot before contact (ADR-027).

Consequences: B13 (`feat/control-tracking`) implements this with tests for stale scans, NaN rays, merge and split of clusters, coasting and gating. The tests use `LidarScan` values built by hand (`tests/support/control_support.py`), never the simulator internals.

Deviations in B13, each deliberate:
- A beacon does not mark a cluster. A beacon within `beacon_sigma + human radius + v_h_max * delay` of a human-sized cluster is absorbed by that cluster. Any other beacon becomes its own detection, also when it lies beside a structure, and the structure stays a structure. Same effect, no reclassification of a large cluster.
- A track is covered by a ring of `ring_points` points at the body radius (at least the human radius) plus the position sigma plus `v_h_max` times the time since it was seen. The ring is used even for a fresh track, so the scan delay is covered. It is more cautious than the visible surface, and E1 reports the cost as false stops.
- The extent of a cluster is measured on the returns that exist. Rays are 1 degree apart, so a disc of 0.6 m at 3 m reads about 0.5 m. This is why the human size limit is 1.0 m and not 0.6 m.
- Velocity comes from the last two detections with exponential smoothing and is clipped to `v_h_max`. Beacons arrive every tick with noise, so their velocity is noisy. Only CPA (B15) uses velocity, and it must smooth over more than one tick.
- Odometry older than `max_scan_age_ticks` is `INPUT_MISSING`, and a scan from the future is `SCAN_INVALID`.
- `control_step` is in `waggle.control.step`. It leaves the state unchanged on bad input, and an exception inside it is logged and stops the robot with `INPUT_MISSING`.

## ADR-027: Control interface and limit arbitration

Status: proposed. Partly implemented in B12 (types, params, envelope, arbiter, limiter); `control_step` is assembled in B13 once perception exists.

Context: every motion command passes through the fast layer and can only be reduced. Several limits act at once (envelope, occlusion cap, CPA, geofence, watchdog, advisors later). Their interaction must be order independent and testable.

Decision:
- Interface: `control_step(state, inputs) -> (state, output)`. `ControlInputs` per robot: the requested command (speed, and steering angle for the forklift or angular speed for the other classes), odometry, scan, beacons, heartbeat tick, active geofences, telemetry flags, the class parameters and the tick. `ControlOutput`: the limited command, the limit that bound, and a `reason` code for every limit that was below the request.
- Arbitration: the output speed is the minimum over the requested speed, the class maximum, the envelope cap, the occlusion cap, the CPA cap, the geofence cap, the watchdog cap and any advisor cap. A minimum is order independent, and a new limit never raises the result. The layer never raises a limit or the speed above the request. Zero wins over any other value.
- Direction: a reverse request is limited in magnitude with the same rules. The sign is never changed.
- Curvature: for the forklift (bicycle model) the curvature depends on the steering angle only, so the speed is reduced and the steering is left alone. For differential drive the curvature is `omega / v`, so the angular speed is scaled by the same factor as the speed, and the path stays the same. A stop keeps the steering and sets the speed to zero.
- Reflex: when the gap to a human candidate or a structure along the swept path is at most `S_stop`, the output is a stop. The simulator applies the class deceleration limit, so the layer never commands a deceleration the robot cannot do.
- The layer must fail closed: a missing field, an invalid scan, a stale heartbeat or an exception in a limit function gives a limit of zero with its reason. The exception is logged and not swallowed, and the step still returns an output.
- Reasons are a closed enum (`REQUEST`, `CLASS_MAX`, `ENVELOPE`, `OCCLUSION`, `CPA`, `GEOFENCE`, `WATCHDOG`, `SCAN_INVALID`, `INPUT_MISSING`, `ESTOP`), recorded per tick in the run log so E1 can attribute each stop.
- Purity and latency: `control_step` reads no clock. The harness measures its code latency around the call with a monotonic timer and reports it as code latency (ADR-028).
- Separation formula, per class and human candidate at distance `d` along the swept path: `S_stop = v*t_r + v^2/(2a)` and `S_sep = v_h*(t_r + v/a) + S_stop + C`, with `C` a margin per class (assumption, to calibrate). The cap is the largest speed `v` with `k*S_sep(v) <= d` (k = 1.5, assumption), solved in closed form from the quadratic. It is full speed when `d >= k*S_sep(v_max)` and zero when `d <= k*S_sep(0)`. The first wording of this ADR, a linear ramp between `k*S_sep` and `S_sep`, was replaced in B12 because a ramp on `S_sep(v_max)` stops the robot far from a human at any speed. Structures use `S_stop(v) + structure_margin <= d`. A gap inside `S_stop` at the current speed is a stop with reason `ESTOP`.

Consequences: B12 (`feat/control-envelope`) implements types, the envelope, the arbiter and `limit_command` (envelope plus arbiter on detections in the robot frame; a swept mode and the radial mode of E1 configuration 1) with property tests, and checks the swept gap against an independent brute-force sweep of the footprint: result at most each limit, invariant to the order of the limits, never above the request, zero wins, same factor on speed and angular speed. The failing run is shown first. B16 adds the reflex items (heartbeat, geofence, e-stop, telemetry threshold) as further limits in the same arbiter.

Reflex layer in B16 (`waggle.control.reflex`), each item one more limit in the same arbiter:
- Watchdog: the heartbeat tick is valid when `0 <= tick - heartbeat <= heartbeat_timeout_ticks` (40 ticks, 1 s, assumption). A missing, stale or future heartbeat gives zero with reason `WATCHDOG`.
- E-stop: a boolean input gives zero with reason `ESTOP`.
- Watchdog and e-stop need no scan and no pose, so they are added also when the scan or the odometry is invalid. The arbiter ranks `ESTOP` and `WATCHDOG` above `SCAN_INVALID` in the reason it reports, and every reason that was below the request stays in `limits_hit`.
- Geofence: a polygon in the world frame (static or set dynamically by the caller). Its edges are sampled every `edge_spacing` (0.2 m, below the footprint half width) and the cap is the structure rule on the swept path gap to the samples, so the robot stops short of the edge. A robot whose footprint already touches a fence may only creep at `escape_speed` (0.3 m/s, assumption) so it can leave. A fence with fewer than three vertices or a non-finite vertex gives zero. A request that does not move is not limited by a fence, so a rotation in place near an edge is allowed (the swept circle of the rotation is not checked against fences).
- Telemetry threshold to geofence: a reading at or over `warn` sets a polygon around its source that contains a disc of `warn_radius` (1.5 m), over `critical` or not a number a disc of `critical_radius` (3.0 m). Both radii are assumptions. The polygon has 16 sides and is built outside the disc.
- Switched on by `ControlInputs.use_reflex`. The inputs are `heartbeat_tick`, `estop`, `geofences` and `telemetry`. With the flag off none of them is read, which keeps the E1 configurations of ADR-028 unchanged.
- `waggle.control.frames` holds the world and robot frame changes that `control_step` used privately.

## ADR-028: E1 metrics and the eight configurations

Status: proposed. Harness implemented in B17 (`waggle.experiments`); development seed results come from the cloud workflow.

Context: E1 must show what each block contributes by ablation, not by summing blocks (AGENTS.md section 9). The Phase 1 baseline is the first configuration.

Decision:
- Eight configurations, same seeds, same scenarios S01 to S18:

| # | Name | Control | Sensing |
|---|---|---|---|
| 0 | `no_control` | none (scripted driver only) | none |
| 1 | `radial_lidar` | radial 1D distance to the nearest point | lidar |
| 2 | `envelope_oracle` | swept footprint envelope | oracle scan |
| 3 | `envelope_lidar` | swept footprint envelope | lidar |
| 4 | `envelope_lidar_beacons` | swept footprint envelope | lidar plus beacons |
| 5 | `envelope_occlusion_lidar` | envelope plus occlusion cap | lidar |
| 6 | `envelope_occlusion_cpa_lidar` | envelope plus occlusion cap plus CPA | lidar |
| 7 | `envelope_occlusion_cpa_lidar_beacons` | envelope plus occlusion cap plus CPA | lidar plus beacons |

- The oracle scan is the same `LidarScan` type with zero noise, zero dropout and no occlusion shadow, produced by `waggle.sim.sensors`. The control code does not change between sensing configurations and never reads ground truth.
- Ablation pairs: 0 against 1 is any control; 1 against 3 is the swept footprint; 2 against 3 is the cost of real sensing; 3 against 4 is beacons; 3 against 5 is the occlusion cap; 5 against 6 is CPA. Envelope with CPA but without the occlusion cap is not run, and the report says so.
- Metrics: collisions with humans, collisions between robots, near misses, separation violations (episodes, definitions of ADR-021), unavoidable cases listed separately, false stops, throughput, code latency.
- A false stop is a stop episode (speed limit of zero while the request was above zero, from the reason log) that starts while the true gap to every human is above `false_stop_gap_m` (3.0 m, assumption). The raw count of stop episodes by reason is reported next to it.
- Throughput is waypoints reached per simulated hour, the proxy for tasks until Phase 3 has tasks. It is reported as a ratio to `no_control` on the same seeds.
- Latency is code latency of `control_step` per robot tick (median, p99, maximum), measured on this machine or in the cloud runner and labeled so. It is not a real-time guarantee.
- Proportions with Wilson 95% intervals and raw counts. Every failing seed is listed. Small samples are called small: 90 development runs per configuration, 720 in all.
- Scope of B17: development seeds only, one run per configuration and seed, results in `results/e1/dev/`. Held-out seeds run once per configuration after the maintainer approves, in the cloud. The full 720 runs are a cloud job (AGENTS.md section 3, rule 8).

Consequences: B17 (`feat/e1-harness`) adds the harness and `uv run report`. Each result file records commit, seed set, numpy version, platform and date.

## ADR-029: Test tiers, rollout optimization approval and approved dependencies

Context: the maintainer answered PENDING 26, 29, 30 and 31 at the start of Phase 2.

Decision:
- `uv run ci` is the fast tier and must finish in 3 minutes or less on the maintainer machine. Measured on 2026-10-30: 1 min 46 s, 988 tests. If it grows past the limit, the slow tests get the `heavy` marker, never a silent exclusion. The pre-push check keeps requiring the fast tier locally plus gitleaks. Heavy tests, seed sweeps and held-out experiments run only in the cloud workflow.
- The rollout cost of ADR-025 (22.3 s for 45 s with 10 robots) is addressed by measurement: profile first, then vectorized kinematics with a broad phase, a cached static lidar with world-frame rays indexed by heading, and process-level parallelism across the K variants. Each is documented as a deviation in ADR-025. The exact lidar stays in execution. No new dependency such as numba. If the best result is below 5x, work stops and the profile is reported.
- Dependencies approved, to be added only by the branch that needs them: fastapi and uvicorn[standard] as runtime dependencies of `waggle.api` only; in `web/`, Node, Vite, TypeScript, three, @types/three and Playwright as dev dependencies, with a committed lockfile and `npm ci`. When `waggle.api` exists, import-linter contracts forbid `sim`, `control` and `validation` from importing `waggle.api` or any web library.
- E9 is regression detection (mutation testing and planted defects). E10 is crisis replanning.
- AGENTS.md git rule 3 now reads: every commit passes the fast CI, and a test and the code that makes it pass go in the same commit.

Consequences: intermediate red commits in published history stay.

ADR-025 addendum, maintainer decision on PENDING 31 (2026-10-30, recommended mix): the measured 5.7 s per 45 s rollout is the design basis (K = 5, H = 45 s, lidar every 4 ticks). Variants for E10 and held-out runs run in the cloud. K, H or the lidar rate may be reduced for the live demo only, and the reduction is labeled in the demo. The walkers and driver are not vectorized now.
