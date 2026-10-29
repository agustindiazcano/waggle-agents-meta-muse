# Waggle Hive: Last context

Updated: 2026-10-29.

## Done last
- Phase 0 (foundation) finished on local branches: uv tooling, import-linter contracts with fixtures, docker compose with pgvector and placeholder services, CI workflow.
- `docs/name-consistency`: project name in every doc, CLAUDE.md read order.
- `docs/gotchas-and-prior-work`: `docs/GOTCHAS.md` (12 entries), PRIOR_WORK.md links the earlier repository.
- `docs/agents-rules`: new AGENTS.md committed unchanged, style test (detector tested on samples, BOM check), `heavy` and `llm` markers excluded from ci, `heavy.yml` workflow, `experiments-test` refuses to overwrite held-out results without `--force`, `tests/unit/test_tasks.py`, README Disclosure, PLAN priority order, compose images tagged `dev`, context-file rules in AGENTS.md.

## Current state
- Branches are stacked and not pushed: `docs/restructure` -> `feat/python-tooling` -> `feat/docker-compose` -> `feat/ci` -> `docs/context-files` -> `docs/name-consistency` -> `docs/gotchas-and-prior-work` -> `docs/agents-rules`. `main` has the two initial commits.
- `uv run ci` is green (ruff, mypy --strict, pytest without heavy and llm, import-linter).
- Remote origin stays `waggle-agents-meta-muse`. The maintainer pushes and merges.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, then LASTCONTEXT.md and PENDING.md. Run git status, git branch and git worktree list, then continue the stack with a new branch docs/providers-and-credits on top of docs/agents-rules. Scope: ADR-015 (provider plan and credits, proposed; ADR-007 marked superseded), ADR-016 (model tiers and roles, fleet planner), updates to ARCHITECTURE, README Models used, PLAN Phases 0, 5 and 5B, SUBMISSION credits, EXPERIMENTS E4 and E5; budget guard and role routing table in waggle.llm with tests first; .env.example names (remove Gemini, add Vertex and Modal; never touch .env). After it: chore/hooks-and-owners, then chore/final-check. Tests before content. No push, no merge. Update LASTCONTEXT.md and PENDING.md at the end of each branch.
```