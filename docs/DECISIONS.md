# Architecture Decision Records

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

Context: same-family models can share blind spots, and different families can still agree on a mistake.
Decision: three families. Report pairwise correlation of errors for same-family and cross-family pairs.
Consequences: diversity is presented as a measured property with its limits.

## ADR-007: Third model family

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
