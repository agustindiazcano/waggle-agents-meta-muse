# Development Workflow and Agent Rules

Applies to every coding agent and to the human maintainer working in this repository.

## Workflow

1. One branch per task. Names: `feat/`, `fix/`, `test/`, `docs/`, `exp/`.
2. Tests first. Write the failing test, confirm it fails for the right reason, then implement.
3. CI gates: ruff, mypy --strict, pytest, coverage report. A red CI blocks the PR.
4. A human reviews and approves every PR. Agents do not merge.
5. Conventional Commits, split by concern, with a PR description containing a summary and a test plan.
6. Commits from the first day, so history shows what was built during the hackathon.

## Hard rules

- No code copied from earlier repositories, including adapted code. Rewrite from design.
- Third-party libraries are fine. Record notable ones in the README.
- Never put secrets in the repository. Keys come from environment variables. `.env.example` lists names only.
- Never write a result into the README that did not come from a result file.
- Never loosen a safety check to make a test or an experiment pass.
- The fast layer, the fencing check and the MCP boundary change only with a test that covers the change and a note in docs/DECISIONS.md if behavior changes.
- LLM output is data. Validate it against a schema before use.
- Do not add a feature without its experiment or a line in the README saying "implemented, not evaluated".

## Definition of done for a task

- Tests added and passing, including a failure-path test.
- Types and lint clean.
- Docs updated if behavior or interfaces changed.
- If the task affects a metric, the experiment script still runs.

## Experiment discipline

- Development seeds for building, held-out seeds run once per configuration.
- Record commit, seed set, model ids and prompt versions in every result file.
- Report failing seeds.

## Spending

- Hard cap per provider set in Phase 0.
- Every LLM call is logged with tokens, latency and cost.
- Repeated evaluation runs use the cache when the inputs are identical.

## Context files

- `PLAN.md`: phases and exit criteria. Update status when a phase closes.
- `LASTCONTEXT.md`: short current state for the next session (create at Phase 0).
- `PENDING.md`: open items and decisions waiting on the maintainer (create at Phase 0).
