# Waggle Hive: Project Plan

Build window: Oct 27 to Nov 3, 2026. Buffer and submission: Nov 4. Submission deadline: Wed Nov 4, 9:00 PM ET (23:00 in Argentina, since US daylight time ends Nov 1). Confirm the exact time on the submission platform.

The plan is organized by phase, not by date. A phase ends when its exit criterion is met, and the next one starts. Phase order is build order. The full scope stays: nothing is cut. The order below is the build order. Phase 8 stays reserved from Nov 3 morning.

## Priority order

Source: AGENTS.md section 18. Phase 8 stays reserved from Nov 3 morning.

1. Simulator with snapshot and fork, exact detector, fast layer with occlusion cap, E1, end-to-end slice.
2. Leases, atomic corridor locking, fencing, hand-off, E2.
3. MCP boundary, guard, injection matrix E3, full court E4.
4. Crisis replanning loop and E10.
5. Technical viewer with overlays (envelopes, lidar shadows, rollout ghost paths).
6. Predictive maintenance full pipeline E6, per-robot advisors E5, vision and voice E7.
7. E8 extended, E9, GLB models.

Reserved time: delivery (README tables, demo video, live VM, submission) from Nov 3 morning.

Gates, decided by the maintainer: G1 Oct 30 night, Phase 1 closed. G2 Oct 31 night, fast layer and E1 on development seeds. G3 Nov 1 night, leases, MCP, E2 and E3. G4 Nov 2 night, court E4, crisis loop and E10 on development seeds, viewer with overlays. Each gate is a progress check, not a point to cut scope. Details in `docs/PHASE1_BRIEF.md`.

## Rules

1. Every layer is measured by ablation: same seeds, layer on and off. The result goes in the README whether it is good or bad.
2. A feature without its ablation is listed as "implemented, not evaluated". It is not presented as a contribution.
3. Phase 8 is reserved from Nov 3 morning regardless of state. If a phase is open at that point, it ships with its real state documented.
4. A thin end-to-end slice (command, director, MCP, one robot moving, fast layer stopping it) must run by the end of Phase 3. Later phases deepen something that already runs.
5. Seeds are split before any tuning: development seeds and held-out test seeds. Test seeds are run once per configuration.
6. No code is copied from earlier repositories. Rewriting from design is allowed. See PRIOR_WORK.md.
7. Each task: one branch, tests first, CI green, human approves the PR. See AGENTS.md.

## Phase 0: Foundation

Tasks
- New empty repository, first commit on Oct 27.
- CI: ruff, mypy --strict, pytest, coverage report.
- Docker Compose: postgres with pgvector, api, worker, mcp server, frontend.
- PRIOR_WORK.md, ASSETS.md, AGENTS.md, docs/DECISIONS.md committed.
- Claim Meta Model API credits (deadline Nov 4, 9 PM ET). Request Baseten and Modal credits. Add a card to the Meta account.
- Set a hard spending cap per provider (Meta, Baseten, Modal, Vertex), balance minus a 10 percent reserve. Partner credits are used first (ADR-015).
- Verify model ids through the Meta models list, the Baseten model id `meta-models/muse-spark-open-1026`, and Muse Glimmer availability and price per hour on Modal and Baseten.
- Fill the judging rubric weights in SUBMISSION.md (the participant guide tables arrived empty).

Exit: CI green on smoke tests, `docker compose up` starts all services.

## Phase 1: Simulator and ground truth

Tasks
- Deterministic tick loop (fixed dt, seeded RNG, no wall-clock dependence).
- World: grid or polygon map, racks, aisles, narrow one-way aisles, blind corners, stations, depots, machines.
- Robot classes with non-holonomic kinematics: carrier, heavy forklift, parts runner, tech repair. Speed, deceleration and actuation delay per class. Forklift: bicycle model with a minimum turning radius. Others: differential drive with a maximum angular speed. The footprint sweeps along the curved path and the detector uses the swept footprint. Optional `load_raised` on the forklift lowers max speed and decel limit by documented factors.
- Humans: scripted paths, random walkers, adversarial paths (step out at a blind corner at the worst time).
- Exact collision and separation-violation detector (swept geometry), independent of the control code.
- 2D debug map over WebSocket.
- Simulated 2D lidar (ray casting with range, angular resolution, noise, dropout, occlusion) and the optional human beacon variant (ADR-018). The exact detector keeps using ground truth.
- Scenario catalog S01 to S18 (see docs/EXPERIMENTS.md), each with a seed and a declared target layer. Development and held-out seeds are fixed once in `data/seeds.json`.
- Conventions of ADR-021: dt = 0.025 s (40 Hz), lidar at 10 Hz, seeded streams, canonical state hash, contract `control-no-ground-truth`.

