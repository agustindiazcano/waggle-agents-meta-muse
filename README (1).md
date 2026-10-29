# AegisFleet

Safety, reliability and predictive maintenance control plane for LLM-directed robot fleets, demonstrated in a seeded warehouse simulation with 10 robots, scripted and adversarial human workers, and industrial machines that emit telemetry.

Meta Global AI Developer Hackathon. Track: Indie Developer. Problem statement: Push the Frontier.

Status: work in progress. Every number in this file is marked TBD until the experiment that produces it has run. Nothing in this repository claims a result that was not measured.

## What it does

An operator gives a command by text or voice, for example "bring Z89 to the North Depot". The system turns it into a verified task, assigns a robot, moves it through a warehouse shared with other robots and humans, and keeps it safe while doing so.

Core principle: LLMs propose, deterministic code disposes. Hard safety never depends on an LLM.

| Layer | Mechanism | Depends on an LLM |
|---|---|---|
| Fast control loop | Stopping-distance envelope, separation monitoring, hazard geofences, e-stop, every tick | No |
| Coordination | Zone leases with monotonic fencing tokens, checked inside the tool in one transaction | No |
| Tool boundary | MCP server, chassis identity, per-tool allowlist, strict schemas, rate limit, audit | No |
| Input screening | Prompt Guard plus deterministic sanitizers on all untrusted input | Classifier only |
| Task review | Unanimous court of three model families, any reject or split goes to the operator | Yes, advisory |
| Per-robot advisors | Safety advisor (can only add caution) and organizer (decides inside its task) | Yes, bounded |
| Predictive maintenance | Physical degradation model, structured manual sheet, RAG for procedure and part | RAG text only |

## Models used

- Meta Model API: Muse Spark (director, diagnosis, court member, per-robot advisors).
- Muse Spark Open 1026 on Baseten (court member, fast advisors).
- Muse Voice Transcribe (voice command input).
- Muse Spark with image input (label and obstruction verification).
- A third model family (court diversity). Which one and why: see DECISIONS.md.

## Results

All results come from seeded, reproducible scripts. See EXPERIMENTS.md for protocol, seeds, baselines and ablations.

| Experiment | Metric | Without layer | With layer | Status |
|---|---|---|---|---|
| E1 Fast layer | Human collisions and separation violations per N scenarios | TBD | TBD | not run |
| E2 Leases and chaos | Double assignments in 500 tasks with killed workers | TBD | TBD | not run |
| E3 Injection matrix | Attempts rejected per layer, by ablation | TBD | TBD | not run |
| E4 Court | Correct blocks, false blocks, reviewer correlation | TBD | TBD | not run |
| E5 Per-robot advisors | Near-misses, false stops, tasks per hour | TBD | TBD | not run |
| E6 Predictive maintenance | Lead time, false alarms, missed failures vs fixed threshold | TBD | TBD | not run |
| E7 Multimodal | ID error rate in transcription, label verification accuracy | TBD | TBD | not run |
| E8 Latency and cost | Fast loop latency, cost per task, LLM latency distribution | TBD | TBD | not run |

Scaling to thousands of agents is reported as an extrapolation from a stub calibrated on measured latency distributions. It is not a claim about real fleets.

## Scope and limits

- Simulation only. Latencies of the fast layer are code latencies inside the simulator, not real-time guarantees on hardware.
- The separation formula is inspired by speed and separation monitoring. This project does not claim compliance with any standard.
- Vision inputs are synthetic renders, so ground truth is known by construction.
- Human behavior is scripted or adversarial by design, not learned from real data.

## Repository layout

```
README.md            this file
PLAN.md              phases, tasks, exit criteria
ARCHITECTURE.md      components, data model, interfaces
THREAT_MODEL.md      assets, adversaries, controls, residual risk
EXPERIMENTS.md       protocol for every measurement
DECISIONS.md         architecture decision records
AGENTS.md            development workflow and rules for coding agents
PRIOR_WORK.md        declaration of prior work
ASSETS.md            provenance and rights of every asset
SUBMISSION.md        hackathon submission checklist
```

## Run

TBD after Phase 0. Target: `docker compose up --build`, then open the operator UI.

## License

MIT.
