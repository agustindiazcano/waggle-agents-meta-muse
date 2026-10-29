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
7. `docs/GOTCHAS.md`
8. `LASTCONTEXT.md`
9. `PENDING.md`

If two documents conflict, stop and ask. `LASTCONTEXT.md` and `PENDING.md` are updated at the end of every session.

## Quick reference

- Python 3.12 with uv. Run tasks as `uv run <target>`: `lint`, `type`, `test`, `ci`, `experiments-dev`, `experiments-test`, `report`. `make` is not available on this machine.
- Import contract violation fixtures live in `tests/importlint_fixtures/`, never under `src/`.
- Do not push or change remotes. The maintainer pushes and merges.
