# Waggle Hive: Architecture

## Principles

1. LLMs propose, deterministic code disposes.
2. Authority comes from authenticated identity, never from prompt or retrieved text.
3. The fast layer can only reduce motion. Nothing above it can widen what it allows.
4. Fail closed on safety and untrusted input. Degrade to a safe hold when an LLM is unavailable.
5. The simulator owns ground truth. The renderer owns nothing.
6. Every claim is backed by a seeded, reproducible script.

## Components

```mermaid
flowchart TB
    subgraph UI["Frontend: React + Three.js, render only"]
        MAP[3D scene via WebSocket]
        CMD[Voice and text command bar]
        INBOX[Operator inbox and maintenance panel]
    end

    subgraph SIM["Simulator: seeded tick loop, ground truth"]
        WORLD[Robots, humans, machines, telemetry]
        DETECT[Exact collision and separation detector]
        LIDAR[Simulated 2D lidar and optional beacons]
    end

    subgraph FAST["Fast control loop: every tick, no LLM"]
        THRESH[Telemetry thresholds to hazard geofence]
        ENV[Stopping-distance and separation envelope, e-stop, watchdog]
        PRED[Closest point of approach predictor, can only restrict]
    end

    subgraph SLOW["Async governance pipeline"]
        GUARD[Guard classifier and sanitizers on untrusted input]
        DIR[Director: Muse Spark]
        DIAG[Diagnosis: manual sheet plus RAG for procedure and part]
        COURT[Unanimous court: Muse Spark, Muse Spark Open, Muse Glimmer]
        ADV[Per-robot advisors: safety, organizer]
        PLANNER[Fleet planner: optional, event driven]
        VALID[Deterministic validator: feasibility, leases, bounds]
        HANDOFF[Mission graph and handoff at a rendezvous zone]
    end

    subgraph MCP["Isolated MCP server"]
        AUTH[Chassis identity, allowlist, schemas, rate limit, audit]
        TOOLS[move, pick, deliver, reserve_part, dispatch_tech, create_purchase_order]
    end

    subgraph DB["PostgreSQL + pgvector"]
        LEASE[Zones, leases, fencing tokens]
        TASKS[Tasks, events, inbox]
        AUD[Audit, LLM call log]
        KB[Manuals, SOPs]
        HIST[Failure history, purchase orders]
    end

    CMD -->|transcript or text| GUARD
    WORLD -->|labels, SOP text, robot messages| GUARD
    GUARD --> DIR --> COURT
    COURT -->|unanimous approve| AUTH --> TOOLS --> LEASE
    COURT -->|any reject, split, timeout| INBOX
    ADV --> AUTH
    WORLD -.->|context change| PLANNER
    PLANNER -->|proposal| VALID --> AUTH
    WORLD -->|telemetry| THRESH --> ENV
    WORLD --> LIDAR -->|detections only| PRED --> ENV
    HANDOFF -->|idempotency key and fencing token| AUTH
    HIST --> DIAG
    THRESH -.->|event, parallel| DIAG --> DIR
    LEASE --> ENV
    ENV -->|verifies every motion command| WORLD
    WORLD --> DETECT
    WORLD --> MAP
    KB --> DIAG
```

## Sensing and prediction

Designed, not implemented (ADR-018).

- The simulator owns ground truth. Robots perceive through a simulated 2D lidar: rays against walls, racks and moving entities, with range, angular resolution, noise, dropout and occlusion, all seeded. Optional human beacons are visible around corners.
- The fast layer reads detections only. The exact detector in the simulator keeps using ground truth for scoring.
- Predictor: constant velocity extrapolation of each detected object and the closest point of approach (time and distance), compared with the robot's stopping distance. A predicted conflict lowers the speed cap earlier. It never raises it. The worst-case separation envelope is the floor.
- Failure mode: a missing or stale scan assumes the worst case and the watchdog stops the robot. No learned model. Camera and vision are not in the control loop.

## Missions and handoff

Designed, not implemented (ADR-019).

- A mission is a small task graph with dependency edges. A dependent task is eligible only when its predecessors are done.
- A handoff happens at a rendezvous zone with capacity one, held by a lease with a fencing token. The handoff event carries an idempotency key, so the dependent task becomes eligible exactly once.
- If the carrier dies, the lease expires, the task is reassigned and the fencing check rejects the stale carrier.
- Inter-robot messages use a fixed schema, are screened as untrusted and are bounded.

