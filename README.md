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
| Coordination | Pure leases, deterministic A* aisle routing, and atomic per-zone-direction corridor reservations with monotonic fencing tokens (implemented, not evaluated). Map binding validates an explicit graph against rectangular static geometry and declared chassis clearance, then returns waypoints; it does not certify curved tracking. Simulator admission is integrated in an explicit S03 variant with exterior staging and parking, covered by unit tests; mapped A* supplies the same fixture waypoints and complete reservation requests, including per-resource direction restoration. The manual E2 simulator comparison harness is implemented, not evaluated; no E2 sweep has run. A durable corridor reference and transactionally fenced event effect are implemented and verified by cloud correctness tests. Task queue, bounded recovery and worker iteration are implemented and verified by cloud correctness tests. A transactional handoff record is implemented, not evaluated; its cloud correctness tests, trusted occupancy and physical effect integration remain pending. Daemon/tool wiring and the full chaos evaluation remain pending. See ADR-031 in [docs/DECISIONS.md](docs/DECISIONS.md) | No |
| Tool boundary | MCP server, chassis identity, per-tool allowlist, strict schemas, rate limit, audit (designed, not implemented) | No |
| Input screening | Sanitizers and an async classifier interface with a fail-closed label policy and an offline mock (implemented, not evaluated). [E3 development declarations](data/e3/README.md) await maintainer labels; production detection and E3 evaluation are not implemented | Planned, first screen only |
| Task review | Unanimous court of three related Muse models, any reject, split or failure goes to the operator | Yes, advisory |
| Per-robot advisors | Safety advisor (can only add caution) and organizer (decides inside its task) (designed, not implemented) | Yes, bounded |
| Fleet planner | Optional, event driven. Proposals pass a deterministic validator, the code-only assigner is the fallback (designed, not implemented) | Yes, optional |
| Crisis replanning | Muse Spark proposes a plan, a simulation-based validator returns counterexamples, at most 3 iterations, then the operator (designed, not implemented) | Yes, proposal only |
| Sensing and prediction | Simulated 2D lidar, closest point of approach predictor that can only restrict (designed, not implemented) | No |
| Missions and handoff | Task dependencies and transactional handoff record (implemented, not evaluated); trusted physical integration pending | No |
| Predictive maintenance | Physical degradation model, structured manual sheet, RAG for procedure and part (designed, not implemented) | RAG text only |

## Planned multi-warehouse extension

The [multi-warehouse logistics plan](docs/MULTI_WAREHOUSE_PLAN.md) treats each Waggle warehouse as an independent cell. A higher-level coordinator proposes inter-site transfers through cell APIs; local safety, task ownership, inventory custody and MCP authorization remain local. Trucks are proposed as a seeded graph-transit simulation, not autonomous road vehicles. This extension is planned, not implemented or evaluated. Its readiness gate preserves the complete local build order and requires maintainer authorization before implementation.

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

