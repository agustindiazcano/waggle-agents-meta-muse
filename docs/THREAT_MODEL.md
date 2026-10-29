# Threat Model

## Assets

1. Human safety (no collisions, no entry into hazard zones).
2. Task integrity (no double assignment, no stale writes).
3. Tool authority (a robot acts only within its chassis role).
4. Inventory and maintenance actions (no fake part orders, no ticket floods).
5. Operator trust (inbox shows true reasons, audit is complete).

## Untrusted inputs

| Input | Source | Entry point |
|---|---|---|
| Work order text | Operator or upstream system | Director |
| Voice transcript | Speech model output | Director |
| Package label text | Package, camera, simulator | Item resolution, vision check |
| SOP text | Knowledge base | Court, diagnosis |
| Manual text | Knowledge base | Diagnosis, RAG |
| Messages between robots | Other agents | Organizer, advisor |
| LLM outputs | Any model | Every consumer |

All of these are treated as data. None can change identity, allowlists, schemas or the fast layer.

## Adversaries and attempts

| ID | Attempt | Target layer |
|---|---|---|
| T1 | Instruction in a package label asking for tools outside role | MCP identity |
| T2 | Poisoned SOP widening a zone or speed limit | Fast layer, MCP schema bounds |
| T3 | Poisoned manual naming a wrong part | Catalog check in code |
| T4 | Voice command that resolves to a wrong item | Read-back, item resolution |
| T5 | Inter-robot message that tries to command another robot | Message schema, MCP identity |
| T6 | Court prompt injection to force approval | Unanimity, three families |
| T7 | Stale worker resumes after lease expiry | Fencing token |
| T8 | Duplicate delivery of the same task | Idempotency key |
| T9 | Ticket flood from repeated telemetry spikes | Idempotency key per failure event |
| T10 | LLM outage or slowdown | Degraded mode, safe hold |
| T11 | Malformed or oversized LLM output | Schema validation, fail closed |
| T12 | Adversarial human path at a blind corner | Fast layer |
| T13 | Sensor dropout on a machine | Conservative default, watchdog |

Each scenario in the corpus declares its target layer in advance. Layers are evaluated by ablation (see [EXPERIMENTS.md](EXPERIMENTS.md) E3).

## Control mapping

| Control | Covers |
|---|---|
| Fast envelope and e-stop | T12, T13 |
| Telemetry geofence | T13, machine faults |
| Fencing tokens in the tool | T7, T8 |
| MCP identity and allowlist | T1, T2, T5 |
| Strict schemas with physical bounds | T2, T11 |
| Prompt Guard and sanitizers | T1 to T6 (first screen) |
| Unanimous court | T6, ambiguous tasks |
| Read-back and item resolution | T4 |
| Catalog check in code | T3 |
| Idempotency keys | T8, T9 |
| Audit with result rows | Incident reconstruction |
| Degraded mode | T10 |

## Residual risk (stated, not hidden)

- Prompt Guard is a classifier and can miss attacks. It is the first screen, not the boundary. The boundary is identity and schema.
- An injected instruction can still influence which allowed tool a robot picks and with which in-bounds arguments. Bounds, the court, and the fast layer limit the damage.
- Court members from different families can still fail together. Correlation is measured and reported, not assumed away.
- The audit table is insert-only by code convention. A database superuser can alter it.
- No TLS between local containers in development.
- Simulated humans are scripted and adversarial, not a model of real behavior.
- Latency figures of the fast layer are simulator code latencies, not hardware guarantees.
- Security of the demo VM and API keys depends on deployment practice outside the simulator.

## Failure policy

- Safety layer fails: stop.
- Untrusted input screening fails or is uncertain: reject and escalate.
- Court member times out or returns malformed output: escalate.
- LLM unavailable: robots keep the fast layer, finish or hold the current motion, no new tasks start.
- Audit write fails: deny the call.
