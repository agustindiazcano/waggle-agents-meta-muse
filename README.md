# Waggle Hive

Safety and reliability control plane for LLM-directed warehouse robot fleets. It includes predictive maintenance, demonstrated in a seeded warehouse simulation with 10 robots, scripted and adversarial human workers, and industrial machines that emit telemetry.

Meta Global AI Developer Hackathon. Track: Indie Developer. Problem statement: Push the Frontier.

Status: work in progress. Every number in this file is marked TBD until the experiment that produces it has run. Nothing in this repository claims a result that was not measured.

## What it does

An operator gives a command by text or voice, for example "bring Z89 to the North Depot". The system turns it into a verified task, assigns a robot, moves it through a warehouse shared with other robots and humans, and keeps it safe while doing so.

Core principle: LLMs propose, deterministic code disposes. Hard safety never depends on an LLM.

| Layer | Mechanism | Depends on an LLM |
|---|---|---|
| Fast control loop | Stopping-distance envelope, separation monitoring, hazard geofences, e-stop, every tick (designed, not implemented) | No |
| Coordination | Pure leases and atomic corridor reservations with monotonic fencing tokens (implemented, not evaluated). Simulator admission is integrated in an explicit S03 variant with exterior staging and parking, covered by unit tests. Database transactions and E2 evaluation are not implemented. See ADR-031 in [docs/DECISIONS.md](docs/DECISIONS.md) | No |
| Tool boundary | MCP server, chassis identity, per-tool allowlist, strict schemas, rate limit, audit (designed, not implemented) | No |
| Input screening | Sanitizers and an async classifier interface with a fail-closed label policy and an offline mock (implemented, not evaluated). Production detection and E3 are not implemented | Planned, first screen only |
| Task review | Unanimous court of three related Muse models, any reject, split or failure goes to the operator | Yes, advisory |
| Per-robot advisors | Safety advisor (can only add caution) and organizer (decides inside its task) (designed, not implemented) | Yes, bounded |
| Fleet planner | Optional, event driven. Proposals pass a deterministic validator, the code-only assigner is the fallback (designed, not implemented) | Yes, optional |
| Crisis replanning | Muse Spark proposes a plan, a simulation-based validator returns counterexamples, at most 3 iterations, then the operator (designed, not implemented) | Yes, proposal only |
| Sensing and prediction | Simulated 2D lidar, closest point of approach predictor that can only restrict (designed, not implemented) | No |
| Missions and handoff | Task graph, handoff with idempotency key and fencing token (designed, not implemented) | No |
| Predictive maintenance | Physical degradation model, structured manual sheet, RAG for procedure and part (designed, not implemented) | RAG text only |

## Models used

- Meta Model API: Muse Spark (director, fleet planner, diagnosis, court member 1), Muse Voice Transcribe, and Muse Spark with image input (label and obstruction verification).
- Muse Spark Open 1026 on Baseten (court member 2, per-robot advisors, organizer).
- Muse Glimmer 30B on Modal (court member 3 and the input guard).
- Vertex AI (Gemini): secondary backup only, and the non-Muse member of one E4 configuration.
- The court members are related models, so correlated errors are expected. See [docs/DECISIONS.md](docs/DECISIONS.md), ADR-015 to ADR-017.

## Results

All results come from seeded, reproducible scripts. See [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) for protocol, seeds, baselines and ablations.

| Experiment | Metric | Without layer | With layer | Status |
|---|---|---|---|---|
| E1 Fast layer | Human collisions and separation violations per N scenarios | No control, 90 runs on development seeds: 107 human collisions, 1027 robot collisions, 125 separation violations (`no_control_20261030T173638Z.json`) | TBD | baseline on development seeds only, fast layer not built |
| E2 Leases and chaos | Double assignments in 500 tasks with killed workers | TBD | TBD | not run |
| E3 Injection matrix | Attempts rejected per layer, by ablation | TBD | TBD | not run |
| E4 Court | Correct blocks, false blocks, reviewer correlation | TBD | TBD | not run |
| E5 Per-robot advisors | Near-misses, false stops, tasks per hour | TBD | TBD | not run |
| E6 Predictive maintenance | Lead time, false alarms, missed failures vs fixed threshold | TBD | TBD | not run |
| E7 Multimodal | ID error rate in transcription, label verification accuracy | TBD | TBD | not run |
| E8 Latency and cost | Fast loop latency, cost per task, LLM latency distribution | 10 robots, 4 humans, 45 s simulated, lidar included: 12.2 s per rollout with the exact lidar and 5.8 s (median) with the rollout lidar, code speed on this machine (`sim_speed_20261030T121253Z.json`). Same-session before and after, four alternating runs: median 18.0 s to 5.7 s, 3.1x (`before_after_20261030.json`). Targets of 2.0 s and 5x are missed | TBD | simulator only |

Scaling to thousands of agents is reported as an extrapolation from a stub calibrated on measured latency distributions. It is not a claim about real fleets.

## Third-party libraries

- numpy 2.5.4 (pinned): the only runtime dependency, used by `waggle.sim`, `waggle.control` and `waggle.validation` for state arrays and seeded random streams. Approved by the maintainer.

## Scope and limits