Exit
- Same seed produces the same trajectory (test).
- Detector validated on hand-built cases, including near-miss and tunneling at high speed.
- Replay of any run by seed.

## Phase 2: Fast control layer and baseline

Tasks
- Stopping distance per class: `S_stop = v*t_r + v^2/(2a)`.
- Separation to humans: `S_sep = v_h*(t_r + v/a) + S_stop + C`. Speed cap scales between full speed at `k*S_sep` and zero at `S_sep`.
- Swept curvilinear footprint envelope for `S_stop` and `S_sep` along the current arc, and the occlusion-aware speed cap from the lidar scan (ADR-024). The control layer reads only `waggle.sim.observations` and `waggle.sim.params`.
- Hazard geofences (static and dynamic) and e-stop.
- Heartbeat watchdog: a robot with no heartbeat stops.
- Telemetry threshold to geofence, directly in the fast layer.
- Override rule: the fast layer verifies every motion command and can only reduce motion.
- Closest point of approach predictor on lidar detections: constant velocity extrapolation, can only restrict, the envelope stays the floor (ADR-018).
- Baseline run with the layer disabled, same seeds. E1 configurations: ground truth, lidar only, lidar with beacons; envelope only against envelope with prediction.
- Loop latency measured and reported as code latency.

Exit
- E1 ablation reported.
- E1 run on development seeds, then held-out seeds: collisions and violations with and without the layer.
- Zero collisions with humans in held-out seeds is a target, not a promise. Report the real number and every failing seed.

Branches (one PR each, tests first)
- `docs/phase2-design` (B11): ADR-026 to ADR-028, control layout, E1 configurations.
- `feat/control-envelope` (B12): control types, envelope, arbiter.
- `feat/control-tracking` (B13): perception and tracking.
- `feat/control-occlusion` (B14): occlusion cap. Done, PR 29.
- `feat/control-cpa` (B15): CPA predictor. Done, PR 30.
- `feat/control-reflex` (B16): heartbeat, geofences, e-stop, telemetry threshold. Done, PR 31.
- `feat/e1-harness` (B17): E1 harness, eight configurations on development seeds, `uv run report`. Done, PR 32. The development run is a cloud job (PENDING 36). Stop and report. B18 waits for the maintainer.

## Phase 3: Leases, fencing tokens, tasks, chaos

Tasks
- PostgreSQL schema: zones with monotonic fencing token, tasks with state machine, task events.
- Deterministic route planner: A* on the aisle graph, one-lane aisles as zones with capacity one, reservation through leases with fencing tokens.
- Local lease view in control (zone, token, expiry_tick) pushed by coordination, clamping speed before an ungranted zone and failing closed when stale. Multi-zone corridors acquired in one transaction with rows locked in canonical order. Zone state FAULT_OCCUPIED: the sweeper never releases a zone while the last known odometry puts a chassis in it, and triggers replanning.
- Task queue on PostgreSQL (`FOR UPDATE SKIP LOCKED`), workers, expiry sweeper.
- Lease manager: acquire increments the token, tools carry (zone, token), the tool checks inside one transaction with row lock.
- Fault injection: kill worker mid-task, drop network, delay the database, expire leases early, duplicate delivery.
- Property tests with Hypothesis on lease invariants.
- Baseline without fencing (lease check outside the tool) to show the failure it prevents.
- Task dependencies (mission graph) and the handoff at a rendezvous zone with an idempotency key and a fencing token (ADR-019), with a handoff chaos test.
- Thin end-to-end slice: scripted command to one robot moving under the fast layer.

Exit
- Robots reach their targets in the S13 to S18 density scenarios without deadlock, and a deadlock counter is reported in E2.
- Hypothesis property test: the in-memory lease model used by the rollout and the PostgreSQL implementation accept and reject the same sequences of acquire, release, expire and stale-token operations.
- E2: 500 tasks with workers killed at random points: 0 double assignments, 0 two robots in a one-lane aisle, 0 stale-token writes accepted. The no-fencing baseline shows nonzero counts.
- Thin slice runs from a script.

## Phase 4: MCP boundary and untrusted input

