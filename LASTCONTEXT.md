# Waggle Hive: Last context

Updated: 2026-10-29.

## Done last
- Phase 0 foundation, then a stack of 11 local branches. Verified on `chore/final-check`: `uv sync --locked && uv run ci` (458 tests, ruff, mypy --strict, 2 import contracts kept) and `docker compose up --build -d` with all 5 services healthy.
- `docs/providers-and-credits`: ADR-015, ADR-016, ADR-017; `waggle.llm` budget guard, routing table, client; `waggle.governance` court and guard rules that fail closed.
- `chore/hooks-and-owners`: `tools/hooks/`, `.claude/settings.json`, `CODEOWNERS`, `protected_paths` CI job, result layout `results/<experiment>/heldout|dev/`.
- `docs/design-extensions` was created but has no commits and no content. A Write was blocked there, because the project hooks (live in the session) point to `tools/hooks/`, which does not exist on a branch cut from `docs/providers-and-credits`. Nothing was lost.

## Current state
- Nothing is pushed. Branches are stacked in this order: `docs/restructure`, `feat/python-tooling`, `feat/docker-compose`, `feat/ci`, `docs/context-files`, `docs/name-consistency`, `docs/gotchas-and-prior-work`, `docs/agents-rules`, `docs/providers-and-credits`, `chore/hooks-and-owners`, `chore/final-check`. `main` has the two initial commits.
- The empty branch `docs/design-extensions` points at the `docs/providers-and-credits` commit.
- The maintainer pushes (AGENTS.md section 2). The push order is in PENDING 1.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, then LASTCONTEXT.md and PENDING.md. Run git status, git branch and git worktree list.

Task: branch docs/design-extensions. Design documents only, no code. Tests first where a test applies (links and style tests must pass). Do not push.
Base: chore/final-check. The maintainer asked for "on top of docs/providers-and-credits", which chore/final-check contains. A branch cut from providers lacks tools/hooks/, and the project hooks then block Write and Edit. An empty docs/design-extensions already exists at the providers commit: delete it (git branch -d) and recreate it from chore/final-check. If the maintainer has merged the stack, base it on main instead.

1. docs/DECISIONS.md, status proposed:
 - ADR-018 "Sensing model and predictive caution": robots perceive through a simulated 2D lidar (ray casting against walls, racks and moving entities, with range, angular resolution, noise, dropout and occlusion). The fast layer reads only what the lidar detects. The exact detector keeps using ground truth. Optional variant: human beacons visible around corners. Prediction: constant velocity extrapolation of each detected object, closest point of approach (time and distance) compared with the robot's stopping distance. Prediction can only add restrictions earlier. The worst-case separation envelope stays the floor. No learned model. Camera and vision stay out of the control loop.
 - ADR-019 "Missions and handoff": a mission is a small task graph with dependency edges. A handoff is an event with an idempotency key at a rendezvous zone (capacity one, lease with fencing token). The dependent task becomes eligible exactly once. If the carrier dies, the lease expires, the task is reassigned, and fencing blocks the stale carrier. Inter-robot messages stay schema-validated and bounded.
 - ADR-020 "Failure history and purchase orders": a synthetic failure log, generated separately from the simulator's degradation dynamics (never shared parameters), used for retrieval of similar cases in diagnosis and for offline calibration of the predictor. MCP tool create_purchase_order against a simulated procurement table when stock is zero, idempotent per failure event, part number verified against the catalog in code first.
2. docs/ARCHITECTURE.md: add a Sensing and prediction section, a Missions and handoff section, failure_history and purchase_orders to the data model, and the new tool to the MCP tool list. Update the mermaid diagram and keep it consistent with the text.
3. PLAN.md: Phase 1 adds the lidar model and the beacon variant (scenario catalog becomes S01 to S36). Phase 2 adds the closest-point-of-approach predictor, with exit criterion "E1 ablation reported". Phase 3 adds task dependencies and the handoff. Phase 6 adds the failure log, history-based diagnosis and create_purchase_order. Keep the priority order from AGENTS.md section 18.
4. docs/EXPERIMENTS.md: E1 configurations: ground truth, lidar only, lidar with beacons; envelope only vs envelope with prediction. Metrics: collisions, near-misses, false stops, throughput, with Wilson intervals. New scenario family S31 to S36 "Coordinated handoff" (runner killed mid delivery, duplicate delivery, technician waiting, rendezvous contention, plus two more of your choice); update the catalog table and declare the target layer of each. E2: add the handoff chaos test with counts of double deliveries and double repair starts, baseline without fencing. E6: add diagnosis accuracy among the three failure modes with and without the failure history, wrong part orders, and duplicate purchase orders.
5. docs/THREAT_MODEL.md: add T14 spoofed or duplicated handoff (idempotency key, fencing), T15 lidar dropout or occlusion (conservative default, watchdog), T16 duplicate purchase order (idempotency key per failure event).
6. README layer table and Models and limits: lidar is simulated, vision is synthetic and not in the control loop. Mark each new element "designed, not implemented".
7. PENDING.md: ask the maintainer to approve numpy as a runtime dependency for waggle.sim before it is added.

Write the failing test first (tests/unit/test_design_extensions_docs.py) and show it failing, then write the content. Run uv run ci and show the output. Update LASTCONTEXT.md and PENDING.md, and give the maintainer the prompt for the following session.
```
