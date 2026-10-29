# Waggle Hive: Last context

Updated: 2026-10-29.

## Done last
- `docs/agents-rules`: new AGENTS.md committed unchanged, style test, `heavy` and `llm` markers, `heavy.yml`, `experiments-test --force`, `tests/unit/test_tasks.py`, README Disclosure, PLAN priority order, context-file rules.
- `docs/providers-and-credits`: ADR-015 (provider plan and credits), ADR-016 (model tiers, fleet planner), ADR-017 (Muse court and LLM guard); ADR-006 and ADR-007 marked superseded with their text kept; ARCHITECTURE tiers table and planner; THREAT_MODEL, EXPERIMENTS (E3, E4 configs A to D, E5 planner), PLAN, README, SUBMISSION updated; the earlier guard model and the non-Meta third-family default removed.
- `waggle.llm`: budget guard (caps from `*_SPEND_CAP_USD`, fail closed), call log interface with in-memory implementation, mock provider, role routing table (`routes.toml`, 11 roles, declared fallbacks), client with labeled fallbacks and per-task caps. `waggle.governance`: pure court and guard decision rules. Outage of any provider escalates, tested per provider.
- `.env.example` has the Meta, Modal and Vertex names. `.env` was not touched.
- License notice "Built with Muse Spark Open" in README and `web/index.html` (wording unverified against the license text).

## Current state
- Branches are stacked and not pushed: `docs/restructure` -> `feat/python-tooling` -> `feat/docker-compose` -> `feat/ci` -> `docs/context-files` -> `docs/name-consistency` -> `docs/gotchas-and-prior-work` -> `docs/agents-rules` -> `docs/providers-and-credits`. `main` has the two initial commits.
- No real provider adapter exists yet, only the interface and the mock. The HTTP client dependency is waiting for maintainer approval (PENDING 9).

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, then LASTCONTEXT.md and PENDING.md. Run git status, git branch and git worktree list. Create chore/hooks-and-owners on top of docs/providers-and-credits and build it tests first: tools/hooks/ scripts (safety_guard.py, lint_check.py, session_start.py and one shared matching module, standard library only), .claude/settings.json, tools/hooks/protected_paths.txt, CODEOWNERS covering every protected path, held-out result layout results/<experiment>/heldout|dev/ with a schema test, a protected_paths CI job summary, README note that this is a weak control. Check the current Claude Code hooks documentation first. Then chore/final-check. No push, no merge. Update LASTCONTEXT.md and PENDING.md at the end of each branch.
```