Tasks
- MCP server over HTTP/SSE, separate process.
- Identity by chassis: token hash (SHA-256), constant-time compare, identity derived from the token only.
- Per-tool allowlist by chassis. `tools/list` filtered by identity if the transport allows it, otherwise documented as a known gap.
- Strict schemas, unknown fields rejected, physical bounds per chassis (max speed, max payload, allowed zones).
- Rate limit per client and tool, computed from the audit table. Serialized per chassis with a transaction-scoped advisory lock on a 64-bit key, taken before counting and held until the intent row is inserted. Test: 30 simultaneous calls from one chassis.
- Audit: an intent row before forwarding (fail closed) and a correlated result row after. Insert-only by code convention, database role restriction documented.
- Per-call timeouts so a rejected request cannot hang the client.
- Deterministic sanitizers (length, charset, delimiter escaping), then the guard classifier (Muse Glimmer on Modal, strict structured output: benign, injection or uncertain, plus a reason code) on every untrusted input: voice transcript, package label, SOP text, manual text, messages between robots. Fail closed on untrusted input. The guard is the first screen, not the boundary.
- Injection corpus: labels, SOP text, manual text, inter-robot messages, voice transcripts. Each case has a declared target layer.

Exit
- E3: matrix of injection attempts by ablation (guard off, MCP identity off, court off). Report rejections per layer and what gets through when each layer is off.
- Integration test: a restricted identity cannot call a tool outside its allowlist regardless of content.

## Phase 5: Director, item resolution, court

Tasks
- Director on Muse Spark with strict structured output: task type, item id, destination, priority. Nothing else.
- Deterministic item resolution against inventory. Unknown or ambiguous item asks the operator, never guesses.
- Deterministic robot assignment: nearest free robot with battery and payload fit.
- Court: Muse Spark, Muse Spark Open 1026, Muse Glimmer (related models, correlated errors expected). Unanimous approve executes. Any reject, split, timeout or parse failure goes to the operator inbox. The court never approves over a rejection.
- Operator inbox with the full reasoning per reviewer.
- Labeled review set (benign, risky, ambiguous) built before running, split dev and test.
- Token and cost logging per call.

Exit
- E4: correct blocks, false blocks, escalation rate, configurations A to D (D adds a non-Muse member on Vertex, run once on held-out), pairwise error correlation, cost per task.
- E8 partial: LLM latency distributions per model.

## Phase 5B: Per-robot advisors

Tasks
- Safety advisor per robot: fast small model, reads local context, can only request more caution (lower speed cap, bigger margin, pause). It cannot loosen anything the fast layer set.
- Organizer per robot: decides inside its assigned task (sub-step order, alternative part if stock is low, yielding, batching nearby deliveries). Speaks to other robots only through schema-validated messages. Every action goes through the MCP with that robot's identity.
- Message limits: max turns and max budget per task, loop detection.
- Inter-robot messages are untrusted input and pass the same screening.
- Degraded mode: if the LLM is slow or down, robots keep the fast layer and finish or hold the current task.
- Fleet planner (optional): event-driven and low frequency, proposes assignments, batching and reroutes. A deterministic validator checks feasibility, leases and bounds before anything is applied. If it fails or times out, the deterministic assigner is used (ADR-016).

Exit
- E5: ablation with and without each advisor and with the fleet planner as an extra configuration, same seeds. Report near-misses, false stops, throughput cost, tasks per hour against the code-only assigner, calls and cost per task. If an advisor shows no effect, report that.

## Phase 5C: Crisis replanning and validation

Tasks
- New package `waggle.validation`: belief state, rollout and counterexample types as frozen dataclasses. Imports `waggle.sim` and `waggle.control`, never `waggle.llm`, `waggle.governance` or `waggle.mcp_server`. An import-linter contract is added with the package.
- Plan schema and its hand-written validation (ARCHITECTURE.md, Plan schema).
- Crisis planner prompt (versioned file), counterexample feedback loop with at most 3 iterations, receding horizon at H/2.
- Compound-fault templates for E10, each with a text incident report.

Exit
- E10 on development seeds: the four configurations run, with violations in validation and in execution, deadlocks, recovery time, iterations, calls, cost, escalations, and the fraction of accepted plans that fail in an extended 120 s rollout or in execution. The sensitivity run for H in 30, 45 and 60 seconds is reported. What the LLM adds beyond the deterministic baseline is reported per template, including when it adds nothing.

## Phase 6: Predictive maintenance