## Control path versus governance path

Governance path (slow, seconds): command, screening, director, court, MCP, lease, motion command.
Control path (fast, every tick): every motion command, from any source, passes through the envelope and can be reduced or vetoed. Telemetry thresholds act on this path directly, without any LLM or retrieval.

## Fast layer

Parameters per robot class (simulator assumptions, to be calibrated and documented):

| Class | Max speed (m/s) | Decel (m/s^2) | Actuation delay (s) |
|---|---|---|---|
| carrier | 2.0 | 2.0 | 0.10 |
| forklift | 1.5 | 0.8 | 0.15 |
| parts runner | 1.8 | 1.5 | 0.10 |
| tech repair | 1.2 | 1.5 | 0.10 |

Kinematics are non-holonomic (assumptions to calibrate, no claim of any standard):

| Class | Model | Parameter |
|---|---|---|
| forklift | bicycle model | minimum turning radius 2.5 m, wheelbase 1.6 m |
| carrier | differential drive | maximum angular speed 1.5 rad/s |
| parts runner | differential drive | maximum angular speed 1.8 rad/s |
| tech repair | differential drive | maximum angular speed 1.2 rad/s |

The footprint is an oriented rectangle that sweeps along the curved path. The detector uses the swept footprint. A robot cannot exceed its minimum turning radius or maximum angular speed, so a forklift at full speed cannot clear a blind corner that a carrier can.

Optional forklift parameter `load_raised`: multiplies max speed by 0.6 and the decel limit by 0.7. Both factors are assumptions to calibrate.

## Route planner

Deterministic, no LLM (designed, not implemented). A* on the aisle graph with a fixed tie-break. One-lane aisles are zones with capacity one, reserved through leases with fencing tokens. A robot that cannot get a lease waits or replans. A deadlock counter is reported in E2.

Formulas:
- Stopping distance: `S_stop = v*t_r + v^2/(2a)`.
- Separation to a human: `S_sep = v_h*(t_r + v/a) + S_stop + C`, with `v_h` the assumed human approach speed and `C` a margin.
- Speed cap: full speed at `d >= k*S_sep`, linear to zero at `d <= S_sep`, e-stop below `S_sep`.
- Heartbeat: no heartbeat within the timeout means stop.
- Hazard geofence: polygon that motion commands may not enter, set statically or dynamically (machine fault, spill, human zone).

Inspired by speed and separation monitoring. No compliance with any standard is claimed.

## Model tiers and roles

Every model role uses a Meta Muse model. Providers and fallbacks are declared in `src/waggle/llm/routes.toml`; model ids come from environment variables. See ADR-015, ADR-016 and ADR-017 in [DECISIONS.md](DECISIONS.md).

| Tier | Roles | Model and provider | Trigger |
|---|---|---|---|
| Reflex | Fast control loop, fencing | Deterministic code, no LLM | Every tick |
| Fast LLM | Per-robot safety advisor, per-robot organizer | Muse Spark Open 1026 on Baseten | Context change, never per tick |
| Fast LLM | Guard classifier | Muse Glimmer on Modal | Each untrusted input, after sanitizers |
| Planning LLM | Director, fleet planner, diagnosis, court member 1, voice, vision | Muse Spark on the Meta API | A command, an event, or every N seconds |
| Planning LLM | Court member 2 | Muse Spark Open 1026 on Baseten | Each reviewed task |
| Planning LLM | Court member 3 | Muse Glimmer on Modal | Each reviewed task |

Fallbacks, only through the routing table and disabled in held-out runs: Modal hosting Muse Spark Open when Baseten fails, and Vertex AI as secondary backup for the guard and court member 3.

Fleet planner (optional): event-driven and low frequency. It proposes assignments, batching and reroutes. A deterministic validator checks feasibility, leases and bounds before anything is applied. If the planner fails or times out, the deterministic assigner is used. In E5 it is an extra configuration; the code-only baseline stays.

Guard classifier: deterministic sanitizers run first (length, charset, delimiter escaping). The classifier returns a label (benign, injection or uncertain) and a reason code as strict structured output, with the input fenced as untrusted data. A parse failure, a timeout or uncertain rejects and escalates. It is the first screen, not the boundary. Identity and schemas are the boundary.

