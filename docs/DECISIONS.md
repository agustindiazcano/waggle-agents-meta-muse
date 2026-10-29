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

## ADR-018: Sensing model and predictive caution

Status: proposed. Designed, not implemented.

Context: a fast layer that reads ground truth hides what a real robot cannot see around a blind corner. The detector that scores E1 must stay exact.

Decision:
- Robots perceive through a simulated 2D lidar: ray casting against walls, racks and moving entities, with range, angular resolution, noise, dropout and occlusion, all seeded. The fast layer reads only what the lidar detects. The exact detector keeps using ground truth and never feeds the control code.
- Optional variant: human beacons that are visible around corners.
- Prediction: constant velocity extrapolation of each detected object, then the closest point of approach (time and distance) compared with the robot's stopping distance. Prediction can only add restrictions earlier. The worst-case separation envelope of the fast layer stays the floor.
- No learned model. Camera and vision stay out of the control loop.
- Lidar dropout or a stale scan makes the layer assume the worst case (conservative default, watchdog).

Consequences: E1 compares ground truth, lidar only and lidar with beacons, and envelope only against envelope with prediction. The lidar needs array math, so numpy as a runtime dependency of `waggle.sim` was approved by the maintainer (PENDING 22).

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
- Units and step: SI units (meters, seconds, radians). The simulation is 2D on the floor plane. Height is not modeled. Rendering is 3D (Three.js) and the FPV vision check renders the 3D scene. Fixed step dt = 0.025 s (40 Hz), one constant that every layer reads, never a wall clock. Every actuation delay must be an integer multiple of dt (the forklift 0.15 s is 6 ticks). The loader rejects a config that breaks this. The lidar runs at 10 Hz, every 4 ticks.
- Seeds: one root seed per run. Independent streams per entity and per subsystem come from numpy `SeedSequence.spawn`, so adding an entity does not change the other streams. A generator is built only from a spawned child, with `default_rng(child)`.
- Determinism scan: a test parses the sources of `waggle.sim` and `waggle.control` with `ast` and rejects global `random`, `time`, `datetime`, network, `os.urandom`, `uuid`, `secrets`, global numpy random functions, `np.random.seed`, `default_rng` without a `SeedSequence` child, builtin `hash()` on strings, and iteration over a set when building state or the hash.
- State hash: a canonical serialization with sorted keys and floats rounded to a fixed number of decimals (documented next to the code). No golden hash values are committed. Determinism tests compare two runs in the same process. Every result file records the numpy version and the platform.
- Reproduction scope: exact reproduction holds on the same platform and numpy version. Published results come from the cloud run (Linux).
- Ground truth versus observation: `waggle.control` never reads ground truth. It reads only the types in `waggle.sim.observations`. That module is a leaf: it imports nothing from the project, and `waggle/sim/__init__.py` imports nothing, because import-linter also flags indirect chains. The contract `control-no-ground-truth` forbids `waggle.control` from importing `world`, `entities`, `engine`, `detector` and `sensors` in `waggle.sim`.
- Detector conventions: closed sets, so an exact touch counts as contact. Contact is a collision. Separation below the declared margin is a violation. The human footprint is a disc or an oriented rectangle, declared per scenario.

Consequences: results are comparable run to run on one platform and are not claimed bit-identical across platforms. The lidar rate and the delay rule are checked at load time, not at run time.
