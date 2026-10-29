@AGENTS.md

# Waggle Hive: working notes for Claude Code

- Source of truth: `PLAN.md`, then `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`, `docs/EXPERIMENTS.md`. If they conflict, stop and ask.
- Read `LASTCONTEXT.md` and `PENDING.md` at the start of a session. Update both at the end.
- Python 3.12 with uv. Run tasks as `uv run <target>`: `lint`, `type`, `test`, `ci`, `experiments-dev`, `experiments-test`, `report`. `make` is not available on this machine.
- Import rules (import-linter, enforced in CI): `waggle.sim` and `waggle.control` must not import `llm`, `governance`, `maintenance` or `mcp_server`. `waggle.mcp_server` must not import `governance`. Violation fixtures live in `tests/importlint_fixtures/`, never under `src/`.
- Never print or log environment variable values. `.env` is gitignored; `.env.example` lists names only.
- Do not push or change remotes. The maintainer pushes and merges.