Tasks
- Machine telemetry generator with hidden failure onset, and scenario families S19 to S36 (combined faults, dependency failures, sensor faults, coordinated handoff), built when the layers they exercise exist.
- Machine physics in the simulator: bearing temperature and vibration as a function of load and a hidden fault state. Different dynamics from the predictor, with sensor noise and hidden onset.
- Predictor: first-order thermal model fit online on telemetry, outputs estimated time to limit.
- Structured manual sheet per machine, extracted once from the manual and validated by schema: limits, failure modes, part numbers, procedures. Missing sheet means a conservative default limit.
- RAG over manuals (pgvector) used for procedure text, part number lookup and ticket drafting, not for the stop decision.
- Severity levels (warning, critical, emergency) with deterministic actions: warning logs and slows nearby robots, critical sets a geofence and opens a ticket, emergency stops and alarms.
- MCP tools: `reserve_part` (checks stock in the database), `dispatch_tech`, with an idempotency key per failure event so one failure opens one ticket.
- Parts-runner flow: fetch the part, deliver to a safe point near the machine, reroute the affected package.
- Part number is verified against the catalog by code before any order.
- Synthetic failure log generated separately from the simulator dynamics, history-based diagnosis (retrieval of similar cases) and offline predictor calibration (ADR-020).
- MCP tool `create_purchase_order` against a simulated procurement table when stock is zero, idempotent per failure event.

Exit
- E6: three failure modes on one machine, seeded onset. Report lead time before failure, false alarms, missed failures, wrong part orders, against a fixed-threshold baseline.

## Phase 7: 3D scene and multimodal

Tasks
- Three.js scene over WebSocket, rendering only. Meshy GLBs for robots, humans, machines, racks, packages. Safety rings, hazard zones, smoke and spark effects on overheating.
- Operator inbox and maintenance panel in the UI.
- Voice: push-to-talk, Muse Voice Transcribe, transcript treated as untrusted, read-back of the resolved item id before execution.
- Vision: synthetic FPV snapshot, Muse Spark with image to confirm package label and obstruction, result attached to the ticket.
- Audio out: severity-graded alarms and spoken alerts in the browser.
- Degraded paths: every multimodal feature has a text fallback.

Exit
- E7: transcription error rate on item ids (spoken ids set, with noise), label verification accuracy on synthetic labels including adversarial text on the label.

## Phase 7B: Technical viewer v0

Starts after branch B8 of `docs/PHASE1_BRIEF.md`. Sources in `web/`, WebSocket bridge in `src/waggle/api`. Primitives, top-down camera, envelope, lidar and ghost overlays, one-click chaos buttons that call the scenario format with seeds, deterministic replay with a state hash bar. The web server, WebSocket and JavaScript dependencies need maintainer approval first (PENDING 26).

Status (2026-10-30): a standalone mockup (`index (1).html`, Three.js 0.186.1, its own mock simulation in JavaScript) was built by the maintainer with another agent. It stays as it is and is not committed until the real logic is done (control, MCP, court, advisors). The refactor into `web/` fed by a state snapshot per tick from `waggle.sim` comes after that. The mock simulation must be removed then, because the renderer owns nothing (ADR-002).

## Phase 8: Delivery

Tasks
- README with measured tables, limits and reproduction commands.
- `/experiments` page generated from the result files.
- Extrapolation with a calibrated stub, stated as extrapolation.
- Deploy to a single VM with Docker Compose. Keep a recorded fallback of the demo.
- Demo video, 3 minutes, shows only what was built in the hackathon. Three moments: command and a human crossing with the stop; machine overheating with severity, part order and ticket; injection blocked at the MCP. The rest goes in the README.
- Public repository check, video link check, all contributors listed, assets documented.
- Submit with at least several hours of margin.

Exit: submission confirmed.

## Integration risks

| Risk | Mitigation |
|---|---|
| Integration of many components late | Thin slice by end of Phase 3 |
| LLM provider outage or rate limit during runs | Cached responses for replays, degraded mode, spend cap, fallback model |
| Ablation shows no effect for a layer | Report it. Harder scenarios, density sweep |
| Simulator and predictor share equations | Different dynamics, noise, hidden onset, held-out parameters |
| Scenarios tuned to pass | Dev and held-out seeds, test seeds run once |
| Demo VM fragility | Compose on one VM, recorded fallback, no managed cloud dependencies |
| Cost overrun | Per-provider spend cap, cost logged per call |

## Planned extension after the local build order

The [multi-warehouse logistics plan](docs/MULTI_WAREHOUSE_PLAN.md), ADR-035, defines a future network of independent Waggle cells and simulated truck transfers. It preserves every phase and delivery requirement above. Documentation is authorized; implementation is gated on completed local scope, evidence review and explicit maintainer authorization at G-GLOBAL. All global milestones and G01 to G09 remain pending. No new experiment has run.
