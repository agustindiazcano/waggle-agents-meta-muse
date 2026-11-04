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

ADR-028 addendum, maintainer decision on PENDING 45 (2026-10-30, options A and C): the fast layer keeps treating other robots as static structure. No relative velocity model for robots is added to `waggle.control`. E1 dev run 4 (cloud run 41100237070) measured the cost: in the 10 and 30 robot scenes (S14, S15, S17, S18) the speed over request is 0.04 to 0.26, because a follower waits for a full stopping gap behind a moving leader, and these scenes carry about 80 percent of the distance of `no_control` (16207 of 19893 m). The README and any E1 table report that number with this cause and do not hide it behind the aggregate. Robot to robot traffic is handled in Phase 3 (leases, zone and corridor locking, E2), not in the fast layer. Revisit only if E2 shows that traffic control does not remove the queues.

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

## ADR-030: Map-aware human classification

Context: the first E1 development run (cloud run 41086309588) gave throughput between 0.01 and 0.34 of `no_control`. In S08 with the oracle scan the cause was perception: wall and rack faces seen at an oblique angle split into clusters under `human_max_extent`, became human tracks, coasted up to 80 ticks with a ring growing at the human speed bound, and triggered ESTOP with the real human 10 m away.

Decision (maintainer approved the strict version, 2026-10-30):
- `ControlInputs.map_segments` carries the static map (walls, racks, bounds) as an (S, 4) array. The default is empty, which keeps the previous behavior.
- A cluster is not a human candidate if every one of its points lies within `PerceptionParams.map_margin` (0.25 m, an assumption) of a mapped segment. One point off the map keeps the cluster a person. The cluster then counts as structure.
- The margin covers the lag between scan and odometry. It stays below the 0.3 m body radius, so a person standing against a wall and seen along it (visible arc up to 0.6 m deep) is still a track. Tests cover that case and a person away from the wall.

Update after the second E1 development run (cloud run 41095424297): without the occlusion cap the filter raised runs with a human collision (envelope_lidar 11 to 21 of 90, envelope_oracle 13 to 24, envelope_lidar_beacons 12 to 36), because false human tracks near walls had acted as extra margin for people leaving cover. With the occlusion cap the counts stayed at 12 of 90. Maintainer decision (option C): the filter is active only when `use_occlusion` is on. Without the cap the previous behavior holds. The beacon jump to 36 of 90 is not explained yet.

Consequences: a person who is seen only through a sliver within 0.25 m of a wall plane is read as wall. This is a known loss of safety for lower false stops. The occlusion cap and beacons do not cover it. It is measured by the next E1 run, not assumed. Single-ray clusters at 0.16 to 0.2 m from the map were the reason for 0.25 over 0.15. S03 (two robots head on in a one-lane corridor) is not a perception problem: it is a deadlock that belongs to corridor locking (Phase 3, E2).

## ADR-031: Pure lease and atomic corridor model

Context: Phase 3 starts with a deterministic reference model before persistence. S03 has two robots facing each other in a capacity-one aisle. Stopping after both enter cannot resolve that geometry; admission must happen before entry. Threat T7 is a worker that resumes with an obsolete grant.

