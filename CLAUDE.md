@AGENTS.md

# Waggle Hive: notes for Claude Code

Waggle Hive is a safety and reliability control plane for LLM-directed warehouse robot fleets. Python package: `waggle`. Subtitle: "Safety and reliability control plane for LLM-directed warehouse robot fleets".

## Read order

1. `AGENTS.md` (imported above)
2. `PLAN.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DECISIONS.md`
5. `docs/THREAT_MODEL.md`
6. `docs/EXPERIMENTS.md`
7. [`docs/GOTCHAS.md`](docs/GOTCHAS.md)
8. [`docs/PHASE1_BRIEF.md`](docs/PHASE1_BRIEF.md) (maintainer brief for Phase 1: branch order B0 to B8, specs, gates)
9. `LASTCONTEXT.md`
10. `PENDING.md`

If two documents conflict, stop and ask. `LASTCONTEXT.md` and `PENDING.md` are updated when a task ends. Whatever the order above, always read those two before starting any task (AGENTS.md section 1).

## Quick reference

- Python 3.12 with uv. Run tasks as `uv run <target>`: `lint`, `type`, `test`, `ci`, `experiments-dev`, `experiments-test`, `report`. `make` is not available on this machine.
- Import contract violation fixtures live in `tests/importlint_fixtures/`, never under `src/`.
- Agents push their task branch and open the PR with `gh pr create`. Never push to `main`, never force push, do not change remotes. The maintainer merges.