Budget: a guard in `waggle.llm` checks accumulated cost plus the call estimate against the provider cap before every call, and per-task call and cost caps apply.
## Leases and fencing tokens

- `zones(zone_id, holder, fencing_token, expires_at)`.
- Acquire: in one transaction, lock the row, check free or expired, increment the token, set holder and expiry.
- Every tool that acts on a zone receives `(zone_id, token)` and verifies in the same transaction with the row locked. A stale token is rejected.
- Expiry is handled by a sweeper using `FOR UPDATE SKIP LOCKED`. The token never decreases.
- One-lane aisles and stations are zones with capacity one. Deadlocks are resolved by acquisition order and timeout.

## Task state machine

`PENDING -> SCREENED -> REVIEWED -> APPROVED -> ASSIGNED -> EXECUTING -> DONE`
Side exits: `ESCALATED` (operator inbox), `REJECTED`, `FAILED`, `ABORTED`.
Each transition is an event row. Retries carry an attempt number and an idempotency key.

## MCP boundary

- Identity: each robot chassis has a token. Server stores SHA-256 hashes, compares in constant time, derives `chassis` and `robot_id` from the token.
- Allowlist: chassis to tools. Carrier cannot call forklift tools or maintenance tools.
- Schemas: strict, unknown fields rejected, physical bounds per chassis.
- Rate limit: counted from the audit table so it holds across replicas.
- Audit: intent row before forwarding (write fails means call denied). Result row after execution, linked by correlation id.
- Per-call timeout on the client so a denied request cannot hang it.

Tools: `move_waypoint`, `pick_package`, `deliver_package`, `release_zone`, `reserve_part`, `dispatch_tech`, `open_ticket`, `get_task`, `get_inventory`, `create_purchase_order` (designed, not implemented).

## Court

- Inputs: structured task, item resolution result, current world summary, relevant SOP excerpts (screened).
- Members: Muse Spark, Muse Spark Open 1026, Muse Glimmer (related models, correlated errors expected, see ADR-017). Same prompt, structured verdict with reason code.
- Decision: execute only if all three approve with no parse or timeout failure. Anything else goes to the operator inbox. No path approves over a rejection.
- Logged per call: model, tokens, latency, cost, verdict.

## Per-robot advisors

- Safety advisor: small and fast model. Input: local context. Output: restriction request only (lower speed cap, larger margin, pause). Applied by the fast layer as a further limit, never as a relaxation.
- Organizer: decides inside the assigned task. Output: structured action requests through MCP with that robot's identity. Messages between robots use a fixed schema, are screened as untrusted, and are bounded by turns and budget.

## Predictive maintenance

- Telemetry: temperature, vibration, hydraulic pressure, current per machine.
- Threshold path (fast, deterministic): limit crossing sets a hazard geofence and severity.
- Prediction path: first-order thermal model fit online, estimated time to limit.
- Manual sheet: structured JSON extracted once per machine and validated (limits, failure modes, part numbers, procedures). Missing sheet means conservative default.
- RAG: retrieves procedure text and part information, drafts the ticket. Part numbers are checked against the catalog in code before any order.
- Idempotency: one failure event key opens at most one ticket and one part reservation.

## Multimodal

- Voice: push-to-talk, Muse Voice Transcribe, transcript is untrusted, screened, resolved to an item id by code, id read back to the operator before execution.
- Vision: synthetic FPV render of the scene, Muse Spark with image verifies label and obstruction, result attached to the ticket.
- Alarms: browser audio by severity. Every feature has a text fallback.

## Data model (summary)

`robots`, `robot_identities`, `zones`, `tasks`, `task_events`, `machines`, `machine_telemetry` (sampled), `spare_parts`, `maintenance_tickets` (unique idempotency key), `failure_history` (synthetic, separate from the simulator dynamics), `purchase_orders` (unique idempotency key per failure event), `mcp_audit` (intent and result rows), `llm_calls`, `knowledge_chunks` (pgvector), `operator_inbox`.

## Observability

Structured logs, `llm_calls` table with tokens, latency, cost per call, per-task cost rollup. Optional tracing with Langfuse. Replay by seed.

## Deployment

Docker Compose on one VM for the live demo. Local `docker compose up` for development and for every experiment script.