PostgreSQL coordination uses `psycopg[binary]==3.3.6`, approved by the maintainer on 2026-10-31. The binary extra supplies the matching libpq adapter on Windows and Linux; there is no ORM. See the [Psycopg documentation](https://www.psycopg.org/psycopg3/docs/basic/install.html).

### Persistent coordination

`waggle.db.corridors` implements the pure corridor transitions under PostgreSQL locks. Migration revision 1 creates `zones`, `fenced_events` and `waggle_schema`; revision 2 adds `tasks`, `task_dependencies` and `task_events`; revision 3 adds handoff requirements, without sample rows. Provision resource ids separately through `CorridorRepository.register`; registering an existing resource never resets its token. Implementation is not an E2 result. Handoff records require trusted occupancy, identity and tick inputs; physical effects and production MCP tool wiring remain pending.

With `DATABASE_URL` configured for the intended database, inspect its revision before applying the approved migration:

```
uv run python -m waggle.db.schema
uv run python -m waggle.db.schema --expected-revision 0
```

The first command only inspects. The second requires revision 0 under a transaction lock and atomically installs the current revision 2. An existing revision 1 database upgrades with `--expected-revision 1`, preserving corridor state. Reapplying with `--expected-revision 2` is a no-op. `--target-revision 1` can select the initial revision when creating a new database; downgrades are rejected. Unexpected revisions or conflicting tables roll back the complete migration. Migration never runs automatically during service startup.

Every operation opens a separate connection. Defaults are a 5 s connect timeout, a 5000 ms statement timeout, a 3000 ms lock timeout and the `public` schema; these are explicit `Database` constructor arguments. `DATABASE_URL` is required and has no default. Configuration values and credentials are not logged.

All zone rows are locked in sorted id order for a complete pure-model transition, with per-holder transaction locks and a shared topology lock. This intentionally coarse implementation has no fleet throughput claim. Occupancy and ticks must come from a trusted coordination adapter, not model output. The fencing proof effect inserts an idempotent `fenced_events` row under those same locks; it does not move a robot or establish MCP audit. A matching repeat returns the historical result without inserting again, even after expiry. Reusing an event id with different content raises an error.

Real PostgreSQL correctness tests are marked `heavy` and run only in cloud workflows, including the manual [PostgreSQL workflow](.github/workflows/postgres.yml). They use temporary schemas and no provider keys. The existing heavy workflow can also select them with `marker=heavy`, `seed_set=dev`. They check model parity, concurrency, rollback, restart and a lock-contended stale-token race. [Cloud run 41217047545](https://github.com/agustindiazcano/waggle-agents-meta-muse/actions/runs/41217047545) on commit `7fa02c0` passed the original 10 PostgreSQL corridor tests. Queue/worker [cloud run 41225808111](https://github.com/agustindiazcano/waggle-agents-meta-muse/actions/runs/41225808111) on commit `085f8ff` passed all 26 PostgreSQL tests (10 corridor and 16 queue/worker tests), with no failures, errors or skips in the JUnit artifact. The full 500-task chaos protocol, physical handoff and production service wiring remain pending.

### Task queue and workers

`waggle.coordination.task_model` provides pure task transitions. `TaskRepository` persists task metadata and one immutable event snapshot per transition. Callers supply trusted worker identities and current simulation ticks. Review must progress through `PENDING`, `SCREENED`, `REVIEWED` and `APPROVED` before a claim. These APIs do not authenticate an operator or replace the guard and court.

Claims select eligible approved tasks with `FOR UPDATE SKIP LOCKED`, highest priority first and task id as the tie-break. Dependencies must already exist and finish `DONE`; immutable definitions and existing-parent insertion prevent cycles through this API. A unique index and per-worker transaction lock allow one active attempt per worker. Assignment increments both attempt and fencing token. Start, completion and failure check the exact live task/worker/token with the task row locked. State and event writes commit together. Matching successful request ids replay historical results; conflicting content raises an error. Empty or denied claims create no transition and may be retried.

`recover` skips locked rows and requeues expired attempts until their cap, then marks them `FAILED`. It retains counters and never changes zone reservations or occupied faults. `DONE`, `FAILED`, `REJECTED`, `ESCALATED` and `ABORTED` are terminal in this queue; resubmission requires a new reviewed task. Explicit handler failure is terminal, while an abandoned expired attempt is eligible for bounded recovery.

`waggle.worker.run_once` commits claim and start before calling its handler. A handler must return exactly `HandlerOutcome.DONE` for completion; malformed results, explicit failure and exceptions fail closed. Exception text is not logged. Replayed claims never invoke the handler again. A handler that outlives its lease cannot complete after recovery. Production handlers must use fenced, idempotent tool effects; this iteration does not provide exactly-once execution for arbitrary external effects. A bounded worker polling loop is implemented, not evaluated. A process entry point, trusted adapters and physical handoff integration remain separate work.

| Queue parameter | Default | Bound or meaning |
|---|---|---|
| `lease_ticks` | 400 | Positive ticks; 10 s at the simulator's 40 Hz, an assumption to calibrate |
| `max_attempts` | 3 | 1 to 10 total assignments; exhaustion fails the task |
| `priority` | 0 | 0 to 9, higher first; no fairness guarantee |
| Recovery `limit` | 100 | 1 to 1000 rows per transaction |
| Dependencies | empty | At most 32 unique existing task ids |

Task ids, worker ids and external request ids use 1 to 64 ASCII letters, digits, underscores, periods or hyphens. Persisted queue metadata contains no item-resolution or model-output payload; those belong to the reviewed mission integration. The queue and worker iteration are implemented, not evaluated by full E2. New cloud tests cover real process exit, competing workers/sweepers, dependency eligibility, stale completion, rollback and handler isolation.

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
