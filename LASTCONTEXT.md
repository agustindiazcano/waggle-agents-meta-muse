# Waggle Hive: Last context

Updated: 2026-10-31 (mapped S03 routes implemented).

## Done last
- Main is at `04fba9d`, including PRs 50 to 53. The principal checkout remains on main with `index (1).html` untracked and untouched.
- PR 54 (`feat/map-aisle-graph`) binds explicit A* graphs to loaded rectangular maps and checks conservative clearance and complete resource declarations. Tests first failed on the missing module; 17 focused tests passed. Final parent CI: 1582 passed, 4 skipped, 97% coverage; Ruff, strict mypy and all 3 import contracts passed. Pre-push, including gitleaks, passed.
- `feat/s03-planned-routes` is based on PR 54. Mapped A* now supplies S03 admission's waypoints and complete requests. Admission reconstruction preserves per-resource directions. The missing-module test and a mixed-direction retry regression failed before implementation; all 85 coordination/integration tests now pass, including existing route completion and independent collision checks.

## Current state
- The maintainer approved the remaining implementation plan with mock on 2026-10-31, including database implementation and migrations, fencing, audit and MCP wiring. See `docs/MOCK_IMPLEMENTATION.md`. Human review and merge remain required.
- S03 retains its staging, approach and parking coordinates, admission-on/off initial hashes and original E1 scenario. Its graph topology is explicitly declared, not automatically generated from map geometry. Static graph validation does not certify curved tracking or moving-obstacle avoidance. Implemented, not evaluated by E2.
- E2 has a manual cloud harness but no sweep has run. E3 has 25 declarations with pending maintainer labels; missing labels or target layers must block evaluation. Paid calls and held-out execution remain unauthorized; provider prerequisites PENDING 4, 5, 9 and 12 remain open.
- Next: persistent PostgreSQL coordination, workers, recovery and handoff, then production MCP and the full mock command flow. No database implementation or migration has been added yet. Keep all remaining scope.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/MOCK_IMPLEMENTATION.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-028 through ADR-032), docs/THREAT_MODEL.md, docs/EXPERIMENTS.md and docs/GOTCHAS.md. Inspect remote PRs, status, branches and worktrees before acting.

Main was last at 04fba9d. PR 54 contains map binding. Inspect feat/s03-planned-routes and its PR before duplicating mapped S03 admission integration and the per-resource direction regression. The S03 branch depends on PR 54; merge and retarget in dependency order. Keep original E1 S03 unchanged and distinguish integration tests from E2 results.

The maintainer approved the remaining implementation plan with mock, including database implementation and migrations, fencing, audit and MCP wiring. Do not ask again for that scope. Follow docs/MOCK_IMPLEMENTATION.md; next is persistent coordination, workers/recovery and handoff. Inspect migration revision before applying any migration. No paid calls, cap or secret changes, or held-out runs without specific authorization. Keep E3 pending labels unscored and fail closed for missing layers. No scope is cut.

Use isolated worktrees and task branches, tests first with the failing run shown, Conventional Commits and Co-Authored-By trailers. Before push require uv run ci on HEAD, gitleaks and a reviewed diff. Never commit to main, force push, merge PRs or commit index (1).html. The maintainer reviews and merges.
```