- Simulation only. Latencies of the fast layer are code latencies inside the simulator, not real-time guarantees on hardware.
- The separation formula is inspired by speed and separation monitoring. This project does not claim compliance with any standard.
- The simulation is 2D on the floor plane. Height is not modeled. Rendering is 3D and the FPV vision check renders the 3D scene.
- Exact reproduction of a run holds on the same platform and numpy version. Published results come from the cloud run (Linux).
- Plan validation in crisis replanning is simulation-based with counterexample feedback. It is not formal verification and not a safety proof. The reflex layer stays the safety mechanism against humans.
- The lidar is simulated (designed, not implemented). Failure history and purchase orders are synthetic (designed, not implemented).
- Vision inputs are synthetic renders, not in the control loop, so ground truth is known by construction.
- Human behavior is scripted or adversarial by design, not learned from real data.

## Repository layout

```
README.md                this file
PLAN.md                  phases, tasks, exit criteria
AGENTS.md                development workflow and rules for coding agents
PRIOR_WORK.md            declaration of prior work
ASSETS.md                provenance and rights of every asset
SUBMISSION.md            hackathon submission checklist
docs/
  ARCHITECTURE.md        components, data model, interfaces
  THREAT_MODEL.md        assets, adversaries, controls, residual risk
  EXPERIMENTS.md         protocol for every measurement
  DECISIONS.md           architecture decision records
src/waggle/              Python package: sim, control, coordination, mcp_server,
                         governance, maintenance, multimodal, llm, api, db
web/                     frontend
experiments/             seeded experiment scripts
results/                 result files produced by experiments
data/                    synthetic manuals and SOPs
assets/                  3D assets and media
tests/                   unit, property, integration, chaos
tools/hooks/             Claude Code hook scripts (safety guard, lint check, session start)
.github/workflows/       CI
```

## Repository safeguards

Claude Code hooks in `.claude/settings.json` run scripts from `tools/hooks/`: a PreToolUse safety guard (denies push, merge, force options, `git add -A`, staged `.env` and held-out result writes; asks first for branch deletion, rebase, amend and protected paths), a PostToolUse lint check and a SessionStart context loader. `tools/hooks/protected_paths.txt` is the single list of protected paths, and `CODEOWNERS` covers every entry.

This is a weak control in a single-maintainer repository. The hooks help an agent stay inside the rules, but the maintainer can change them, and CODEOWNERS has an effect only when branch protection requires code owner review. Branch protection is a repository setting that the maintainer sets by hand. The command guard also reads interpreter one-liners (python -c, node -e, powershell -Command) for the text git push, git remote and gh api, which is a best-effort text match: a command built at run time, a script file or an encoded string passes it. Branch protection on main is the real control.

## Run

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

```
cp .env.example .env        # fill in values locally, never commit .env
uv sync
uv run ci                   # ruff, mypy --strict, pytest with coverage, import-linter
docker compose up --build   # db, api, worker, mcp_server, web (Phase 0 placeholders)
```

Other tasks: `uv run lint`, `uv run type`, `uv run test`, `uv run experiments-dev`, `uv run experiments-test`, `uv run report`. `uv run experiments-dev` runs E1 on the development seeds (a full run is a cloud job, see `.github/workflows/e1.yml`) and `uv run report` writes `results/e1/dev/report.md` from the result files. `experiments-test` is still a placeholder.

Tooling: uv, ruff, mypy, pytest, pytest-cov, hypothesis, import-linter, pre-commit. Postgres image: pgvector/pgvector.

## Environment variables

Names only live in `.env.example`. Values go in `.env`, which git ignores.

| Variable | Description | Default |
|---|---|---|
| `META_API_KEY`, `META_API_BASE_URL` | Meta Model API access | none |
| `META_MODEL_ID`, `META_VOICE_MODEL_ID` | Model ids, read from the API model list (`GET /v1/models`) | none |
| `META_USE_CONTRIBUTOR_TIER` | Use the cheaper contributor tier. Allowed only because all data is synthetic | false |
| `BASETEN_API_KEY`, `BASETEN_MODEL_ID` | Baseten access and the Muse Spark Open 1026 id | none |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `MODAL_ENDPOINT_URL` | Modal access and endpoint | none |
| `MODAL_GLIMMER_MODEL_ID`, `MODAL_SPARK_OPEN_MODEL_ID` | Model ids served on Modal (guard and court member 3; fallback host for Muse Spark Open) | none |
| `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `VERTEX_MODEL_ID`, `GOOGLE_APPLICATION_CREDENTIALS` | Vertex AI backup, service account file | none |
| `META_SPEND_CAP_USD`, `BASETEN_SPEND_CAP_USD`, `MODAL_SPEND_CAP_USD`, `VERTEX_SPEND_CAP_USD` | Hard cap per provider in USD. A missing or invalid value blocks calls | none |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | Database | none |
| `MESHY_API_KEY`, `LANGFUSE_*` | 3D assets and optional tracing | none |
| `WAGGLE_IMAGE_TAG` | Tag of the service images in compose | dev |

## Model license notice

Built with Muse Spark Open. Muse Spark Open is used under its license, which asks for an attribution notice in products and services. The exact text is to be confirmed against the license (see PENDING.md).

## Disclosure

| Area | Detail |
|---|---|
| AI tools used to build this repository | Claude Code, used for code, tests and documentation under maintainer review. |
| Models used by the product | Muse Spark, Muse Spark Open 1026, Muse Voice Transcribe and Muse Spark with image input (Meta); Muse Glimmer 30B on Modal; Vertex AI only as a declared backup. See [docs/DECISIONS.md](docs/DECISIONS.md). |
| Libraries | Listed in `pyproject.toml` and pinned in `uv.lock`. Notable ones are named in this README. |
| Prior code | None. See PRIOR_WORK.md. |
| Assets | See ASSETS.md for the source and rights of every asset. |

## License

MIT.
