# Waggle Hive: Last context

Updated: 2026-10-29.

## Done last
- Phase 0 foundation, then the stack of local branches below. All verified on the last branch: `uv sync --locked && uv run ci` (458 tests, ruff, mypy --strict, 2 import contracts kept) and `docker compose up --build -d` with all 5 services healthy.
- `docs/providers-and-credits`: ADR-015 (provider plan and credits), ADR-016 (model tiers, fleet planner), ADR-017 (Muse court and LLM guard); `waggle.llm` budget guard, routing table (11 roles, declared fallbacks), client; `waggle.governance` court and guard rules that fail closed.
- `chore/hooks-and-owners`: `tools/hooks/` (safety guard, lint check, session start, protected paths report), `.claude/settings.json`, `CODEOWNERS`, `protected_paths` CI job, result layout `results/<experiment>/heldout|dev/`.
- `chore/final-check`: verification only; the forbidden-name test builds its names from fragments so `git grep -il` finds nothing.

## Current state
- Branches are stacked and not pushed, in this order: `docs/restructure`, `feat/python-tooling`, `feat/docker-compose`, `feat/ci`, `docs/context-files`, `docs/name-consistency`, `docs/gotchas-and-prior-work`, `docs/agents-rules`, `docs/providers-and-credits`, `chore/hooks-and-owners`, `chore/final-check`. `main` has the two initial commits.
- No real provider adapter exists, only the interface and the mock. The HTTP client dependency waits for maintainer approval (PENDING 9).
- The project hooks are new: the maintainer must review them in `/hooks` (PENDING 20).

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, then LASTCONTEXT.md and PENDING.md. Run git status, git branch and git worktree list. The maintainer has pushed the stacked branches (check which PRs merged). Next work is Phase 1 (simulator and ground truth) from PLAN.md: deterministic tick loop, world, robot classes, humans, the exact collision detector, replay by seed. Create a new branch per task (feat/sim-tick-loop first), tests first, no push, no merge. Do not start it until PENDING items 1 and 2 (push and green CI on GitHub) are confirmed by the maintainer. Update LASTCONTEXT.md and PENDING.md at the end of each branch.
```