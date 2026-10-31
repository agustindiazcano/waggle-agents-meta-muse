# Waggle Hive: Last context

Updated: 2026-10-31 (PR 50 context reconciled with main).

## Done last
- PR 50 adds 25 synthetic development declarations for T1 to T6, T11 and T18. Each names its target layer, probes and benign near-lookalike. All labels, reviewers and rationales remain null for maintainer review. No E3 evaluation was run.
- Tests first: 18 failed because the corpus was missing, 1 passed. After implementation, 19 declaration tests and 51 corpus/docs tests passed. No provider call, held-out seed, result file, new dependency or `.env` change.
- PR 49 classifier work is merged to main. PR 50 now includes main's latest handoff; its conflict resolution is in this merge commit. E3 labels remain pending and must not be scored before review.

## Current state
- Main includes B0 to B17, E1 development results, pure leases/corridors, S03 admission, ADR-032 schemas/identity/sanitizers and the fail-closed classifier interface. E1 held-out seeds were not run.
- PR 50 contains the E3 corpus, incorporates the latest main history and should target main. E2 harness PR 51 is open but E2 was not run. A* route-planner PR 52 is open. Check remote state before duplicating or retargeting work.
- E3 labels need maintainer review before any evaluation. Production entry points/evaluator remain incomplete, including incident text source, message schema, catalog compatibility, read-back, court prompt and planner integration. Pending cases or missing layers must fail closed.
- Database implementation and migrations require separate maintainer approval. Paid calls remain blocked by PENDING 4, 5, 9 and 12. No scope is cut.
- Keep `index (1).html` uncommitted. Use isolated worktrees and do not edit another branch's files. Check the branch before each commit.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-028 addendum and ADR-030 to ADR-032), docs/THREAT_MODEL.md, docs/EXPERIMENTS.md (E1 to E3) and docs/GOTCHAS.md. Fetch and inspect status, current branch, remote branches, worktrees and open PRs.

PR 49 is merged. PR 50 adds the 25 E3 development declarations; all labels are pending maintainer review. PR 51 prepares the E2 simulator comparison but E2 has not run. PR 52 adds pure A* routing and is open. Check these PRs before repeating work. Do not merge PRs.

Continue with E3 label review and integration only after maintainer decisions. Keep pending cases unscored and fail closed when an entry point or target layer is missing. No paid calls, E2 runs or held-out seeds without explicit maintainer authorization. Database work and migrations also require separate approval. Nothing is cut; close gaps against AGENTS.md section 18.

Use a new branch and isolated worktree, tests first with the failing run shown, no force push, no main commits, and never commit `index (1).html`. Run `uv run ci`, gitleaks and review the staged diff before pushing. The maintainer reviews and merges.
```
