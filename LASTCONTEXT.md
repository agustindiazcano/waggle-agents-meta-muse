# Last context

Updated: 2026-10-29. Phase 0 (Foundation) code work is done on local branches, not pushed.

## State
- Branches are stacked, one per task: `docs/restructure` -> `feat/python-tooling` -> `feat/docker-compose` -> `feat/ci` -> `docs/context-files`. `main` holds the two initial commits.
- Project name: Waggle Hive. Package: `waggle`. Remote origin: `waggle-agents-meta-muse` (unchanged on purpose).
- Tooling: uv, ruff, mypy --strict, pytest + coverage, hypothesis, import-linter, pre-commit. Tasks run as `uv run lint|type|test|ci|experiments-dev|experiments-test|report`.
- Import contracts: 2, both tested against real code (pass) and against `tests/importlint_fixtures/` (fail).
- Compose: db (pgvector/pgvector:pg16), api, worker, mcp_server, web. All reported healthy locally. Placeholders only.
- CI workflow written at `.github/workflows/ci.yml`; its commands were run locally, never on GitHub.

## Next
- Maintainer reviews, pushes and merges the branches in order, then confirms CI is green on GitHub.
- Then Phase 1 (simulator). Not started.