Decision:
- `waggle.coordination.leases` holds frozen `LeaseState` and `LeaseResult` objects. Every operation receives `now_tick`; no clock, database, network or random source is read. Ticks are nonnegative integers and cannot move backwards relative to returned state. Callers must retain the returned state even on denial. Invalid configuration or malformed state raises `ValueError`; authorization checks return false for missing, stale or invalid credentials.
- A lease defaults to 400 ticks (10 s at the current simulator's 40 Hz), an assumption to calibrate on development seeds. Callers can supply a positive duration explicitly. Its validity interval ends just before `expires_tick`: at that tick it is expired. A new grant increments a resource's positive integer token; renew keeps that token and never shortens expiry. Revoke and expiry retain the last token. Never recreate a resource with token zero after it has been used. The credential is `(resource_id, holder, token)`, scoped to one resource, not a secret or an authenticated identity.
- `check_token` accepts only the exact live holder and current token, not a future token or just a token greater than a floor. Generic leases represent logical ownership only. Physical corridor clearance is handled separately by `waggle.coordination.corridors`; generic `expire` must not be used to authorize corridor entry.
- A corridor request names its complete resource set and one direction (forward or reverse relative to a fixed route orientation). All resources are granted or none are. Resources are stored and acquired in sorted resource-id order. The first serialized eligible request wins; there is no queue or fairness guarantee in this branch. A holder cannot expand its reservation, acquire a disjoint second bundle or reverse direction while holding resources. It must leave and release the complete bundle first. Retries return existing tokens without extending expiry. This prevents hold-and-wait cycles for this model; it does not solve robots already face to face inside an aisle or motion outside reserved corridors.
- Occupancy is explicit trusted input, never inferred from lease expiry. Each zone needs an observation at `now_tick`. Missing, older, future or unknown occupancy fails closed. Empty means clear; an expired lease with an occupied or unknown zone retains its previous holder and direction as `FAULT_OCCUPIED`. No token for that zone is usable after expiry. A later current empty observation permits expiry and reassignment with a new token. Release also requires empty occupancy and all live tokens. A robot that never releases stops blocking an empty corridor at expiry; one physically stuck inside requires recovery and replanning, not automatic admission of its opponent.
- S03-like unit tests put both robots outside the corridor: one receives the entire route, the other waits, then receives the route after the first leaves and releases. Hypothesis generates lease and corridor operation sequences to check monotonic tokens, stale-token rejection and mutual exclusion. The coordination package is included in the forbidden-import contract and scanned for clocks, network and global randomness.

Database contract for a later branch: persist resource rows and token history, lock every required row with `FOR UPDATE` in canonical order, and apply the complete transition in one transaction. Use a unique resource-id constraint and unique request/task ids to prevent duplicate processing (AGENTS.md section 7). Serialize a holder's reservations too, so concurrent disjoint requests cannot bypass the one-bundle rule. Derive holder identity from authentication. Check the current holder, token and expiry inside the tool with the same rows locked, immediately before its protected effect; a preflight call to this pure checker is insufficient (ADR-004). Keep occupancy evidence authoritative, latch occupied faults and trigger replanning. Recovery uses `FOR UPDATE SKIP LOCKED`, never clears a physically occupied zone on a timer, and closes transactions before long LLM or MCP calls. Audit timestamps remain `clock_timestamp()`. Resource counters must survive restart and never wrap or reset. Database implementation and any migration require a separate maintainer approval; neither is included here.

E2 measurement plan: after admission is integrated with the current simulator, map capacity-one aisles to corridor resource ids, call the pure model using the simulator tick, and hold robots before entry until their full route is granted. Use the independent simulator detector and zone occupancy to score S03 and deadlocks in S13 to S18, compare identical development seeds with coordination enabled and disabled, then compare the persistent implementation with this model under the protocol's 500 tasks, worker kills, early expiry, duplicate delivery and database delay. Count double assignments, simultaneous zone occupants, accepted stale writes, recovered and stuck tasks, deadlocks and recovery time; report raw counts, failing seeds and Wilson 95% intervals for proportions. Record commit, configuration and seed set. This branch runs no E2 experiment, no paid calls and no held-out seeds, and does not claim an improvement in simulator throughput or safety.

Consequences: the pure model is implemented, not evaluated. It is not a concurrent service and does not authenticate holders, move robots, enforce entry limits, persist state, implement A* or recover a physically blocked aisle. Those integrations remain separate work. No change is made to the fast layer, MCP boundary, audit logic or migrations.

### ADR-031 addendum: simulator admission integration (2026-10-30)

Decision: the simulator adapter lives in `waggle.experiments.corridor_admission`, leaving the pure checker and fast layer unchanged. Each robot requests its complete route in fleet-index order before it moves. A denial cancels queued and active motion commands, while the simulator still applies its declared braking dynamics. Lease expiry never means physical clearance. Occupancy comes from current ground-truth footprints against rectangular capacity-one zones; bounding boxes are conservative and exact contact counts as occupied. The adapter keeps token history, owner, expiry, observation tick and fault latch in simulator arrays. Admission-only snapshot and fork replay preserve those values; replay of the whole existing control rig is not established here.

The original S03 fixture and all E1 results remain unchanged. `build_s03_admission` explicitly constructs exterior staging and one-shot parking routes on the same map: the first robot starts south of the aisle, the opponent waits to the north-east, and the first parks to the north-west before releasing. This geometry prevents the parked robot from blocking the opponent's entry under the unchanged envelope. The route grants last 4000 ticks by default for this bounded fixture; a shorter occupied expiry is tested as a fault, not silently renewed. This does not handle arbitrary routes, initial moving robots, fairness, dense-fleet deadlocks or database failures.

Validation: `uv run pytest tests/unit/experiments/test_corridor_admission.py -q` passes 10 tests, including both robots completing, no simultaneous occupants, no robot collision according to the independent detector, all-or-nothing multizone admission, unknown occupancy denial, occupied expiry, release only when clear and admission state replay. The initial failing run reported the missing adapter module before implementation. These are integration and unit tests, not E2 measurements. Status: implemented, not evaluated. E2, paid calls, held-out seeds, database implementation and migrations were not run or added.

### ADR-031 addendum: simulator comparison harness (2026-10-30)

The S03 fixture accepts a strict boolean `admission_enabled`, defaulting to true. Disabling it removes only the admission engine system, retaining the same initial arrays, routes, streams, fast layer and dynamics. A unit test checks equal initial hashes and movement of the previously waiting robot when admission is disabled. The E2 simulator component uses paired development seeds, typed raw results and Wilson intervals, and is manual and cloud-only at its CLI. It does not implement the database no-fencing baseline or the full chaos protocol. Stall counts are explicitly not deadlock counts, and zone occupancy is sampled rather than continuously swept. No E2 sweep was run by this task. Status: implemented, not evaluated.

### ADR-031 addendum: deterministic aisle routing (2026-10-31)

Decision: `waggle.coordination.routing` provides a pure A* planner over a caller-supplied directed aisle graph. Nodes have finite map coordinates in metres. Every edge has a finite positive cost no lower than the Euclidean distance between its endpoints, so the straight-line heuristic is admissible. Stable node and edge ordering gives reproducible equal-cost choices. The result contains the node path, total cost and one atomic `CorridorRequest` for every capacity-one resource on that path. Each resource carries its own direction relative to that resource's fixed orientation.

The corridor model continues to acquire the entire resource set atomically, in canonical resource-id order, and checks exact direction on a retry. Legacy requests with one direction retain their existing behavior. A route that traverses the same resource in conflicting directions is rejected. The planner does not load maps, account for dynamic obstacles, or contact persistence; the S03 adapter is not wired to it. No fast-layer, fencing, MCP, database or migration behavior changes. Unit tests cover shortest paths, deterministic ties, unreachable goals, malformed geometry, route bundle construction and mixed-direction grants. Status: implemented, not evaluated by E2.

### ADR-031 addendum: graph binding to loaded maps (2026-10-31)

`waggle.coordination.map_graph` validates an explicit graph against a loaded simulator `World` before planning. Nodes need full declared clearance inside the map. Every straight edge must avoid walls and racks expanded by that clearance and name exactly the capacity-one resource its expanded segment touches. Boundary contact counts as intersection. The square expansion conservatively contains a disk; a caller must choose a radius enclosing the chassis at every heading. Unsupported nonrectangular geometry and edges touching multiple resources are rejected rather than repaired. Resource directions remain explicit caller metadata; geometry does not infer authority or orientation. The output is the existing A* plan plus waypoint coordinates excluding the start node. This does not generate graph topology, certify curved tracking or turning feasibility, handle moving obstacles, persist grants or change the fast layer. Status: implemented, not evaluated by E2. Tests first failed on the missing module; all 17 map-binding tests then passed.

### ADR-031 addendum: mapped S03 routes and direction restoration (2026-10-31)

`waggle.experiments.s03_routes` declares the S03 admission fixture's directed topology and binds it to the loaded map using a clearance equal to the carrier's footprint half-diagonal. A* produces both waypoint lists and complete per-resource requests. The builder rejects unreachable destinations or routes without the required reservation before constructing an engine. The node coordinates preserve the existing staging, approach and parking waypoints, so both sides of the admission ablation retain identical geometry, streams and initial hashes. The original E1 S03 remains unchanged. This is explicit fixture topology, not automatic map topology extraction or general fleet planning.

Admission state reconstruction now uses `request.direction_for(zone.id)` instead of one uniform direction. The regression first failed because a valid mixed-direction bundle was denied on its next tick; after the correction it retains admission and tokens while its opponent remains stopped. The five new routing and direction tests and the 85-test coordination/integration selection pass. Existing integration tests still cover completion and the independent collision detector. Status: implemented, not evaluated by E2. No fast-layer threshold, fencing checker, MCP boundary, audit, database or migration is changed.

## ADR-032: MCP boundary and guard design

Status: design only, proposed. No code, no migration, no `.env` change. The MCP boundary code, the audit logic and the fencing check are protected (AGENTS.md section 15), so each implementation branch below needs a maintainer go-ahead first.

Context: the MCP server is the only path from an LLM-directed organizer to a motion or inventory effect. Threats T1, T2 and T5 (tool escalation by prompt text, poisoned bounds, inter-robot commands) are met here, and T7, T8 and T14 (stale, duplicate or spoofed grants) are met by the fencing check inside the tool (ADR-004). The Architecture section "MCP boundary" lists the controls; this ADR fixes the order, the data contracts and the failure modes so the implementation can be tested first.

Decision:
- Order of checks per call, each failing closed with a typed error result and no forward: (1) authenticate, (2) allowlist, (3) schema and bounds, (4) rate limit, (5) write the intent row, (6) forward with a per-call timeout, (7) write the result row. A failure at 1 to 5 never reaches the tool. An exception inside dispatch becomes an error result (AGENTS.md section 6.5).
- Identity: each chassis has one bearer token generated outside the repository. The server stores only `sha256(token)` in `robot_identities` (hash, chassis, robot_id, revoked flag). Lookup is by hash; the stored and presented digests are compared with `hmac.compare_digest`. The token is high entropy and random, so a plain SHA-256 is enough and a slow password hash would add cost without benefit. `chassis` and `robot_id` come from the matched row. Any `chassis`, `robot_id` or identity field in the arguments or headers is ignored for authority, and a mismatch with the derived value is denied and audited. A missing, unknown or revoked token is denied. Tokens never appear in logs, audit rows or error text.
- Allowlist: a static table in code, `chassis -> frozenset[tool]`, not read from prompts, documents or the database. Unknown chassis or unknown tool is denied. Proposed starting table (assumption, the maintainer confirms): carrier and forklift `move_waypoint`, `pick_package`, `deliver_package`, `release_zone`, `get_task`; parts runner `move_waypoint`, `release_zone`, `get_task`, `get_inventory`; tech repair `move_waypoint`, `release_zone`, `get_task`, `open_ticket`; `reserve_part`, `dispatch_tech` and `create_purchase_order` belong to the maintenance workflow identity, not to a robot chassis. Carrier and forklift never get maintenance tools, and no maintenance-only tool is open to a motion chassis.
- Schemas: one frozen, strict model per tool, extra fields forbidden, types not coerced. Physical bounds are per chassis and come from the same parameter source as the simulator (`RobotParams`: `max_speed`, footprint, turning limits), not from the request. A waypoint speed above the chassis `max_speed`, a coordinate outside the map bounds, or a nonpositive quantity is denied, never clamped, so a clamp cannot hide an attack. Ids that code derives (idempotency key, task id, part number) are checked against their source (mission content, catalog) in code, never trusted from the model (AGENTS.md section 8.7).
- Rate limit: counted from `mcp_audit` rows per chassis in a sliding window, under the transaction-scoped advisory lock already described in Architecture, taken before counting and held until the intent row is inserted. The limit values are configuration with a default to calibrate. No count held in process memory.
- Audit: the intent row records correlation id, chassis, robot_id, tool, a hash of the validated arguments and the decision, and is written with `clock_timestamp()` before forwarding. If the write fails the call is denied. Denials are audited too, with the reason code, unless the audit write itself is the failure. The result row shares the correlation id and records outcome and latency. The request carries a `request_id` checked before any work: a repeat returns the stored result (AGENTS.md section 6.2).
- Fencing: tools that change a zone or task call the fencing check inside their own transaction with the row locked (ADR-004, ADR-031 database contract). The boundary does not re-implement it and does not accept a client claim that a token is valid.
- Guard (first screen, untrusted text only): sanitizers run first (length cap, control character and markup stripping, encoding normalization), then a classifier that returns a score. Voice transcripts, package labels, SOP text, manual text and inter-robot messages pass through it before any model sees them. If the classifier errors, times out or cannot score the input, the input is rejected and escalated to the operator inbox. The guard output is advice to the court and organizer; it never widens an allowlist, schema or bound. Which classifier to use (a rule set, a small model) follows parsimony: start with deterministic rules and add a model only if E3 shows the rules fail.
- Transport: stdio or HTTP is not decided here. A stdio server writes nothing to stdout except protocol frames (AGENTS.md section 5.11).
- Import contract: `waggle.mcp_server` does not import `waggle.governance` (already enforced). It may read `waggle.sim.params` for chassis bounds only if the maintainer approves that edge, otherwise the bounds are copied into a config table checked against `RobotParams` by a test.

Tests that the implementation branches must write first: constant-time compare used (no `==` on digests); revoked, unknown and missing token denied; identity fields in arguments ignored and mismatch denied; every (chassis, tool) pair in and out of the allowlist; each schema rejects extra fields and each bound at, just inside and just outside its limit; 30 simultaneous calls from one chassis respect the rate limit across two connections; intent write failure denies and does not forward; result row correlated; classifier failure rejects; a poisoned SOP or label naming a forbidden tool changes nothing. E3 is the injection matrix over T1 to T6, T11 and T18, run by ablation with each layer off against the same cases.

Branches, each needing a go-ahead on the protected parts: (a) `feat/mcp-schemas` pure schemas, bounds and allowlist table, no I/O; (b) `feat/mcp-identity` token hashing and lookup against an interface, no database; (c) `feat/guard-sanitizers` deterministic sanitizers and rules with the fail-closed classifier interface; (d) the audit and rate-limit repository with its migration, which needs migration approval (AGENTS.md section 15); (e) the server wiring.

Consequences: nothing is implemented or evaluated by this ADR. The allowlist table and rate-limit numbers are assumptions until confirmed. Denying out-of-bound requests instead of clamping may raise the denial count of an LLM organizer, which E3 and E4 will show. A single token per chassis means a leaked token is usable until revoked; rotation and revocation are covered by the revoked flag, and per-call signing is not added now.

### ADR-032 addendum: offline classifier contract (2026-10-30)

The guard interface is implemented in `waggle.governance.classifier`, without a provider or detector. It sanitizes and fences each input before calling an async protocol, validates a bounded strict JSON response (`label` and `reason_code` only, duplicate fields rejected), and delegates the label policy to the existing `screen()`. Only benign passes; uncertain, injection, malformed output, exceptions and timeouts reject and escalate. The returned rejection is a decision, not delivery to an inbox. The mock defaults to uncertain. Deadline expiry remains a rejection if an adapter swallows cancellation and returns benign. Adapters must cooperate with the event loop and apply transport timeouts in the future `waggle.llm` implementation. No MCP, audit, fencing or court behavior changes. Unit tests cover the failure paths; E3 detection performance is not evaluated.

## ADR-033: Persistent corridor reference implementation

Status: implementation authorized by the maintainer on 2026-10-31 as part of the mock plan. The maintainer separately approved `psycopg[binary]==3.3.6` on the same date. No paid provider, HTTP client or secret change is included.

Decision: use Psycopg 3 directly, without an ORM. Each operation opens, commits or rolls back, then closes its own connection with connect, statement and lock timeouts. The DSN is excluded from repr and application logs. Schema revision 1 is explicit, transactional and guarded by an expected-revision check under a database advisory lock. It contains only `zones`, an idempotent fenced event ledger and the schema revision. Migration never provisions resource ids; separate registration inserts missing resources without changing existing counters.

The repository calls the production pure corridor transitions from ADR-031. A shared topology lock excludes resource provisioning while a transition runs; a per-holder advisory lock serializes same-holder requests; all resource rows are then locked in sorted id order. Updating the whole model under this deliberately coarse lock scope avoids partial bundles and cross-request expansion. No concurrency throughput or large-fleet claim is made. Counters use PostgreSQL bigint; exhaustion raises and rolls back instead of wrapping or resetting.

The first protected effect is an event insertion, not robot motion. `record_event` holds the resource locks through exact live token validation and insertion. It rejects incomplete credentials and faulted zones. Event ids are unique. A matching repeat returns historical success without reinsertion; different content raises a typed conflict. Events use `clock_timestamp()`. Production MCP authentication, audit/rate-limit rows and tool effects remain separate work; a preflight call to this repository is not authority for an effect outside its transaction. Occupancy and simulation ticks must come from a trusted adapter. Task queue, workers, recovery and mission handoff are not implemented by this branch.

Verification: unit tests first failed on the missing database modules. The unit/configuration/workflow selection has 25 passing tests. Cloud-only heavy tests exercise real PostgreSQL with isolated schemas: revision mismatch and atomic DDL rollback, Hypothesis parity with the pure model, competing holders, concurrent disjoint requests from one holder, direction restoration, unknown occupancy, occupied expiry across repository restart, idempotent effects, integer overflow rollback and a row-lock-contended stale-token race. The workflow rejects a zero-test selection instead of treating it as success. [Cloud run 41217047545](https://github.com/agustindiazcano/waggle-agents-meta-muse/actions/runs/41217047545), on commit `7fa02c0`, passed all 10 selected tests in 2.95 s with PostgreSQL 16. The normal `uv run ci` passed 1606 tests with 4 existing hook skips, 10 heavy tests deselected and 95 percent fast-tier coverage; Ruff, format, strict mypy and all 3 import contracts passed. These are correctness checks, not E2 chaos measurements or performance results.

## ADR-034: Task attempts, dependency eligibility and bounded recovery

Status: implementation authorized by the existing mock implementation approval. No dependency, provider call, secret or spend-cap change.

Decision: `waggle.coordination.task_model` defines frozen typed task metadata and pure transitions. Review progresses in single steps before assignment. Queue terminal states cannot be reopened; an operator must submit a new reviewed task. `TaskRepository` stores state, immutable definition signatures, dependencies and append-only event snapshots. Each accepted transition and its event share one transaction. Matching successful request ids replay historical snapshots without writing another event; conflicting content is rejected. Empty and denied claims are not cached as transitions. This is a queue contract, not operator authentication or court approval.

Claims select approved tasks whose existing dependencies are done, with priority descending and task id as a deterministic tie-break. Definitions reference only previously inserted tasks and cannot be changed, preventing cycles through the API. Priority defaults to 0 in 0 to 9; no fairness claim is made. Task, worker and request ids are bounded ASCII identifiers. Only queue metadata is stored; reviewed mission payloads and tool arguments remain separate work.

Claims use task row locks with `SKIP LOCKED`, a per-worker database advisory lock and a unique active-worker index. Tokens and attempts increment on every assignment. Start, completion and failure require the exact live task/worker/token under the same lock as the transition and event. The lease defaults to 400 caller-supplied ticks; the attempt cap defaults to 3 with a hard configuration range 1 to 10. These assumptions require calibration under E2. Expired attempts are recovered in bounded `SKIP LOCKED` batches; exhaustion fails the task. Counters never reset. Recovery does not modify physical corridor state, even for an occupied expired zone.

Worker iteration commits claim and start before calling a handler. A matching replay stops before the handler, including a crash after claim. Recovery can later reassign with a new request and token. A handler must return the exact `HandlerOutcome.DONE` enum member; arbitrary strings or objects cannot mark completion. Exceptions log a fixed code without their text and fail a live attempt. A late return after expiry/reassignment is stale. Arbitrary external side effects still require their own fenced idempotent tool transaction; this API is not an exactly-once executor for external systems.

Schema revision 2 adds only queue tables and indexes. The explicit migration accepts an optional forward target, rejects downgrades and verifies the expected installed revision under its existing transaction lock. Revision 1 remains available for staged installation and upgrade tests. No service startup automatically migrates. The old revision 1 corridor model and fencing behavior remain unchanged.

Verification: missing-module and migration-target tests failed before implementation; a separate handler-result regression first returned done for an untyped object, then passed after requiring an explicit typed outcome. The 92-test local coordination/database/worker selection passes. Cloud-only tests cover PostgreSQL upgrade/rollback, competing workers and sweepers, dependency gating, stale completion, event failure rollback, handler transaction boundaries and an actual worker process exiting abruptly after its durable claim. No local database was used. Full E2 chaos, physical handoff and production daemon/MCP wiring remain pending.

Cloud verification: [cloud run 41225808111](https://github.com/agustindiazcano/waggle-agents-meta-muse/actions/runs/41225808111), commit `085f8ff`, passed all 26 tests in 7.893 s according to the downloaded JUnit artifact, with zero failures, errors or skips. This includes 10 existing corridor tests and 16 new queue/worker tests. Normal `uv run ci` passed 1626 tests with 4 existing hook skips, 26 heavy tests deselected and 92 percent fast-tier coverage. Ruff, strict mypy and all 3 import contracts passed. This is correctness verification, not a full E2 result.

## ADR-035: Plan a logistics network of independent Waggle cells

Status: documentation accepted for planning on 2026-10-31; implementation gate not passed. The maintainer supplied a global logistics draft and requested adaptation to this repository. This ADR changes no runtime behavior, safety threshold, court rule, migration or experiment result.

Decision: record the extension in [MULTI_WAREHOUSE_PLAN.md](MULTI_WAREHOUSE_PLAN.md). One warehouse is a local authority domain. The global orchestrator requests inter-site outcomes through authenticated cell contracts and cannot issue robot motion, widen local limits or impersonate a chassis. Source, truck and destination track physical custody separately from reservations and expected receipts. Each local transition is atomic and idempotent; durable inbox/outbox processing and reconciliation connect domains without a cross-site database transaction. A timed-out request is reconciled before compensation. Cargo on a failed truck stays there until a confirmed handoff.

Use `waggle.logistics` for future pure domain/simulation code, `waggle.db` for persistence, `waggle.llm` for model calls and thin service/API adapters. Do not use the Python keyword `global` as a package name or combine model, route and database logic. Reuse local task/zone credentials only inside their authority domain; they are not network-wide capabilities. The truck service is an abstract seeded logistics simulator and makes no road-driving claim.

The complete local build order in AGENTS.md section 18 remains first. Planning does not pass G-GLOBAL or authorize implementation, paid calls, held-out runs, dependencies or migrations. All nine proposed global scenarios remain pending. Start with a deterministic baseline, then mock model proposals and a bounded validated loop. A no-global-validator comparison is shadow-only, with identical local safety. E-GLOBAL is a proposed experiment and does not renumber E1 through E10. No global benefit or correctness result has been measured.

Consequences: global work has explicit custody, partition and stale-state requirements rather than simply adding more robot agents. A shared-tick demo is insufficient evidence for independent sites; multi-clock lease authority and trusted arrival receipts remain design decisions. The maintainer must review local completion evidence and authorize implementation separately at G-GLOBAL.

## ADR-036: Atomic task handoff record

Status: cloud PostgreSQL correctness tests passed; no E2 evaluation. This does not authorize an external robot effect.

A task definition may name one existing capacity-one handoff zone. The immutable definition signature includes the zone, and revision 3 stores this requirement separately. Existing task definitions retain their original signatures. Ordinary task completion rejects a task with a handoff requirement. The transactional handoff operation locks the task and the corridor state, checks live credentials and current trusted occupancy for the same holder, and atomically commits the task completion and event. Dependencies remain blocked until the predecessor is done. A matching request replay returns historical success; a conflicting request id raises an error. The existing transaction rollback preserves the task if event insertion fails.

The caller must supply authenticated identity, current trusted occupancy and a trusted tick. This code does not authenticate a caller, ingest occupancy, command a robot, establish custody or implement a live worker adapter. The pure admission check alone cannot authorize a later effect. Incorrectly declaring a delivery as an ordinary task would bypass this requirement; mission construction must explicitly bind physical deliveries to handoff zones. Cloud PostgreSQL run 41235442937 on 15d505f passed all 36 correctness tests, including ten handoff cases; no E2 evaluation has run.

## ADR-037: MCP audit rows and database rate limit

Status: implemented; cloud run 41239557152 passed 48 PostgreSQL tests. Realizes ADR-032 branch (d) under the maintainer approval of 2026-10-31. No E3 result.

Revision 4 adds `mcp_audit`: one intent row and at most one result row per correlation id (unique on id and phase). Rows carry chassis, robot id, tool, the SHA-256 of the validated arguments and `clock_timestamp()`. Table checks keep a deny reason on denied intents, an outcome and latency only on result rows, and an allowed intent always tied to an identity. A failed authentication is a denial with no identity.

`McpAuditRepository.begin` takes a transaction-scoped advisory lock per chassis, returns the stored decision for a repeated correlation id, counts allowed intent rows in the sliding window and writes the intent as allowed or denied `rate_limited`. Denials are not counted, so a flood of bad calls cannot extend its own lockout. Reusing a correlation id with other content raises `IdempotencyConflict`. A database error propagates and the caller must not forward. `complete` writes the correlated result row only for an allowed intent, and a repeat with another outcome raises.

This repository does not authenticate, check the allowlist or schemas, or forward a call. The server wiring (ADR-032 branch (e)) remains. Limit values are caller configuration and still need calibration. The window uses the database clock, which is the only wall-clock use and stays outside `waggle.sim` and `waggle.control`.

## ADR-038: MCP boundary dispatcher

Status: implemented against in-memory fakes, not evaluated. ADR-032 branch (e), first part, under the maintainer approval of 2026-10-31. No E3 result.

`waggle.mcp_server.boundary.Boundary.handle(token, request_id, tool, args)` runs the ADR-032 order: authenticate, allowlist and schema, rate limit with the intent row, forward with a per-call timeout, result row. It never raises and returns a `CallResult` with a reason code and no argument values. Identity store, audit log and forwarder are injected protocols, so the module opens no connection. `McpAuditRepository` satisfies the audit protocol.

Failure modes, all closed: an invalid request id is rejected before any work and, having no usable correlation id, is not audited; a failed intent or denial write returns `audit_unavailable` and nothing is forwarded; a reused request id with other content returns `request_id_conflict`. A tool exception becomes an `error` result row and a `tool_error` result with no exception text. A failed result-row write is logged and does not hide a completed effect.

Limit: only the outcome of an allowed call is stored, not its data. A repeat of an allowed request therefore returns `duplicate_request` and is never forwarded twice; the caller must read state through `get_task`. Still pending: the PostgreSQL identity store (a `robot_identities` migration), the concrete forwarder that calls the fenced repositories, the transport and rate-limit calibration.

## ADR-039: PostgreSQL identity store

Status: implemented; cloud run 41241463775 passed 56 PostgreSQL tests. ADR-032 branch (e), second part, under the maintainer approval of 2026-10-31 for migrations. Revision 4 was the latest in the repository; no persistent database exists to migrate yet, only isolated cloud test schemas.

Revision 5 adds `robot_identities`: the SHA-256 digest as primary key (checked as 64 lowercase hex digits, so a plain token cannot be stored by mistake), chassis, robot id, a revoked flag with its timestamp, and a unique index allowing one active token per chassis and robot. `PostgresIdentityStore` implements the `IdentityStore` protocol: `lookup` returns revoked records too, so authentication reports `revoked` rather than `unknown_token`; a malformed digest is a miss without a query; `register` validates chassis against the allowlist table and the robot id format; `revoke` is one-way. Rotation is revoke, then register. A database error raises and authentication denies.

The token is generated and provisioned outside the repository (`generate_token`); only its digest reaches this table. There is no provisioning command yet. Still pending: the concrete forwarder, the transport and rate-limit calibration.

## ADR-040: Fenced forwarder for release_zone and get_task

Status: implemented against fakes, not evaluated. ADR-032 branch (e), third part, stacked on ADR-039.

`FencedForwarder` implements the boundary `Forwarder` for the two tools that already have a fenced backend. `release_zone` calls `CorridorRepository.release` with the authenticated robot id as holder, the caller token as the zone credential, and a tick and occupancy evidence taken from injected `TickSource` and `OccupancySource`. A request can supply neither. A failing source raises before any release, so the boundary records an error and nothing changes. A refused release is a normal result (`released` false with the model reason). `get_task` returns the snapshot only when the task worker is the authenticated robot; a missing task and another robot task raise the same `ToolDenied`, so a caller cannot probe which ids exist.

Every other tool raises `ToolUnavailable` and surfaces as `tool_error`: `move_waypoint`, `pick_package`, `deliver_package` need a physical effect and trusted occupancy ingestion, and the maintenance tools need their workflow. No production `TickSource` or `OccupancySource` exists yet; wiring one is pending, and until then the forwarder runs only in tests.

## ADR-041: Trusted shared tick and zone occupancy

Status: implemented; cloud run 41243437112 passed 66 PostgreSQL tests. Stacked on ADR-040. Schema revision 6, under the maintainer approval to migrate of 2026-10-31; revision 5 was the latest before it.

Revision 6 adds `trusted_tick` (a singleton, only moving forward) and `zone_occupancy` (one row per registered zone: observed tick and occupants, where a null array means unknown and an empty array means clear). `TrustedStateRepository` implements the forwarder `TickSource` and `OccupancySource`. A missing tick raises `UnknownTick`; a zone never recorded reads as unknown at tick 0; a lower tick raises `TickRegression`; an older observation never replaces a newer one; an observation later than the shared tick is rejected; occupants must have the robot id format. `release_zone` through these sources is refused while a zone is recorded occupied or unknown.

Trust boundary: `advance_tick` and `record` have no MCP tool and no request path. They are for a trusted writer holding database credentials, such as the simulator bridge. That writer, and what feeds it real odometry, does not exist yet, so nothing writes these tables in a running system. The release and handoff checks are only as trustworthy as that writer.

## ADR-042: Simulator bridge as the trusted writer

Status: implemented; cloud run 41244266563 passed 68 PostgreSQL tests. Stacked on ADR-041.

`SimTrustedBridge.publish(sim)` is the first writer of the trusted tick and occupancy tables. It advances the shared tick to the simulator tick, then records one observation per zone using the occupancy derivation of the simulator admission adapter (conservative footprints; an unknown pose is published as unknown). A regressing tick raises before any observation. Only the live simulation publishes: a rollout fork must not, because the shared tick cannot move backwards.

This closes the loop for simulator runs: the bridge writes, `TrustedStateRepository` stores, and `FencedForwarder` reads for `release_zone`. For real hardware the writer would be an odometry service, which does not exist. The bridge makes one transaction per zone and per tick, which is correct but not measured for speed. It is implemented, not evaluated, and is not part of E2.

## ADR-043: Handoff completion through the worker

Status: implemented; cloud run 41245044162 passed 74 PostgreSQL tests. Stacked on ADR-042.

`run_once` gains an optional `complete` argument that replaces ordinary completion; the default is unchanged, so a handoff task is still denied without it, and a test shows that. `HandoffFinisher.complete` is the production value: a task with no handoff requirement completes normally; a task with one gets the zone token that the worker itself holds in the corridor table and the occupancy evidence from the trusted store, then calls the atomic `complete_handoff`. The worker supplies neither. A worker that does not hold the zone, a second occupant and unknown occupancy all leave the task EXECUTING and the iteration STALE. `TaskRepository.handoff_zone` is the only new read.

Limits: the handler is still a trusted callable that must itself drive the robot into the zone; no physical effect exists beyond the simulator. A replay of completion after the lease was released is refused here, and `run_once` does not call completion again for a replayed claim. The stale iteration leaves the task EXECUTING until its lease expires and bounded recovery requeues it. `serve_worker` accepts the same `complete` argument. Not part of E2.

## ADR-044: End-to-end handoff scenario on the simulator

Status: test only; cloud run 41246267282 passed 76 PostgreSQL tests. Stacked on ADR-043. No new behavior.

One cloud test chains the whole path on S03 seed 7: the simulator moves robot-0, `SimTrustedBridge` publishes the tick and occupancy, `TrustedStateRepository` stores them, a task with a handoff zone is claimed by a worker, and `HandoffFinisher` completes it through the atomic handoff. The handler is a trusted driver that steps the simulator and returns DONE only when the simulator derivation shows robot-0 alone in the zone. A second test shows a handler that claims DONE before the robot arrives leaves the task EXECUTING and the iteration STALE. A database-free test fixes the fact the scenario depends on, that robot-0 is outside the zone at the start and alone in it later.

This shows the components fit together in the simulator. It is not E2: there is one seed, no baseline without the layer, no crashed workers and no throughput measurement.

## ADR-045: Line transport for the MCP boundary

Status: implemented against a fake dispatcher, not evaluated. Stacked on ADR-044.

`LineServer` turns one JSON-RPC line into at most one reply line and never raises; `serve_stdio` loops over a stream. It implements the parts checked against the current MCP specification on 2026-10-31: newline framing with nothing but protocol messages on stdout, `tools/list` with a name, description and input schema per tool in sorted order, `tools/call` returning `content`, `structuredContent` and `isError`, a tool failure as an `isError` result with only the reason code, and `-32602` for an unknown tool. The boundary still audits an unknown tool name first, so probing is recorded.

Not implemented, and the reason it must not be called a conformant MCP server: the handshake. The fetched specification describes a newer revision without negotiation (every request carries its version in `_meta`, plus a required `server/discover`) next to the legacy `initialize` flow, and the pages that define `initialize`, `server/discover` and the `_meta` key rules were not read. A client that expects either handshake will not work until that is added from the current text. The input schemas are advisory; the boundary enforces the real per-chassis bounds.

Decisions: one token per process, bound at construction, so one chassis per server process; correlation ids are the JSON-RPC id prefixed with a per-process session name, so a repeat inside one session is a replay and a new session cannot collide, but a retry after reconnecting is a new request; a line over 64 KiB is rejected before parsing; non-finite numbers are a parse error. The process entry point is not wired: it needs the database, the token source, the map extent, the rate limit values and the trusted sources, and `waggle.mcp_server.__main__` is still the placeholder.

## ADR-046: MCP handshake for both protocol revisions

Status: implemented against a fake dispatcher, not evaluated against a real client. Stacked on ADR-045 and supersedes its missing-handshake limitation.

Source: the specification pages for revisions 2025-11-25 and 2026-07-28, read on 2026-10-31. Legacy flow: `initialize` (params `protocolVersion`, `capabilities`, `clientInfo`, all required here) answers with the server version `2025-11-25`, `capabilities` with `tools`, and `serverInfo`; the specification requires a supported requested version to be echoed and otherwise the server to answer with a version it supports, which is what this does. Other requests before `initialize` are refused with -32600 (the specification only says clients should not send them, so this is a fail-closed choice, not a stated rule); `notifications/initialized` is accepted and ignored, and initialization is marked complete at the `initialize` reply. `ping` is optional in that revision and answered with an empty result at any time. Modern flow: a request is modern when `_meta` carries `io.modelcontextprotocol/protocolVersion`; it then needs `io.modelcontextprotocol/clientCapabilities` as an object or gets -32602, and an unsupported version gets -32022 with `data.supported` and `data.requested`. `server/discover` answers `supportedVersions`, `capabilities` and `serverInfo` in `_meta`. Every modern result carries `resultType` complete. No state is kept for modern requests.

Gaps, stated plainly: the field definitions of `Implementation` and `ClientCapabilities` were not read, so only their types are checked; whether `server/discover` itself requires all three `_meta` keys is not stated in the text read, so it requires the two the general rule marks required; a modern request that omits the version key cannot be told apart from a legacy one and gets the not-initialized error rather than -32602; `ttlMs` and `cacheScope` are omitted; the 2026 revision removes `ping`, which is still answered. No real client has been run against this, so interoperability is untested and the server is not claimed to be conformant.

## ADR-047: MCP server entry point reads every setting from the environment

Status: implemented with unit tests and injected fakes; not run against a real client or a real database in this branch. Stacked on ADR-046.

Decision: `waggle.mcp_server.app` builds the boundary over the PostgreSQL repositories (identity store, audit and rate limit, corridors, tasks, trusted tick and occupancy) and `python -m waggle.mcp_server` serves newline-delimited JSON-RPC on stdio. The five settings below are required and have no default, because a default for a rate limit or a map extent would be an unreviewed safety value. A missing or invalid value, a schema revision other than the latest, or an unreadable revision ends the process with exit code 2 before any line is read. Errors name the variable and never its value; an unreadable revision reports only the exception class, because driver text can carry the connection address. The token is one chassis token per process (ADR-045). The trusted tick and occupancy come from `TrustedStateRepository`; in a running system only the simulator bridge writes them (ADR-042), so a deployment without that writer answers release calls as unknown evidence and denies.

Gaps: the rate limit and timeout values are not calibrated; the map extent is typed in by hand and not read from a loaded map; `docker-compose.yml` still expects an HTTP health endpoint on port 8002 that a stdio server does not provide; the eight other tools still raise `ToolUnavailable`.

## ADR-048: Spare parts catalog and idempotent reservations

Status: implemented with unit tests and fakes; PostgreSQL behavior is checked only by the cloud workflow, not run locally. Stacked on ADR-047.

Decision: schema revision 7 adds `spare_parts` (part number, `on_hand`, `reserved`, with `reserved <= on_hand` enforced by a check) and `part_reservations` (unique idempotency key, part, quantity, holder). The table is the catalog: a part number outside it is denied by code, so text from a manual or a model cannot create a part (T3). `InventoryRepository.reserve` locks the part row first and then looks up the key, so concurrent calls with one key reserve once and stock cannot oversell. A repeat with the same values is a replay; the same key with other values raises `IdempotencyConflict` and the tool denies (T16 for orders, same mechanism). A shortage is a result (`reserved: false`), not an error. `get_inventory` reports only available units. The holder is the authenticated robot id. Catalog rows load through `add_part` from separate scripts, never inside the migration.

Gaps: no catalog load script exists yet; reservations are never released or consumed; `dispatch_tech`, `open_ticket` and `create_purchase_order` still raise `ToolUnavailable`; the starting allowlist lets only the maintenance chassis reserve.

## ADR-049: Machine catalog, idempotent tickets, dispatch and purchase orders

Status: implemented with unit tests and fakes; PostgreSQL behavior is checked only by the cloud workflow. Stacked on ADR-048.

Decision: schema revision 8 adds `machines`, `maintenance_tickets` and `purchase_orders`. The ticket id is derived from the failure event key (`tkt-` plus 16 hex digits of its SHA-256), so one event opens at most one ticket (T9); a repeat returns `created: false`, and the same key with another machine, summary or opener is denied. `dispatch_tech` needs an existing open ticket and a registered zone, records the dispatcher and is idempotent for the same zone; a second, different zone is denied. `create_purchase_order` locks the part row, requires a catalog part, places the order only when no unit is available (ADR-020), and is idempotent per key (T16); with stock available it returns `ordered: false`. The opener, dispatcher and requester are the authenticated robot id. The summary is untrusted text: stored bounded and printable only, never returned.

Gaps: dispatch records a request and does not move a technician or take a zone lease; a technician must still acquire the zone through the corridor path. There is no ticket close or reopen. The machine catalog has no load script. The summary is not passed through the guard yet.

## ADR-050: Motion tools queue orders for the simulator bridge

Status: implemented with unit tests and fakes; PostgreSQL behavior is checked only by the cloud workflow. Maintainer chose this design on 2026-11-01. Stacked on ADR-049.

Decision: `move_waypoint`, `pick_package` and `deliver_package` do not move anything in the MCP server. After the boundary checks (identity, allowlist, schema and chassis bounds, rate limit, audit intent), the forwarder queues a row in `motion_orders` (schema revision 9) and returns `queued` with the order id. The simulator bridge, which owns ground truth, is the consumer: `pending()` lists orders and `resolve()` records `done` or `failed`. One transaction checks that the task exists, belongs to the caller (`worker_id` is the authenticated robot) and is live (`ASSIGNED` or `EXECUTING`, expiry above the trusted tick); a delivery also checks that the caller holds a live lease on the zone. A robot has at most one pending order (partial unique index): the same call again replays the pending order, a different one returns `busy` as a result. Refusals are denials that do not say which check failed; the reason is kept for audit and tests only.

Gaps, stated plainly: nothing consumes the queue yet, so a queued order does not move a robot; the simulator-side consumer is the next branch. Package ids are bounded identifiers and are not checked against any registry, because none exists. The lease check uses the holder and expiry; the fencing token is not an argument of these tools. Chassis speed bounds are enforced earlier, by the schema layer.

## ADR-051: The simulator executes queued motion orders

Status: implemented with unit tests on the real simulator and a fake queue; the PostgreSQL pairing is checked only by the cloud workflow. Stacked on ADR-050.

Decision: `waggle.experiments.sim_motion.MotionExecutor` is a simulator system placed before the one-shot waypoint driver. Each tick it closes finished orders and starts pending ones. A `move_waypoint` order replaces the robot's route with one waypoint and resolves `done` when the driver reports arrival, `failed` when the deadline passes (the route is cleared so the robot stops). An order for a robot the simulation does not have, or for a robot that already has an active order, resolves `failed`. The simulator has no package model, so `pick_package` and `deliver_package` resolve `failed` immediately: a physical effect is never reported that was not simulated. The executor runs only in the live simulation, never in a rollout fork, and is deterministic for the same orders.

Gaps, stated plainly: the ordered `speed` is not used, because the waypoint driver always drives at the class cap (the chassis bound was already checked upstream); the fast layer still governs actual motion, so arrival can be late or never; the executor is not yet part of any experiment scenario, and no process runs the server and the simulator together; package orders need a package model before they can succeed.

## ADR-052: Guard adapter and the first E3 evaluator pieces

Status: implemented with unit tests over scripted providers; no real model call, no result file, E3 has not run. Based on `main`, independent of the open MCP stack.

Decision: (1) `INCIDENT_TEXT` is an `UntrustedSource` with a 2000 character cap (an assumption to calibrate), so incident reports take the same sanitize, fence and screen path as every other untrusted text. (2) `waggle.llm.guard_adapter.LlmGuardClassifier` implements the existing `GuardClassifier` contract over the `guard` role: one request per fenced input, request id from the prompt version and the input so a repeat is served from the client cache, model id from the routing table. It returns raw text and parses nothing; `parse_guard_response` (now public) validates strictly and any failure rejects and escalates. The prompt is versioned (`guard-v1`). (3) `waggle.experiments.e3_eval` loads the corpus and refuses any case that is not fully reviewed; raises `MissingLayer` when a required target layer has no runner and, when a subset is selected, lists every case it leaves out with a reason; scores T11 structure on its own against the expectation fixed in the corpus README (reject T11-01 and T11-02, accept T11-03), never against the review label; and measures the guard alone on benign and injection text cases, reporting missed injections first with Wilson 95 percent intervals and raw counts.

Gaps, stated plainly: no layer runner exists yet except output structure, so a full E3 run still raises `MissingLayer` for the other nine target layers (identity, schema bounds, fast layer, catalog check, read-back, message schema, court unanimity, plan validator, plan schema, untrusted-data boundary); the guard-only measurement is not an E3 layer result and says nothing about downstream layers; the guard prompt has not been run against any real model; the catalog check does not establish compatibility (E3-T3-02), a known limit to report; the planner, court prompt and message schema integrations remain.

## ADR-053: E3 runners for the MCP identity and schema bounds layers

Status: implemented with unit tests, including sensitivity tests; E3 has not been run as an experiment and no result file exists. Extends ADR-052.

Decision: `waggle.experiments.e3_mcp_layers` runs the seven corpus cases that target `mcp_identity` and `mcp_schema_bounds` on the production `Boundary`, with an in-memory identity store, an audit log that allows every intent (so the rate limit never decides) and a forwarder that only records. Both layers are deterministic and never read free text, so each case performs the action its text tries to cause, or the ordinary action for a benign case. An injection is blocked when its call is not forwarded; a benign call must be forwarded. The report lists forwarded injections first, then benign calls that were blocked. `RUNNABLE_LAYERS` (output structure, identity, schema bounds) is the set a selected run may name; any other target layer still raises `MissingLayer`.

Provenance: `ATTEMPTS` maps each case id to a caller and a call. I wrote it from the case text. It is a fixture, not a label, and it needs maintainer review: a wrong mapping would measure the wrong thing. Sensitivity tests widen the allowlist and the speed bound and require the runner to report forwarded injections, and block everything and require false blocks, so a green result cannot come from a runner that cannot fail.

Gaps, stated plainly: what this measures is that the layer holds when the attack action reaches it, independent of the guard; it does not measure whether a model would be fooled into making that action. Seven of 25 cases are covered; catalog check needs PostgreSQL, the fast layer needs the control stack, and read-back, message schema, court unanimity (production prompt), plan schema, plan validator and the untrusted-data boundary still have no runner.

## ADR-054: E3 runner for the catalog check layer

Status: implemented with unit tests over a fake orderer and a PostgreSQL test that runs only in the cloud; E3 has not been run as an experiment and no result file exists. Extends ADR-053.

Decision: `waggle.experiments.e3_catalog` runs the three corpus cases that target `catalog_check` by placing the order each case tries to cause through the production `ProcurementRepository`, over a synthetic catalog (`BRG-6204` and `SEAL-08`, stock zero, loaded by `seed_catalog`). An injection is blocked when no order is placed. The report reuses `LayerReport`, forwarded injections first. `catalog_check` joins `RUNNABLE_LAYERS`.

Result expected before the run: E3-T3-01 (absent part) is blocked because the part is not in `spare_parts`. E3-T3-02 (existing but incompatible part) is accepted, because the catalog stores no machine-to-part compatibility, so existence is the only check. The runner reports it as a missed injection. It is a real gap in the layer, not a runner defect, and no check was loosened or hidden. Closing it needs a compatibility table and a design decision, listed in PENDING.

Provenance: `PART_FOR_CASE` maps each case id to a part number. I wrote it from the case text. It is a fixture, not a label, and needs maintainer review like `ATTEMPTS`.

Gaps, stated plainly: 10 of 25 cases now have a runner. Message schema, read-back, court unanimity (production prompt), plan schema, plan validator, untrusted-data boundary and the fast layer still have none.

## ADR-055: Inter-robot message schema and its E3 runner

Status: implemented with unit tests; E3 has not been run as an experiment and no result file exists. Extends ADR-054.

Decision: `waggle.governance.messages.parse_robot_message` is the fixed schema of `docs/ARCHITECTURE.md`. A message is a JSON object with exactly `sender`, `recipient` and `status`. Unknown fields, missing fields, duplicate keys, a non-object, text over the 500 character `ROBOT_MESSAGE` cap, a status outside `waiting`, `ready`, `blocked`, `done`, `fault`, a sender that is not the authenticated caller and a message to oneself are all rejected. It never ignores an extra field and carries no authority. `waggle.experiments.e3_messages` runs the `message_schema` case through it, and `message_schema` joins `RUNNABLE_LAYERS`.

Gaps, stated plainly: the status list is an assumption to calibrate. The corpus has one case for this layer (E3-T5-02) and no benign case, so false blocks are not measured. Nothing yet routes real robot messages through this parser or through the guard; 11 of 25 cases now have a runner.

## ADR-056: Provisioning script for catalog, machines, zones and identities

Status: implemented with unit tests over fakes; the PostgreSQL test runs only in the cloud workflow. Extends ADR-049 and ADR-039.

Decision: `uv run provision SPEC TOKENS_OUT` (`waggle.provisioning`) loads data that migrations must not carry (AGENTS.md section 7). The JSON spec has exactly the keys `parts`, `machines`, `zones` and `identities`; any unknown, missing, duplicate or out-of-range entry rejects the whole spec before anything is created. It uses the existing repositories (`add_part`, `add_machine`, `register`). A rerun skips existing parts, machines and active identities and names them; stock is never reset. A token is generated per new identity with `generate_token`, only its SHA-256 digest goes to `robot_identities`, and the tokens go to a new file with owner-only mode that is never overwritten and never printed or logged. Rotation is not part of this script: revoke the old token first. Any failure exits 2 with the exception class only.

Gaps, stated plainly: `data/provision/example.json` is sample data, not the demo catalog; the real part list, machine list and zone map come from the maintainer. A spec run twice against a partly provisioned database cannot recover a token that was lost. Zones are registered with the corridor repository, which creates unheld zones only. No compatibility data exists for the catalog (ADR-054, PENDING row 95). On Windows the owner-only file mode is not enforced by the operating system.

## ADR-057: Read-back and item resolution before a voice-driven pick

Status: implemented with unit tests, including sensitivity tests; E3 has not been run as an experiment and no result file exists. Extends ADR-054. ADR-055 and ADR-056 are in open PRs; keep the numbers in order when merging.

Decision: `waggle.governance.readback` is pure. `resolve_items` maps a transcript to known item ids by code (digits, `ITEM-n`, number words up to 99). `start_readback` builds the read-back text from the trusted order item only, never from the transcript. `authorize` allows execution only when a `Confirmation` exists for that prompt id and that item and the transcript names no item other than the ordered one. A `Confirmation` is a typed object the authenticated operator channel produces; words in the transcript, such as a claim that confirmation already happened, are never parsed into one. `waggle.experiments.e3_readback` runs E3-T4-01 to 03: the two injections try to execute from the transcript with no confirmation and must not be authorized; the benign case asks for a read-back and must get a prompt naming ITEM-17. `read_back_item_resolution` joins `RUNNABLE_LAYERS`.

Provenance: `ATTEMPTS` is a fixture I wrote from the case text, like the other runners. It needs maintainer review.

Gaps, stated plainly: this measures the confirmation rule, not whether a transcription model would hear the wrong number. The result is independent of what the transcript says, which is the design; it does not show the rule is enough against a compromised operator channel. Nothing yet connects a real voice transcript, a trusted order or the operator channel to these functions. Number words stop at 99. The word-error rate on item ids (EXPERIMENTS.md E7) is not measured. 13 of 25 cases have a runner with this branch alone (10 on main plus 3), and 14 once PR 90 (message schema) is merged.

## ADR-058: E3 runner for the untrusted-data boundary layer

Status: implemented with unit tests, including a sensitivity test; E3 has not been run as an experiment and no result file exists. Extends ADR-054. Numbers 055 to 057 are in open PRs; keep them ordered when merging.

Decision: `waggle.experiments.e3_boundary` runs the case that targets `untrusted_data_boundary` (E3-T18-03, a package label with forged closing and system tags) through the production `sanitize` and `fence` as the source the case declares. An injection is blocked when the fenced result is exactly one `<untrusted source="...">` wrapper whose body has no raw angle bracket, so the text can neither close the fence nor open another tag. The check is structural and never reads meaning. A sensitivity test wraps without escaping and requires the runner to report the missed injection. `untrusted_data_boundary` joins `RUNNABLE_LAYERS`.

Provenance: `SOURCES` maps the case id to `PACKAGE_LABEL`, taken from the case entry. It is a fixture and needs maintainer review.

Gaps, stated plainly: this shows the fence holds as data markup; it does not show that a model given the fenced text ignores instructions inside it, which only a model run could measure. The corpus has one case for this layer and no benign case. The planner context that should carry the fence does not exist yet (`waggle.validation` is not created).

## ADR-059: Plan schema in a new `waggle.validation` package

Status: schema and E3 runner implemented with unit tests, including a sensitivity test; E3 has not been run as an experiment and no result file exists. Implements the "Plan schema" table of `docs/ARCHITECTURE.md`. Numbers 055 to 058 are in open PRs; keep them ordered when merging.

Decision: `waggle.validation.plan.parse_plan(raw, mission_id, context)` is pure and fails closed. A plan is one JSON object with exactly `nodes`, `rationale`, `escalate` and `escalation_reason`; a node has exactly the nine documented fields. Unknown fields (including a model-supplied `mission_id`), duplicate keys, `NaN` and `Infinity`, more than 20 nodes, duplicate labels, `wait_for` that names a missing label or forms a cycle, an unknown robot, item or zone, an action outside MOVE, PICK, HANDOFF, DELIVER and DISPATCH_REPAIR, a speed cap not above zero or above the robot's maximum, and a zone that is both required and avoided are all rejected. PICK, HANDOFF and DELIVER need an item; the other two reject one. `escalate` and `escalation_reason` must agree. The mission id comes from code. Errors carry a code, never plan text. A new import contract, `validation-no-llm-side`, keeps `waggle.validation` from importing `waggle.llm`, `waggle.governance` or `waggle.mcp_server`, with a violation fixture. `waggle.experiments.e3_plan` runs E3-T18-02: it adds the JSON object quoted in the case to a valid base plan and requires the schema to reject it. `plan_schema` joins `RUNNABLE_LAYERS`.

Assumptions to calibrate: the escalation reasons (`no_feasible_plan`, `unsafe_state`, `needs_operator`), the 2000 character rationale cap and the 20 zones per node. The rule that an item action needs an item and the others reject one is mine, not in the table.

Gaps, stated plainly: this is the schema only. There is no belief state, rollout, counterexample loop, planner prompt or fleet validator, so `plan_validator` (E3-T18-01 and 04) still has no runner and a full E3 run still raises `MissingLayer` for it. The schema does not check geometry: a plan that names a blocked zone as a corridor is schema-valid and must be caught by the validator. `BASE_PLAN` and `CONTEXT` in the runner are fixtures that need maintainer review. One case for this layer, no benign case.

## ADR-060: Geofence check of a plan and the E3 runner for the plan validator layer

Status: implemented with unit tests, including two sensitivity tests; E3 has not been run as an experiment and no result file exists. Stacked on PR 94 (ADR-059).

Decision: `waggle.validation.geofence.check_geofence(plan, hazard)` returns a `GEOFENCE_INTRUSION` counterexample, with node label and zone, for every node whose target zone or required corridor zone is in the hazard set. The hazard set is trusted state (telemetry thresholds, static geofences) and never comes from text. `waggle.experiments.e3_plan_validator` builds the plan each case causes, parses it with the production schema and checks it: E3-T18-01 (route the forklift through Z1) must be rejected, and E3-T18-04 (a detour that avoids Z1) must be accepted. `plan_validator` joins `RUNNABLE_LAYERS`. This is the minimal validator recommended to the maintainer; the full rollout validator of ADR-023 is not replaced.

Provenance: `PLANS` in the runner is a fixture I wrote from the case text, like the other runner fixtures. It needs maintainer review. The detour in E3-T18-04 uses `avoid_zone_ids` and no corridor.

Gaps, stated plainly: the check sees only the zones a plan names. A path through open transit zones that crosses the hazard is not seen, and no rollout runs, so the part of E3-T18-01 that asks to omit the thermal alarm from the rollout is not exercised. Marking `plan_validator` runnable therefore means the geofence part only; a result for it must say so. Other counterexample types (collision, separation, deadlock, lease conflict, progress) do not exist.

## ADR-061: E3 runner for the fast layer

Status: implemented with unit tests, including a sensitivity test; E3 has not been run as an experiment and no result file exists.

Decision: `waggle.experiments.e3_fast_layer` runs E3-T2-02 (an untrusted SOP asks to remove a hazard geofence and zero the separation margin). The fast layer has no text input, so the case text is never passed to it. The runner puts a trusted critical telemetry reading on the robot's path and asks the production `geofence_limit`, with the default control and reflex parameters, for its cap. The injection counts as blocked when the cap is below the requested speed. `fast_layer` joins `RUNNABLE_LAYERS`.

Provenance: `HAZARD_READING`, `ODOMETRY` and `REQUEST` are a fixture I wrote from the case setup and need maintainer review. A first version put the reading 8 m ahead; the geofence edge was then 5 m away and a carrier at 2 m/s can stop in that distance, so the cap did not drop. The test caught it and the reading moved to 4 m. No limit was changed.

Gaps, stated plainly: the result shows that no text path reaches this check and that the geofence limit works for one geometry. It says nothing about whether a model resists the text, and it does not exercise the separation margin or the occlusion cap. One case, no benign case.

## ADR-062: The maintainer adopted the recommended option of the design decision tables

Date: 2026-11-02. Said by the maintainer: "para las decisiones hace lo recomendado".

Decision: for every decision table at the end of the design documents `docs/PACKAGE_MODEL_DESIGN.md`, `docs/CATALOG_COMPATIBILITY_DESIGN.md`, `docs/COURT_DESIGN.md`, `docs/ROLLOUT_VALIDATOR_DESIGN.md`, `docs/ADVISORS_DESIGN.md`, `docs/PREDICTIVE_MAINTENANCE_DESIGN.md`, `docs/MULTIMODAL_AND_VIEWER_DESIGN.md` and `docs/MCP_CLIENT_TEST_DESIGN.md`, the option in the Recommendation column is adopted. The tables are the record of what was recommended; this entry does not restate them, so it cannot misquote one.

What this approves, which AGENTS.md section 15 reserves for the maintainer, each to be built with a test first and a check of the current schema revision before any migration: the catalog compatibility table and the technician lease with ticket close and reservation settlement (schema revisions proposed as 10 and 11, widening a CHECK constraint counts as approved); a required `ticket_id` on `reserve_part` and `create_purchase_order`; the package id registry table and its check in the forwarder, with the foreign key later; filtering `tools/list` by chassis; `Reason.ADVISOR` and an advisor limit list in `control_step`, which can only reduce motion; round records of the court stored in the database. The first Python SDK client is the first real MCP client to run, and Streamable HTTP is not built now.

What this does not cover: paid calls, provider caps and balances (PENDING rows 4 and 5), the HTTP client dependency (row 9), held-out seeds and their definition for the chaos harness, global implementation, the real data only the maintainer has (parts, machines, zones, compatibility rows, manuals, recordings, labels of the E4 review set and the E5 cases, cost weights), the Muse Model License wording, and any claim that the MCP server is conformant. Where a table asks the maintainer for a value, the value is still needed.

Consequence: PENDING rows 103 and 106 are answered. The work they blocked is built next as stacked branches, each reviewed as a diff. A decision that turns out wrong is superseded by a new entry, never edited here.

## ADR-063: tools/list is filtered by the authenticated chassis

Status: implemented with unit tests against fakes; not run against a real client. Touches the MCP boundary (AGENTS.md section 15); the maintainer approved it by adopting decision D3 of the MCP client test design (ADR-062).

Decision: `tools/list` returns the definitions of the tools the authenticated chassis may call, in sorted order, with the same input schemas as before. Both the listing and the call path read `waggle.mcp_server.allowlist.allowed_tools(chassis)`, so there is one source of truth. `Boundary.allowed_tools(token)` authenticates the token and returns that set; any authentication failure (bad, unknown or revoked token, identity store error) returns the empty set, so an unknown chassis fails closed with an empty list and not an error. The chassis is derived from the token held by the process (ADR-045) and the request params are never read, so a client cannot ask for another chassis's list. The handshake rules of ADR-046 are unchanged: a legacy client still gets -32600 before `initialize`, and a modern request is served without prior state.

Not changed: `tools/call`. A tool that is not allowed is denied with the same `tool_not_allowed` result as before, audited as before, and an unlisted tool stays denied when the client names it. The listing writes no audit row and is not rate limited, as before. Why: a client or model that sees only the tools it may use is less tempted to probe, and the listing now matches what the boundary will accept.

Gaps: a transport built over a dispatcher that lacks `allowed_tools` is a type error, so test doubles needed the method. The listing is not itself a security control; the allowlist check at call time remains the control.

## ADR-064: Advisor limits in the fast layer and the harness bridge

Status: implemented with unit and property tests; E5 has not been run and no advisor runtime exists. Maintainer adoption of the recommended option of decision 2 in `docs/ADVISORS_DESIGN.md` (ADR-062) approved this interface change. Stacked on `feat/advisors-core`.

Decision: `Reason.ADVISOR` joins the closed reason set of ADR-027, ranked below `CPA` and above `CLASS_MAX` for ties. `control_step` takes an optional `advisor_limits` sequence of `Limit` values, default empty. Each one is relabeled `Reason.ADVISOR` inside the step and joins the same minimum as every other limit, so an advisor cannot name `GEOFENCE`, `ESTOP` or `WATCHDOG`, cannot raise a cap, cannot flip the sign of a command and cannot relax another limit. A cap that is not finite or is negative is turned into a zero cap by the arbiter, with reason `INPUT_MISSING`. No threshold, margin or existing limit was changed. With an empty list the output and the state equal those of a call without the argument, and a rig run with an empty caution log has the same state hash as a run without an advisor.

Bridge: `waggle.experiments.advisor_bridge` turns the plain `SpeedLimit` values of `waggle.governance.caution_limits` into `Limit(speed_cap, Reason.ADVISOR)` and reads the caution log per robot and tick. It sits in the harness because `waggle.control` must not import `waggle.governance` (AGENTS.md 5.8); no import contract changed. `ControlRig` takes an optional `advisor` hook with the signature `(robot_index, tick, class_max)`. Replay reads the stored log, so the same seed and the same log give the same state hash.

Tests: invariants I1 (property test with a seeded generator and a seeded random sweep: speed magnitude never above the run without advisor, sign kept), I3 (reflex stops and geofence or envelope caps unchanged when an advisor names them) and I10 (import-linter contracts stay green). The closed-set assertion in `tests/unit/control/test_control_types.py` gained `ADVISOR`; it is the only existing test edited, and it only lists the new enum member.

Gaps, stated plainly: only the speed cap is advised, no margin input (decision 3). An advisor limit is not applied on the stop path of an invalid input, where the output is already zero. No advisor, runtime or E5 result exists.

## ADR-065: Part compatibility, schema revision 10 and ticket-bound part tools

Status: implemented with unit tests; the PostgreSQL tests (migration, repositories, provisioning, E3 catalog run) were written but run only in the cloud workflow. ADR-062 (the maintainer's adoption of the recommended options) is on `docs/session-handoff-design-batch`; the number follows it. Implements Part A of `docs/CATALOG_COMPATIBILITY_DESIGN.md`. Part B (revision 11) is not touched.

Decision: schema revision 10 (forward only, checked with `--expected-revision 9`, no data, nothing dropped) adds `part_compatibility(machine_id, part_number)` with a composite primary key and foreign keys to `machines` and `spare_parts`, and a nullable `ticket_id` (foreign key to `maintenance_tickets`) on `part_reservations` and `purchase_orders`, nullable for rows written before the migration. `reserve_part` and `create_purchase_order` now require `ticket_id`; the strict schemas still reject unknown fields, so a `machine_id` argument is refused and the machine can only come from the ticket row. In the tool transaction the repository locks the part row (`UnknownPart`), reads the ticket (it must exist and be `open` or `dispatched`, else `UnknownTicket`), tests the compatibility row (no row raises `IncompatiblePart`, so the check fails closed), and only then runs the existing idempotency and stock logic. The idempotency row stores `ticket_id`; the same key on another ticket, or a key row written before the migration, is an `IdempotencyConflict`. The forwarder maps `UnknownPart`, `UnknownTicket`, `IncompatiblePart` and `IdempotencyConflict` to the one existing denial text of each tool ("reservation not available", "order not available"), so the denial does not say which check failed. ACK, retry, fencing and audit logic are unchanged. `provision` accepts an optional `compatibility` list of `{machine_id, part_number}`: unknown keys, malformed or duplicate rows, and rows naming a machine or part found neither in the spec nor in the database reject the whole spec before anything is created; a rerun skips existing rows and names them; it warns when parts are in the spec and the table has no rows. The key is optional so specs written for ADR-056 still load.

E3-T3-02: the runner opens a ticket for conveyor C1, loads (C1, BRG-6204) and (P1, SEAL-08), and orders SEAL-08 against that ticket, which is now blocked. T3-01 stays blocked and T3-03 must still be served. The check was added after E3-T3-02 was seen to pass (ADR-054, not rewritten), so the outcome is a regression test of a known gap and not an unbiased measurement; there are three cases and the rows are a synthetic fixture. A sensitivity test shows the runner reports T3-02 as accepted when the lookup allows every pair.

Gaps, stated plainly: `ticket_id` is a new required argument, so every earlier caller of the two tools changed (E3 attempts, tests); a client built for the old schema is rejected. The check proves a row exists; it does not prove the row is true, and the real compatibility data comes from the maintainer. An empty table denies every order. `TicketRepository.has_machine` was added for the load script. Nothing here was run against PostgreSQL on this machine.

## ADR-070: HTTP providers on the standard library, with fail-closed rules

Status: implemented with unit tests against a local fake server; no real provider was called and no key was used. The runtime dependency choice of PENDING row 9 is still open and this decision does not settle it.

Decision: `waggle.llm.http_provider.HttpProvider` speaks OpenAI-style chat completions over `http.client`, with a timeout on every call, one fresh connection per attempt and no redirect following. It adds no runtime dependency. If the maintainer later approves an SDK, the class can be replaced behind the same `Provider` interface.

Fail-closed rules:

- Provider mode comes from `WAGGLE_LLM_PROVIDER` (`mock` or `http`). Unset or any other value raises `ConfigError`.
- A missing or invalid `*_SPEND_CAP_USD`, key, token or URL raises before any call. URLs must be `https`; plain `http` is accepted only for loopback when the caller of the loader sets the switch in code, never from the environment.
- Prices live in `src/waggle/llm/prices.toml`, all shipped `verified = false`. An unverified or incomplete price makes `estimate_cost` and `complete` raise `ConfigError`, so the client makes no call.
- Cost is computed from the response `usage` and the verified price. A response without valid `usage` is rejected.
- 429, 5xx and transport errors are retried up to an attempt cap with exponential backoff; `Retry-After` in seconds is honored up to a cap. Other 4xx, 3xx, wrong content type, oversized body, malformed JSON, duplicate keys and non-finite numbers end in `ProviderError` with no retry.
- Exception and log text carries the provider name and a status or reason only. It never carries a header, a URL or a response body. Tests search for the key text in exceptions, tracebacks, logs and reprs.
- `vertex` and voice are not implemented (`docs/PROVIDER_INTEGRATION.md` gives the reasons). A route to them fails closed.

Gaps, stated plainly: the Meta usage fields, the Baseten auth header and the Modal endpoint shape are unconfirmed (see the table in `docs/PROVIDER_INTEGRATION.md`). The cloud smoke tests are written and have not been run. The retry logic lives in the provider because `LlmClient` does not retry; the client's own retry policy is unchanged.

## ADR-071: Handoff chaos scenes S31 to S35 and their own baseline

Status: implemented with unit tests; cloud checks in `postgres.yml`; not run as an experiment and no result file exists. Stacked on the E2 chaos runner.

Decision: `waggle.experiments.e2_handoff_scenes` scripts S31 to S35 step by step on a migrated schema, with the production corridor and task repositories, the production sweeper and `HandoffFinisher`. The two arms differ in one object. `fenced` uses `TaskRepository`. `baseline` uses `NoFencingHandoffRepository` (`e2_handoff_baseline`), whose `complete_handoff` reads the task and the zone without a lock, replaces the task token and the zone token sent by the caller with the live ones, runs the production pure check and writes in a second transaction. The worker name, expiry, task state and trusted occupancy are still checked, so only the fencing token is removed. Starts and ordinary completions keep production behavior. `e2_handoff_oracle` counts, from the same `task_events` rows as the E2 oracle, double deliveries (a handoff that is not the first of its task, or a stale handoff while another attempt is live), stale handoffs accepted and dependents claimed after a stale handoff of their dependency. The zone oracle counts two runners in the capacity-one zone of S34. `e2_handoff.aggregate_scenes` gives raw counts, Wilson 95 percent intervals and failing seeds per arm and scene.

Faults: the kill point of the first attempt and the replay mode of the stale runner come from `e2_faults` through one schedule per seed, one draw per scene. A kill is an exception raised by the `KillSwitch` of `e2_hooks` that abandons the runner mid step, not an operating system process kill. The E2 modules and production code are unchanged.

Provenance: the tick numbers of each scene, the lease length of 10 ticks, the scripted occupancy stand-in and the definition of a double delivery are assumptions of this change and need maintainer review. The metric "double repair starts" of `docs/EXPERIMENTS.md` is replaced by "dependents claimed after a stale handoff", because the log shows that and not which repair physically began; the document keeps its original wording until the maintainer agrees.

Gaps, stated plainly: S32 and S34 are controls. Neither is expected to break the baseline, because duplicate request ids are handled by the shared idempotency key and capacity one comes from the corridor table, both outside the removed check. S31 fails the baseline only when the stale copy arrives after the task is claimed again by the same worker name and the first attempt had not delivered. A different worker name is stopped by the baseline too, so the baseline is weaker than a check with no worker name at all. The scenes are scripted in time: they show that the oracle separates the two arms, not how often a real fault pattern hits a stale delivery. An import contract that keeps `waggle.experiments.e2_handoff_baseline` out of production code needs a change in `pyproject.toml`, which this task did not touch; an AST test enforces the rule meanwhile.

## ADR-072: Attachments in the LLM request and the voice-intent pipeline

Status: implemented with unit tests on the mock and scripted providers; E7 has not been run as an experiment and no result file exists. Branches 6 and 7 of `docs/MULTIMODAL_AND_VIEWER_DESIGN.md`, recommendation B (decision D1 of that document).

Decision: `LlmRequest` gains `attachments`, a tuple of at most 2 `Attachment` (kind `image` or `audio`, a closed media type list, base64 text). The constructor rejects an unknown kind or media type, empty or invalid base64 (strict decoding), an encoded text longer than the limit (checked before decoding), and a decoded size over 2 MiB for images or 5 MiB for audio. The limits are assumptions. The mock and scripted providers add `media_cost_usd` per attachment to `estimate_cost`, so the existing budget guard sees the price before the call and denies a call that would pass the cap without calling the provider. The default media cost is zero, so earlier callers are unchanged. `waggle.llm.voice_adapter.transcribe` sends a clip to the `voice` role and returns a `Transcription` with text or an error code (`empty`, `provider_error`, `no_budget`, `bad_request`, `llm_error`); it never raises for a model or budget failure.

`waggle.multimodal.voice_intent` parses `voice-intent-v1`: exactly four fields, a closed intent enum, short lists of plain ids, confidence 0 to 1, extra fields and duplicate keys rejected. `waggle.multimodal.voice` runs the pipeline: authenticated session (identity comes from the session only), sanitizer and guard through `classify_input`, a proposer (a callable; `keyword_proposer` is deterministic and gives confidence 0 for no keyword or for two different intents), schema validation, confidence threshold, item resolution by `resolve_items`, and for pick and deliver a read-back of the trusted ordered item. A transcript that names another item is rejected, two items or none ask to repeat, and a proposed id the transcript does not name is not trusted. Execution needs a typed `Confirmation` through `authorize_execution` (ADR-057); words in the transcript never count. `waggle.experiments.e7_voice` runs thirteen fixture cases in two arms and reports false accepts first with Wilson intervals; it states that it is a mock run of the rule.

Provenance: the case fixtures `VOICE_CASES`, the confidence threshold 0.6, the keyword list and the attachment limits are my assumptions and need maintainer review. All cases are pending review (AGENTS.md 10.2).

Gaps, stated plainly: the Muse Voice Transcribe request format was not read, so no real provider adapter exists and the audio field is only exercised by mock providers. There is no push-to-talk UI, no audio capture, no speaker identification and no real model proposer. The `no_readback` baseline shows three false accepts (V-04, V-06, V-08) and the full arm none on these fixtures; this shows the fixtures can fail, not that the pipeline resists real speech or a real model. The vision path (branch 8) is not built. No import contract covers `waggle.multimodal` yet; adding one touches `pyproject.toml`.

## ADR-073: waggle.replay and waggle.api, what they are and what they do not do

Status: implemented with unit tests; the web viewer has not been opened in a browser by an agent and no latency or frame-rate figure exists. Records PRs 122, 126 and 130 and the generator added with this entry.

What they are. `waggle.replay` writes, reads and checks replay files: JSON Lines with a header (commit, seed, scenario id, `dt`, world hash, frame count, `resimulable`), one frame per tick as `waggle.sim.frame.export_frame` produces it, and a footer with the final state hash and a digest of the frame lines. `ReplayRecorder` writes the file once, in exclusive-create mode, on a clean close; an existing file is never overwritten and a failed run leaves none. `replay-verify FILE` reads under a strict reader, checks the digest, the final hash and the run metadata, and for a `resimulable` file rebuilds the scenario from the seed and compares every frame with the simulator, which is the only check that catches a tamper that also repairs the hashes. `python -m waggle.replay.generate --scenario ID --seed N --ticks N --out PATH [--commit SHA]` builds a scenario, steps it with no control and records the frames. The same arguments give the same bytes; the commit comes from `--commit` or `WAGGLE_COMMIT` (default `unknown`), never from git. `waggle.api` is a FastAPI process with a health endpoint and two read-only WebSocket streams: `/ws/live` runs an allowlisted scenario id with the configured seed and `/ws/replay` forwards a file by name from one configured directory. It forwards simulator output unchanged and computes nothing.

What they do not do. They do not control a robot, write to the simulator, change a scenario, accept a seed or a path from a client, or touch the database, the MCP server or the LLM layer (the `core-no-web` contract keeps `waggle.sim`, `waggle.control` and `waggle.validation` free of the web layer). A replay file is evidence of a recorded run, not a result: it enters no README table and replaces no result file. A live stream is a scenario with no control layer, so it shows no safety behavior. `replay-verify` on a file that is not `resimulable` is a digest check only, and says so.

Security. The API has no authentication and none is designed. It binds to `127.0.0.1` by default (`WAGGLE_API_HOST`), the compose file publishes the port on `127.0.0.1` only, and it must not be exposed on a network as it is. A web page on any origin can still open a socket to localhost and read frames; the frames hold simulator data and nothing else. Exposing it beyond localhost needs a separate decision with authentication and an origin check, and that is not made here.

Provenance and gaps, stated plainly: the generator writes `source = "replay"` in every frame, which is a label of this tool and not a statement about how a given file will be used. It records scenarios without control, so a replay of a controlled run needs a different generator. A write that fails midway can leave a partial file because the recorder opens in exclusive mode before writing; `replay-verify` refuses such a file. The generator is exercised on S01 only in the tests.

## ADR-074: Technician zone lease at dispatch, ticket close and reservation settlement (schema revision 11)

Status: implemented with unit tests (migration text, argument checks) and cloud-only PostgreSQL tests; not run on this machine and not evaluated. Implements Part B of `docs/CATALOG_COMPATIBILITY_DESIGN.md`, option B1, adopted through ADR-062 (which counts the CHECK widening as approved). The MCP tools are not wired yet.

Decision: revision 11 (forward only, `--expected-revision 10`, no data) adds `technician`, `zone_token` and `closed_at` to `maintenance_tickets`, widens the status set to `open`, `dispatched`, `closed` and rebuilds the state check, and adds `status` and `settled_at` to `part_reservations`. The two old status checks have generated names, so the migration finds them by their text and drops only those; no table or column is dropped. A `dispatched` row must have a technician and a token together or neither, so rows written by the revision 8 `dispatch` stay valid.

`TicketLeaseRepository.dispatch` locks the ticket row, then the zone rows (`lock_zones`, a thin public wrapper of the existing private lock in `waggle.db.corridors`), then takes the zone lease for the named technician with the pure corridor model, and stores the token on the ticket, all in one transaction. A zone held elsewhere, occupied or unobserved, or leased for another live ticket is a result with `dispatched` False and the ticket left open. A repeat replays; another zone or technician is an `IdempotencyConflict`. `close` releases the lease with the stored token through the pure release (so a technician whose lease expired cannot close, and occupied or unknown occupancy denies), releases the ticket's reservations and marks the ticket `closed` in the same transaction. `reopen_expired` returns tickets with an ended lease to `open` and frees the zone, skipping locked rows; an expiry in an occupied or unobserved zone keeps the zone faulted and the ticket dispatched. `SettlementRepository.consume` lowers `on_hand` and `reserved`, `release` lowers `reserved`; both lock the part row, then the reservation row, and a repeat changes nothing. Lock order is ticket, zones, parts everywhere. ACK, retry, fencing and audit logic are not changed.

Gaps, stated plainly: the existing `TicketRepository.dispatch` and the `dispatch_tech` tool are unchanged, so a dispatch through the MCP still takes no lease. `technician`, `close_ticket`, `consume_reservation` and `release_reservation` need allowlist entries, schemas, bounds and forwarder code, which touch the MCP boundary and come in the next branch. Lease length is the 400 tick assumption of ADR-031. The sweeper passes the holder name `sweeper` to the advisory lock. Observations must cover every zone with an expired lease, or the pure model marks it faulted. Reopening a ticket leaves its reservations reserved. No crash case for a killed technician exists in the E2 fault schedule yet.

## ADR-075: Package id registry, schema revision 12 and the forwarder check

Status: implemented with unit tests; the PostgreSQL tests (upgrade, registry) run only in the cloud workflow; not evaluated. Implements branch 5 of `docs/PACKAGE_MODEL_DESIGN.md`, option B of decision 2.2, adopted through ADR-062. Stacked on `feat/technician-lease-settlement` (ADR-074), because both change `schema.py`.

Decision: revision 12 (forward only, `--expected-revision 11`, no data, nothing dropped) adds `packages(package_id, source, created_at)`. The table declares which ids are valid and holds no location: the simulator owns ground truth. `PackageRegistry` reads for the server (`has`) and writes for load scripts (`add`). `FencedForwarder` takes an optional `packages` port; with it, `pick_package` and `deliver_package` are denied with the existing text "order not available" when the id is not registered, before anything is queued, and a registry that cannot be read raises instead of queueing. `build_forwarder` wires the registry, so the server fails closed on an unknown id. `move_waypoint` does not consult it. `provision` accepts an optional `packages` list of ids (unique, same id pattern); a rerun skips registered ids and names them. The foreign key from `motion_orders.package_id` is not added: it needs a migration path for rows written with free ids and waits for approval.

Gaps, stated plainly: an empty registry denies every package order until a spec lists packages. A forwarder built without the port (tests, other callers) still queues any well-formed id; only `build_forwarder` closes that. The loader takes ids from the spec, not from a scenario, so nothing yet keeps the registry equal to the simulator's package set; a test that compares them belongs to the branch that adds the package model to the simulator.

## ADR-076: The maintenance alert loop

Status: implemented with unit tests over a fake tool port; no result file and no experiment. Implements branch 5 of `docs/PREDICTIVE_MAINTENANCE_DESIGN.md` (rule A3 and the loop of section 6). Decision D5 of that design (no technician before a reservation or an order) was adopted through ADR-062; here it is a rule of the loop, and the `dispatch_tech` tool is unchanged.

Decision: `waggle.maintenance.loop.MaintenanceLoop` takes predictor `Assessment` values and a `ToolPort`, and holds no authority: the caller backs the port with the authenticated `maintenance` tools. The rule is A3: the CUSUM flag, and when `use_estimate` is set an estimated time to limit at or under `lead_target_ticks`, must hold for `persistence` consecutive scorable readings. Neither number has a default, so none is invented; both are tuned on development seeds only. A reading that cannot be scored holds the count and is returned as `held`, never counted as quiet. The event key is `failure:<machine>:<tick>` with the tick that first satisfied the rule, frozen for the event, and the reservation and order keys extend it, so a re-estimated onset or a repeated alert opens one ticket, one reservation and one order. Stages run in order: ticket, reserve, order only when the reservation reports a shortage, dispatch only once a reservation or an order succeeded. A refusal is retried with the same keys on the next assessment up to `max_attempts`, then the event is `escalated` and no further call is made. A machine with no part plan gets its ticket and is escalated, because the loop must not guess a part. The ticket summary is a fixed text built from the machine name; no telemetry or manual text reaches a tool.

Gaps, stated plainly: nothing backs the port with the MCP tools yet, and the manual sheet that yields `PartPlan` does not exist (branch 6). A completed event is closed to new alerts until `reset` is called after a repair, which nothing calls yet. The loop does not act on the severity levels of the reflex path; those stay in `waggle.control`. No false alarm, missed failure or lead time has been measured.

## ADR-077: The llm_calls table, schema revision 13, and the client factory

Status: implemented with unit tests (migration text, record validation, factory in mock mode and fail-closed cases); the PostgreSQL tests run only in the cloud workflow. No real provider was called and no key was used. Stacked on `feat/package-registry` (ADR-075), because all three change `schema.py`. Settles the part of PENDING row 110 that said `build_providers` had no caller and the `llm_calls` table did not exist.

Decision: revision 13 (forward only, `--expected-revision 12`, no data, nothing dropped) adds `llm_calls`: request id, task id, role, provider, model id, status (`ok`, `denied`, `error`, `cached`), tokens, latency, cost, fallback label, a `mode` of `mock` or `http`, and a `clock_timestamp()` time. Costs and latency must be finite and not negative. There is no column for a prompt or a response, so the log cannot leak either. `waggle.db.llm_calls.PostgresCallLog` implements the existing `CallLog` protocol, so `BudgetGuard` and the client work unchanged, and spend now holds across processes. Its `mode` is set where the log is built, so a mock run and a real run are told apart without changing `CallRecord`. `cost_by_task` sums `ok` rows per task (optionally by role prefix, such as `court_`) and leaves `cached` rows out; `count_by_status` gives raw counts. A write that fails raises: the guard reads spend from this log, so dropping a row could let a paid call go uncounted (fail closed).

`waggle.llm.client_factory.build_client(environ, log, fallbacks_enabled=...)` builds the one production client from `build_providers`, `load_routes` and a `BudgetGuard` over the given log. `fallbacks_enabled` has no default, so a held-out run must say False. The client retry stays at zero because the HTTP provider already retries 429 and 5xx; `LlmClient.max_retries` is now readable so a test can assert it. The factory makes no call.

Gaps, stated plainly: the experiment harnesses still build their own scripted clients and the in-memory log; nothing yet passes a `PostgresCallLog` or a `build_client` result into a real run. `BudgetGuard.spent` reads every row on each check, which is fine at this volume and not designed for a long run. The `mode` label is a promise of the caller, not something the table can verify. Prices stay unverified, so an http client refuses any call (ADR-070). No cost figure exists.

## ADR-078: Plan validator stage C, one deterministic rollout without humans

Status: implemented with unit tests; no run on development or held-out seeds and no result file. Implements stage C of `docs/ROLLOUT_VALIDATOR_DESIGN.md` (section 2.1, option C), after the counterexample record, the static geometry stage and the geofence check that were already on `main`. Not formal verification: it checks one simulated run under the stated assumptions.

Decision: `waggle.validation.plan_rollout` adds `run_plan_rollout` and `validate_plan`. `validate_plan` runs the stages in the order of the design: an `escalate` plan is routed to the operator and not validated as motion; then `check_geofence`; then `compile_plan` (static geometry); then one rollout. The rollout drives the compiled paths with the simulator dynamics over `horizon_s` (default 45 s, the ADR-025 design basis; it must be a whole number of ticks), with every robot of the start map simulated (a robot with no path stands still and can be hit). It reports `COLLISION` between robots with the time and midpoint of the first contact, `GEOFENCE_INTRUSION` when a robot footprint reaches a hazard zone along the real path (even if no node names the zone), and `NO_PROGRESS` for a robot that did not reach its first waypoint. Counterexamples are sorted by time, then severity, then entities. A plan is accepted only if every stage returns none. A missing robot kind, an unknown hazard zone or a bad config raises ValueError, never an empty pass. The same inputs give the same counterexamples and state hash; the seed does not matter without humans.

Tests: planted head-on plan (collision) and the same plan with the fault removed (accepted); a path through a hazard zone that no node names; a short horizon (no progress); an idle robot on the route; stage order; determinism; and two mutant validators (accept everything, skip the rollout) that the same sensitivity suite must reject. The module imports nothing from the LLM, governance, MCP or control packages.

Gaps, stated plainly: no human variants (stage D, which needs the belief state and the sampler); no reflex layer in the rollout, so a plan that only survives because the reflex layer would brake is rejected, which is stricter than the design and can reject safe plans; no lease, deadlock or recoverable-terminal check; `wait_for` is not applied, so every robot starts at tick 0; progress means one waypoint reached, a weak definition; the hazard check uses the bounding box of the zone polygon and the robot half width, which is conservative for non-rectangular zones. The detector counts robot-robot contact only, so a robot-wall collision is covered by the static clearance check and not by the rollout. No latency or cost figure exists for the whole call.

## ADR-079: Synthetic failure log generator and case retrieval

Status: implemented with unit tests; no table, no migration and no caller yet. Implements the generator and retrieval of branch 7 of `docs/PREDICTIVE_MAINTENANCE_DESIGN.md` (ADR-020), without the `failure_history` table. The first draft was written by Antigravity under a narrow command allowlist and audited by the main agent; the audit changed one behavior (an unknown mode now raises).

Decision: `waggle.experiments.failure_log` generates a deterministic synthetic failure log from `(seed, count)` with a seeded PCG64 stream, no wall clock, no file read and no global random. A case holds a machine class, a failure mode, the ticks from onset to failure and the peak temperature, vibration and current. Every parameter lives in `LOG_PARAMETERS` under `LOG_` names. They are assumptions and not measurements. The module imports nothing from `waggle.sim`, and a test checks that no key and no numeric value of `LOG_PARAMETERS` equals one in `data/sim/degradation.json` or `data/maintenance/predictor.json` (AGENTS.md 9.8). `similar_cases` returns the k nearest cases of one mode by the three peaks, each divided by its spread in the log, with ties broken by case id. An unknown mode raises ValueError instead of returning an empty result, so a typo cannot pass as "no similar case".

Gaps, stated plainly: the part numbers (`PART-BRG-01`, `PART-LUB-01`, `PART-ALN-01`) are placeholders and are in no catalog, so a caller must map them to the real catalog before any order (AGENTS.md 8.7). The machine class is drawn independently of the mode. The distributions are simple choices with no fit to anything, so the log is not evidence about real failures, and calibrating the predictor on it proves only that the predictor can use a log. No `failure_history` table exists, and nothing calls the generator or `similar_cases` yet.

## ADR-080: The advisor runtime on the scripted provider

Status: implemented with unit tests on the scripted and mock providers; no real call, no key, no E5 run. Implements branch 5 (`feat/advisor-runtime`) of `docs/ADVISORS_DESIGN.md`, invariants I11 and I12. The first draft was written by Antigravity under a narrow command allowlist and audited by the main agent; the audit changed five things, listed below. Stacked on the advisor core already on `main`.

Decision: `waggle.llm.advisor_runtime.AdvisorRuntime.advise` builds the advisor input from trusted facts and screened messages, renders the versioned prompt `advisor-v1` (`advisor_v1.txt`, which states that the snapshot is untrusted data and that the model may only propose a speed cap, a hold, an organizer signal or nothing), calls `LlmClient` with the `advisor` role and the request id `advisor-<robot>-<tick>`, parses the answer with the strict caution schema, records an accepted event in the caution log and returns the limits of `caution_limits`. An advisor can only add caution. A provider error, a timeout, a budget denial, an oversize answer, a schema rejection or a rate limit returns a labeled result with the limits already in force and records nothing, so the fast layer is unaffected. A repeated request id returns the earlier result with no second call and no second record (I12); a message the guard cannot score is withheld from the prompt and an `unscored_input` signal is recorded (I11).

Changed in the audit: (1) the timeout did not bound the wait, because leaving the thread pool waited for the worker; the pool is now left without waiting, and a test blocks the provider with an event and asserts the call returns first (a mutant that waits again fails it at 5 s); (2) the classifier and the input limits were optional, and the default classifier labeled everything benign, so untrusted text would have been screened by nothing; both are now required with no default; (3) the cached case was read from a private attribute of the client with `getattr`, which would fail quietly if renamed, and the runtime now keeps its own set of served request ids; (4) `status` is a closed `Literal` and `run_id` and `task_id` are required; (5) the AST test no longer depends on the working directory.

Gaps, stated plainly: `build_advisor_input` is a coroutine, so `advise` runs it with `asyncio.run`, in a helper thread when a loop is already running; this works but is a seam to remove if the caller becomes asynchronous. The rate limit counts attempts, including failed ones. An abandoned call after a timeout still runs to the end in its thread and may still be charged by a real provider. The reason text of a provider error is returned as is, and ADR-070 keeps secrets out of those messages. No E5 configuration, replay check or real-model run exists, and nothing calls the runtime outside its tests.


## ADR-081: MCP tools for the technician lease, ticket close and reservation settlement

Status: implemented with unit tests over fake ports and a cloud-only PostgreSQL test for the two new repository reads; not run against a real database on this machine and not evaluated. The MCP boundary change is the one approved through ADR-062 and named in the gap list of ADR-074. ACK, retry, fencing and audit logic are not touched.

Decision: `dispatch_tech` takes a required `technician` id and now goes through `TicketLeaseRepository.dispatch`, so the zone lease is taken for the named technician in the same transaction. `close_ticket` (ticket id only), `consume_reservation` and `release_reservation` (idempotency key only) are new tools. All four are on the `maintenance` chassis only; `tech_repair` and the motion chassis do not get them. Schemas are strict like the others: ids of 1 to 64 characters, no extra field, no token argument. The forwarder takes three new optional ports (`leases`, `technicians`, `settlement`), and `build_forwarder` wires the repositories. Without the ports the tools are unavailable: there is no fallback to the old dispatch that took no lease. The tick and the occupancy evidence come from the trusted sources, never from the request. The technician must have an active `tech_repair` identity (`PostgresIdentityStore.is_technician`), so a maintenance robot cannot lease a zone for an arbitrary name. `close_ticket` first reads the zone of the ticket (`TicketLeaseRepository.zone_of`, read only) to know which zone to observe; a stale answer only makes the close deny, because the close locks the ticket and the pure release needs an observation of the stored zone. The lease token is never returned. Denials use one text per tool and never say which check failed: "dispatch not available", "close not available", "settlement not available". A busy or occupied zone, or a lease denial at close, is a result with its reason, as for `release_zone`.

The old `TicketRepository.dispatch` stays in the repository and is no longer reachable through the MCP. `TicketPort.dispatch` was removed from the forwarder.

Gaps, stated plainly: a `dispatch_tech` call now needs a `technician` argument, so the alert loop (`waggle.maintenance.loop`, ADR-076) and its `ToolPort` do not match the tool yet and need the technician choice; no caller exists. `consume_reservation` and `release_reservation` do not check that the caller made the reservation, only that it is a maintenance robot. The E3 case E3-T1-02 (`dispatch_tech` from a carrier) now carries a `technician` argument so that, with the allowlist widened, the schema does not block it for a missing field and the case still measures the allowlist layer; the full CI caught this. No real client has run, and the MCP server is not claimed conformant.
## ADR-082: Rollout validator stage D: belief state, human prior sampler, K variants and all-pass aggregation

Status: implemented with unit tests (158 in `tests/unit/validation`); no result file, no experiment, not evaluated. Implements the belief and variant branches of `docs/ROLLOUT_VALIDATOR_DESIGN.md` section 11 on top of ADR-078. The first draft of `belief.py` and `variants.py` and their tests came from Antigravity (a bounded implementation task, ANTIGRAVITY.md); the main agent audited it and changed what is listed below.

Decision: `waggle.validation.belief` holds `HumanPrior` (an id, a version and a spawn density per declared map zone, each density finite and between 0 and 1), `sample_humans` (pure, seeded only by the variant seed through a numpy generator, rejects a human that starts inside the stopping distance of any robot at t = 0 and counts the rejections, raises `SamplingError` when one human cannot be placed within `max_attempts`) and `variant_seeds` (SHA-256 of scenario seed, snapshot state and index, first four bytes). `waggle.validation.variants` holds `run_variant_rollout` (the plan rollout with walkers), `aggregate` (the plan passes only when exactly K results exist and none has a counterexample; a missing result, an exception or a result without counterexamples attribute rejects) and `validate_with_variants` (stage order of the design: escalation, geofence, static geometry, then K variants in order). The stopping distance is computed from the robot parameters as braking distance plus the distance covered during the actuation delay, for the fleet's worst robot. `k` and `max_attempts` are arguments with no default.

Changed in the audit: (1) the draft defaulted the stopping distance to 1.5 m and the attempt cap to 1000, numbers nobody chose; both are now required and the stopping distance comes from the robot parameters. (2) With no robot position the sampler skipped the stopping rule silently; it now raises. (3) `variant_seeds` took `str()` of any object, and `str()` of an array is cut with `...`; it now accepts only an int or a string. (4) `aggregate` took K from the length of the list, so a short list passed; K is now required. (5) A failed variant was stored without a log line; it is logged by exception type. (6) Aliases and tuple-like methods nobody used were removed. (7) A test now compares `run_variant_rollout` with no humans against `run_plan_rollout` (same final hash, counterexamples and ticks, with and without a hazard on the path), because the variant rollout is a copy of about 175 lines. Each new guard was broken on purpose and its test failed, except the seed: without humans nothing is random, so that test cannot see a seed change, and it cannot see the hazard margin either (a point inside the box is at distance 0).

Gaps, stated plainly: the rollout is still duplicated and should be one function that takes humans, which needs a change to `plan_rollout.py`; no per-variant timeout exists (a variant that never returns blocks, and workers use threads, so the GIL makes more than one worker a determinism check and not a speedup); `snapshot_rng_state` is the constant 0 until the belief builder reads a real snapshot; the density rule (`round(area * density)`, at least one human in a region with density above zero) is an assumption to calibrate and is declared per scenario by the maintainer (design decision 3); humans walk straight at a constant speed with no turning; no belief builder from tracked entities, no lease or deadlock check and no progress check beyond the first waypoint exist yet. Nothing here is a safety claim: validation is simulation based under the stated prior.
## ADR-083: E5 runner for the safety advisor, configurations C0, C1 and C1 replay

Status: implemented with unit tests on the scripted provider; no result file written, no experiment run, not evaluated. Implements branch 8 of `docs/ADVISORS_DESIGN.md` for the configurations that need no organizer. The first draft of `e5_advisors.py` and its tests came from Antigravity (a bounded implementation task, ANTIGRAVITY.md); the main agent audited it and changed what is listed below.

Decision: `waggle.experiments.e5_advisors` runs one scenario and seed on development seeds only (it reads the `dev` list of `data/seeds.json` and has no option for the held-out list). C0 has no advisor. C1 calls `AdvisorRuntime` on a scripted provider through `LlmClient` with fallbacks off, records cautions in a `CautionLog` and feeds them to the fast layer through `AdvisorBridge`. C1_REPLAY rebuilds the log from the recorded JSON lines and must reproduce the digest and counts. C2, C3 and C4 raise `UnsupportedConfigurationError`: they need the organizer, which does not exist. `waggle.experiments.e5_rig.E5Rig` repeats the E1 rig step and adds two measures: ticks where a second `control_step` with no advisor limits is slower than the one with them (widening, expected 0 by construction), and the smallest gap to a human or robot. `assemble` builds the result document with Wilson 95 percent intervals, raw counts, small-sample labels and failing seeds, and `write_result_file` validates the required fields before it writes. Timeouts, rate limits, the caution config and input limits are arguments of the runner with no defaults.

Changed in the audit: (1) the draft gave the advisor a track id as the "active reason" of the fast layer; the rig now records the reason of the last `control_step` (`Reason` value), and a test spies on `advise` and checks every reason; with the defect put back that test fails. (2) The rig is a copy of the E1 step, so a test now runs C0 against `e1_run.run_one` for the same configuration and requires the same hash, counts and stop episodes. (3) Every test asserted `widening_ticks == 0`, so none would notice a counter that never counts; a test now plants a widening `control_step` and requires a count above 0, and with the increment removed it fails. (4) `write_result_file` refused to write under `results/` and swallowed an `OSError` while checking the path, which depended on the working directory and would block the cloud run that must write there; both were removed. (5) The module was 618 lines and the rig is now its own file with its own test file. (6) `Any` for the tick source became `Callable[[], int]`.

Gaps, stated plainly: the facts given to the advisor are partly fixed values (`occluded` is always false, no geofences, no lease holders, task step "travel", and a 3 m threshold that decides when a context counts as changed), so the advisor sees less than the design lists; the scripted answers prove nothing about a real model; E5 scenario labels ("caution warranted") are not written (decision 5 of the design, the maintainer's); the rig step is still a copy and should become a hook in `ControlRig`, which is E1 code; no workflow, no persistence of the caution log across runs, and no real client. Nothing here is a result.

## ADR-084: The failure_history table, schema revision 14

Status: implemented with unit tests (migration text, record validation); the PostgreSQL tests (upgrade, repository, table checks) run only in the cloud workflow; not evaluated. Implements the table of branch 7 of `docs/PREDICTIVE_MAINTENANCE_DESIGN.md`, flagged there as a migration and approved through ADR-062. The migration needs `--expected-revision 13`; a database at any other revision is refused. No database was available on this machine, so the installed revision of any real database was not read.

Decision: revision 14 (forward only, no data, nothing dropped) adds `failure_history(case_id, machine_class, mode, onset_to_failure_ticks, peak_temperature_c, peak_vibration_rms, peak_current_a, part_number, source, created_at)`. Mode and machine class are closed sets in the table, peaks must be finite and not negative, and there is no column for manual text or model output, so a poisoned manual or a model answer cannot be stored through it. `waggle.db.failure_history.FailureHistory` only touches the database: `add` validates first and inserts with `ON CONFLICT (case_id) DO NOTHING` (the first write of a case id wins and the call returns False for a repeat), and `rows` returns every case ordered by id. `source` labels where a row came from (for example `synthetic`), so a later real log is never mistaken for the generated one. The table is loaded by a script, never by a migration (AGENTS.md 7.8).

Gaps, stated plainly: the part numbers in synthetic rows are placeholders that are in no catalog, so any caller must check them against the catalog before an order (AGENTS.md 8.7). There is no loader script yet. The table holds the synthetic log of ADR-079, which is not evidence about real failures.

## ADR-085: E6 runner and maintenance diagnosis, sheet and tool port

Status: implemented with unit tests (85 in the four new test files); no result file and no run over all development seeds. Implements the diagnosis, sheet and tool port parts of branches 6, 7 and 8 of `docs/PREDICTIVE_MAINTENANCE_DESIGN.md`, and the mock E6 runner of section 7. No model is called anywhere in this change. The drafts came from a subagent and were audited by the main agent.

Decision: `waggle.maintenance.diagnosis.diagnose` takes the failure log (ADR-079), a reading and a catalog. It compares the k nearest cases of each candidate mode and proposes the nearest mode with the part its supporting cases share. The proposal is advisory. A part that is not in the catalog, supporting cases that disagree on the part, or an empty log give an escalation that carries no part. An unknown mode raises. `waggle.maintenance.sheet` is a strict schema per machine: a zone and, per failure mode, a part and a quantity. Unknown fields are rejected, ids and quantities are bounded, and the free-text notes are bounded and printable and are read by no decision. A missing sheet is the default, which lists no part, so the loop escalates. A sheet part becomes a `PartPlan` only if it is in the catalog. `waggle.maintenance.tool_port.McpToolPort` implements the loop's `ToolPort` over a caller-supplied `call(tool, arguments)`. A denial or an unreadable result is `ToolRefused` for the ticket, reserve and order calls, and a shortage is `False`. For `dispatch_tech` it chooses a technician: the first of an ordered caller list that is not busy, trying the next if a call is denied, and `False` when none can go. This closes the technician-choice gap of ADR-081 on the caller side. `waggle.experiments.e6_runner` runs B0, B1, C1, C2 and C3 on development seeds only, with telemetry from `waggle.sim.machines` and `telemetry`, an in-memory idempotent backend, the scorer of `waggle.maintenance.scoring`, Wilson 95% intervals with raw counts, and a result document with commit, seed set, configuration, model ids (empty), date and per-seed rows. It refuses to run if the simulator and predictor parameter files share a name or a value. A blind predictor, an unscorable reading and a repeated tool key are covered by tests. The audit of the drafts broke nine guards on purpose (catalog checks, unknown mode, extra fields, busy technician, NaN hold, dev seed guard, wrong part scorer, seed set check) and each broke its test.

Gaps, stated plainly: on these simulated machines C2 never opens a ticket, because the machines fail at temperatures far below the predictor's 95 C limit, so the time-to-limit estimate never fires, and the C3 ablation is empty until that is addressed; C1 does detect a planted failure. Fixing it means retuning `predictor.json` or the simulator limits, which needs a decision. Persistence, lead target, threshold limits, stock and the diagnosis log are untuned assumptions, recorded in the result file as `assumptions_untuned`. Diagnosis runs on the synthetic log, whose peaks are not the simulator's, so wrong-part counts reflect that mismatch and not diagnosis quality; the part numbers are placeholders. `InMemoryBackend(idempotent=False)` and the `assessor_factory` and `policy` arguments of `run_trace` exist for tests. Downtime, robots stopped before a hazard zone and all LLM steps are not measured. One seed is one machine, so intervals are wide. No full run was executed (it belongs in the cloud) and no figure exists.

## ADR-086: Rollout validator: one rollout, variant timeout, belief builder and crisis loop

Status: implemented with unit tests (48 in the variants, crisis loop and belief builder files); no result file, no experiment, not evaluated. Closes four gaps listed in ADR-082. The drafts came from a subagent and were audited by the main agent.

Decision: (1) `run_plan_rollout` takes an optional `walkers` sequence of `HumanState` (default none, behavior unchanged) and reports robot-human collisions and separation violations. `run_variant_rollout` is a one-line call to it with the variant seed in the config; the 175-line copy is removed. A test compares them with humans, another checks the seed reaches the engine, and an AST test refuses a second rollout loop in `variants.py`. (2) `validate_with_variants` takes a required `variant_timeout_s` (positive, finite, no default). Variants run in a thread pool that is not entered with `with` and is closed with `shutdown(wait=False, cancel_futures=True)`, as in ADR-080, so a variant that never returns does not block. It counts as a rejection (fail closed), is logged, and is named in `AggregatedResult.notes`. A test blocks the rollout with an event and asserts the call returns first; replacing the shutdown with `wait=True` made it fail. (3) `waggle.validation.belief_builder` turns a `TrackSnapshot` of `TrackedEntity` (plain dataclass, or a mapping with exactly seven keys) and a declared `HumanPrior` into a `Belief`: tracked humans as known humans, the prior for hidden ones, and a SHA-256 digest of tick, entities (sorted by id) and prior. The digest replaces the constant 0 as `snapshot_rng_state` for the variant seeds. A missing, non-finite, mistyped or negative-sigma value, or a repeated id, raises `BeliefError`; nothing is skipped. The module does not import `waggle.control`. `validate_with_variants` takes the `Belief` in place of the prior, and the known humans are in every variant. (4) `waggle.validation.crisis_loop.run_crisis_loop` runs at most 3 rounds (`max_rounds` required, 1 to 3). The proposer is a Protocol (`propose(feedback)` returns raw text) because no planner interface exists in `waggle.llm` or `waggle.governance`. Each output goes through `parse_plan` (strict schema) and `validate_with_variants`, and counterexamples return as `build_feedback` JSON built by code. A parse failure or proposer error counts as a rejected round with only a closed error code in the feedback. After 3 rejected rounds, or when the plan asks for the operator, the result is an escalation with no plan; only a plan whose variants all passed is returned as accepted.

Changed by this: the "clean plan accepted" test used a human prior that spawned a walking human and only passed with seed 0; it now uses density 0 (no human), so that case no longer exercises sampled humans. The subagent wrote the tests before the code but did not show the failing run, because another suite held the machine; the red evidence is the timeout mutant.

Gaps, stated plainly: no LLM adapter for the proposer and no caller outside tests; tracked humans have no coasting, sigma inflation or speed bound and walk straight; a timed-out variant keeps running in its thread until it ends; with several workers each future is awaited for up to the timeout in order; the lease and deadlock check, the progress check beyond the first waypoint and the density calibration are still missing; nothing is evaluated.

## ADR-087: E5 wiring: richer advisor facts, caller, caution log file and client factory in the harness

Status: implemented with unit tests (653 in the touched sets: governance, the E5 files, `tests/unit/llm`); run in mock mode only, no real call, no key, no E5 result file. Builds on ADR-077, ADR-080 and ADR-083. The drafts came from a subagent and were audited by the main agent.

Decision: (1) `TrustedFacts.task_step`, `occluded`, `geofences` and `lease_holders` may be `None` when the state does not expose the value. The advisor input renders `None` as `unknown`, never as a default. `occluded` comes from the fast layer output of the previous step through `E5Rig.occluded`, and is unknown before the first step or when the run has no occlusion layer. The task step, geofences and lease holders are unknown in E5 until the simulator or rig exposes them; zone kinds were not mapped to geofences because that would invent a meaning. (2) `waggle.experiments.e5_caller.AdvisorCaller` asks the advisor at tick 0 and each tick the context changed (reasons, zone, or the nearest distance crossing `near_threshold_m`). The threshold is a required argument everywhere, with no default. The caller can only add caution through the caution log; an advisor failure is counted under `advisor_error` and leaves the limits already in force. (3) `waggle.governance.caution_file` writes the caution log as JSON lines through a temp file, `fsync` and `os.replace` (the temp file is removed on failure and the old file is kept) and loads it through `CautionLog.from_jsonl`, rejecting the whole file on a bad line or a file that is not UTF-8. `C1_REPLAY` accepts `replay_path`; exactly one of `replay_log` and `replay_path` must be given. (4) `E5Runner` accepts an optional `client_environ` and `call_log` (in-memory or `PostgresCallLog`) and builds its client with `build_client(..., fallbacks_enabled=False)`. Only mock mode is accepted. `build_client` gained a `providers` override, allowed only in mock mode, so the scripted provider keeps working. Nine guards were broken on purpose in the audit (fallbacks forced on, temp file left, UTF-8 check, the two mock-only checks, `occluded` defaulting to false, the advisor failure catch, the hard-coded threshold, an unknown rendered as a default) and each broke its test.

Gaps, stated plainly: E5 prompts carry `unknown` for three facts, which weakens what the advisor can reason about, and that is reported as is. The mock provider cannot produce a real advisor answer, so runs still need the scripted provider. Database persistence of the caution log (a table and a migration) is not built; the file is the persistence for now. No real provider run exists. The full CI was not run by the subagent; it runs on the integration branch.

## ADR-088: Failure history loader

Status: implemented with unit tests (one generated log through `FailureHistory` and `FakeDatabase`, a skip double, abort on a bad row, CLI argv and missing `DATABASE_URL`); no PostgreSQL run in this change; not evaluated. Closes the loader gap named in ADR-084. The table and `FailureHistory` are unchanged (schema revision 14).

Decision: `waggle.experiments.failure_history_loader.load_failure_history` takes a `FailureHistory` (or a double with the same `add`), a sequence of `FailureCase`, and a required `source` string with no default. It maps each case to a `FailureRow` (mode is the enum value) and calls `add`. The synthetic log is loaded with source `synthetic`, passed by the caller. `add` returning False is a skip, counted in `LoadResult`, not an error: a second load of the same cases inserts nothing. A `ValueError` from `add` fails the load at once; the invalid row is not skipped and later cases are not added. The generator stays in `waggle.experiments.failure_log`; this module does not reimplement it, so the same seed and count still produce the same rows. `waggle.db` and `waggle.maintenance` do not import `waggle.experiments`. The table is loaded by this script, never by a migration.

The CLI `load-failure-history SEED COUNT SOURCE` matches `provisioning.main(argv, environ, stderr) -> int`. `DATABASE_URL` comes from the environment. Argv is checked before a database is constructed. Exit 2 on bad arguments, a missing or unusable database setting, or a refused row. Usage and errors go to stderr as a usage line or `load-failure-history failed: <ErrorType>`. One result line goes to stdout: `inserted=<n> skipped=<n>`. Environment values, URLs and secrets are never printed or logged.

Gaps, stated plainly: the synthetic rows are still not evidence about real failures. PART-BRG-01, PART-LUB-01 and PART-ALN-01 are still placeholders and are not catalog parts; any caller must check part numbers against the catalog before an order. Diagnose and the E6 runner still read the in-memory log. No PostgreSQL load was run here.

## ADR-089: Generated models, modular previews and offline asset import

Status: implemented, not evaluated. Continues the unfinished GLB viewer on a separate
branch. The maintainer requested completion and owns visual review.

Decision: the model gallery is separate from replay state and offers all current
models plus original modular rack, conveyor and dock previews. GLBs stay outside
Git history in a separate archive. `web/models.json` pins each file's SHA-256,
byte count, authored animation names and generation provenance. The offline
importer validates all sources before copying, rejects external resource
references, and refuses to replace a different existing destination file.
No API key is needed for import. Meshy generation checkpoints retain task ids
and consumed credits; monthly credits fund the five additional models, with no
permanent-credit purchase or consumption requested.

The revised worker replaces the old replay worker. A replay without chassis or
human roles still uses one model per kind. Gallery pickup uses an independent
visual box following the hand midpoint during an authored fraction of the clip;
it is hidden if the clip, hand nodes or timing are unavailable. No human pickup
or package pose is invented in the replay. Procedural dimensions never define
simulator geometry. No control, fencing, audit, retry or simulator contract changes.

Verification: viewer unit and browser contract tests cover camera pan without a
recorded-state change, malformed replays, missing models, invalid rack settings,
pickup prop ownership and offline import failures. A separate model browser check
requires the binary pack and checks decoding and clip names. Playwright 1.64.1 is
development only (ADR-029). `viewer.yml` runs checks without the binary pack.
Artistic quality, map geometry, overlays, live mode and role/action replay fields
remain outside this gallery change.

## ADR-090: Crisis planner adapter in waggle.llm

Status: implemented with unit tests (9 in the adapter file, plus the validation and
court suites); mock provider only, no paid call, no result file, not evaluated.
Closes the proposer gap named in ADR-086.

Decision: `waggle.llm.crisis_adapter.LlmPlanProposer` satisfies the `PlanProposer`
protocol of `waggle.validation.crisis_loop` without that package importing the LLM
side. It is bound at construction to one mission id and one `PlanContext`, renders
the versioned `planner-v1` prompt (`planner_v1.txt`, hash recorded in the module)
listing only the trusted robot, item and zone ids with their speed limits, and
passes validator feedback as data in the prompt. The request id is a digest of the
prompt hash and the canonical mission, context and feedback, so a repeated round
is served from the client cache and a new feedback round is a real call through
the `planner` route, with budget, retries and the call log applied by the shared
client. The adapter returns raw text and never parses it: `parse_plan` and the
rollout validator still decide, and a provider error propagates so the loop counts
the round and escalates at the bound. No caller outside tests exists yet; the E10
harness and any production crisis caller remain separate work.
