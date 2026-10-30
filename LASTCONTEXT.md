# Waggle Hive: Last context

Updated: 2026-10-30 (E3 development corpus, isolated worktree).

## Done last
- Branch `test/e3-case-corpus`, stacked on `feat/guard-classifier-interface` (PR 49), in `C:/Users/agusd/.codex/visualizations/2026/10/30/01a18ea4-b4aa-7941-ae69-1931e66bf8e0/waggle-e3`. Other agents use their own worktrees; E2 is active in `feat/e2-simulator-harness`. Do not edit their files or switch their branches.
- Added 25 synthetic development declarations in `data/e3/cases.json` for T1 to T6, T11 and T18. Each declares source, entry point, trusted synthetic setup, exact untrusted input, probe and target layer. Each threat has multiple probes and a reference near-lookalike. Construction metadata is not a ground-truth label. All 25 reviews are pending with null labels, reviewers and rationales.
- Tests first: 18 failed because the corpus file did not exist, 1 passed. With the corpus: 19 declaration tests passed. `uv run pytest tests/unit/experiments/test_e3_corpus.py tests/unit/test_docs_content.py tests/unit/test_docs_consistency.py tests/unit/test_gotchas_prior_work.py -q`: 51 passed. Changed-file ruff, format and mypy passed.
- Added review instructions and linked the corpus from README and EXPERIMENTS. No evaluation runner, provider call, new dependency, protected-path change, stored result or `.env` change. Declaration validation is not an E3 measurement.

## Current state
- Main includes B0 to B17, E1 development results (commit `94bacc4`), the pure coordination model, the S03 admission adapter and ADR-032 schemas, identity and sanitizers. Verified ancestor checks for the schema, identity, sanitizer, scope and S03 branches against `origin/main`. PR 48 was open when checked; do not merge it as an agent. Reconcile its context update when merging this task.
- E1 dev still has human-collision runs and a measured throughput cost. Read `results/e1/dev/report.md` for the figures. Held-out seeds were not run. E2 and E3 were not run.
- PR 49 is open with green local and remote CI: guard classifier protocol, strict JSON, sanitizer/fence ordering, fail-closed timeouts and an offline mock. No production detector or inbox delivery yet. E3 declarations are on this stacked branch, not main.
- Next: maintainer labels and reviews the E3 declarations; implement the missing entry points and production evaluator, which must refuse pending cases or missing layers. Incident text has no sanitizer source yet; message schema, catalog compatibility, read-back, production court prompt and planner integration are incomplete. The corpus README records these gaps. E2 is another agent's active task. No scope is cut.
- PENDING 47 remains maintainer-owned: audit/rate-limit repository, migration and MCP server wiring need approval. PENDING 4, 5, 9 and 12 block paid calls. E2 has no database dependency.
- Gate dates follow AGENTS.md: G2 Oct 31 night, G3 Nov 1 night, G4 Nov 2 night. Keep the pre-push CI stamp requirement until the maintainer changes it.
- Traps: verify the current branch before every commit; do not commit `index (1).html`; use an isolated worktree; use the S03 admission variant for E2 and preserve original S03 for E1. Async classifier adapters must cooperate with cancellation and use transport timeouts. C: filled during setup, then the maintainer freed space. Sandbox access to uv cache and Git metadata required elevated tool execution.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/DECISIONS.md (ADR-028 addendum, ADR-030, ADR-031 and ADR-032 with their addenda), docs/EXPERIMENTS.md (E1, E2, E3) and docs/GOTCHAS.md. Fetch and inspect status, branches, worktrees and recent PRs. Check merged work reached main with git merge-base --is-ancestor.

Use your own worktree and a new type/short-description branch. Never commit or push to main, merge PRs, force push or commit index (1).html. Check git branch --show-current before every commit. Tests first, show the failing run, Conventional Commits with a Co-Authored-By trailer. Keep uv run ci green on HEAD and inspect the diff before each push. Never change hooks to bypass the gate.

PR 49 contains the guard classifier interface and mock, with local and remote CI green. Branch test/e3-case-corpus is stacked on feat/guard-classifier-interface and contains 25 E3 development declarations, all pending maintainer labels. Check PR states before repeating work. Reconcile the PR 48 handoff. The maintainer merges PR 49 first and then retargets the corpus PR to main. No E3 evaluation has run.

Next: the maintainer reviews E3 case labels and rationales before any evaluation. Build the missing production entry points and evaluator after checking the corpus README; never score construction metadata as labels or missing implementations as passes. E2 development evaluation is active in another agent's worktree; coordinate without editing it. Run experiments in the cloud. No paid call or held-out run. Audit logic, migrations, fencing and MCP boundary changes require maintainer approval. PENDING 4, 5, 9 and 12 still block paid calls. Nothing is cut; report gaps against AGENTS section 18 and the work that closes them.
```
