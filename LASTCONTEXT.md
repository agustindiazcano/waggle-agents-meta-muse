# Waggle Hive: Last context

Updated: 2026-10-31 (mock implementation authorized; map binding).

## Done last
- Main is at `04fba9d`, including PRs 50 to 53. The principal checkout remains on main with `index (1).html` untracked and untouched.
- The maintainer approved the remaining mock implementation plan, including database implementation/migrations, fencing, audit and MCP wiring. The sequence and acceptance criteria are in `docs/MOCK_IMPLEMENTATION.md`. Human review and merge remain required.
- Branch `feat/map-aisle-graph` adds map binding for explicit A* graphs, conservative static clearance checks, exact capacity-one resource declarations and waypoint output. The first test failed on the missing module; 17 map-binding tests then passed. `uv run ci`: 1582 passed, 4 skipped, 97% coverage; Ruff, strict mypy and all 3 import contracts passed.

## Current state
- Map binding supports rectangular geometry and straight graph segments only. The caller supplies topology and a clearance enclosing the chassis at every heading. It does not certify curved tracking, turning feasibility or moving-obstacle avoidance. Status: implemented, not evaluated by E2.
- S03 still uses explicit fixture routes and requests. Next, connect it to mapped A* routes and preserve per-resource directions when rebuilding admission state. Retain the original E1 S03 and paired E2 geometry.
- E2 has a manual cloud simulator harness but no sweep has run. E3 has 25 declarations with pending maintainer labels; no pending label or missing target layer may be scored. Paid calls and held-out execution remain unauthorized; provider prerequisites PENDING 4, 5, 9 and 12 remain open.
- Persistent database, production MCP, director/court orchestration, crisis loop, viewer integration, maintenance and multimodal work remain pending. Use mock providers and keep the full scope.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/MOCK_IMPLEMENTATION.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-028 through ADR-032), docs/THREAT_MODEL.md, docs/EXPERIMENTS.md and docs/GOTCHAS.md. Inspect remote PRs, status, branches and worktrees before acting.

Main includes PRs 50 to 53 and was last at 04fba9d. Inspect feat/map-aisle-graph and its PR before duplicating the new map_graph implementation. Next is mapped A* route integration with S03 admission, including a regression for per-resource directions in restored state. Keep original E1 S03 unchanged and distinguish integration tests from E2 results.

The maintainer approved the remaining implementation plan with mock, including database implementation and migrations, fencing, audit and MCP wiring. Do not ask again for that scope. Read docs/MOCK_IMPLEMENTATION.md for order and checks. Do not make paid calls, change caps or secrets, or run held-out seeds without specific authorization. Keep E3's pending labels unscored and fail closed for missing layers. No scope is cut.

Use isolated worktrees and task branches, tests first with the failing run shown, Conventional Commits and Co-Authored-By trailers. Before push require uv run ci on HEAD, gitleaks and a reviewed diff. Never commit to main, force push, merge PRs or commit index (1).html. The maintainer reviews and merges.
```
