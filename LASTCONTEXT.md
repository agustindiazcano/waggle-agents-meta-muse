# Waggle Hive: Last context

Updated: 2026-10-31 (PRs 50 to 52 merged).

## Done last
- PR 50 merged: 25 synthetic E3 development declarations for T1 to T6, T11 and T18. Target layers, probes and benign near-lookalikes are declared. All labels, reviewers and rationales remain null for maintainer review. No E3 evaluation ran.
- PR 51 merged: paired S03 admission-on/off E2 simulator harness and manual cloud workflow. It records raw counts, Wilson intervals and limitations. No E2 sweep ran; the database chaos evaluation is still unimplemented.
- PR 52 merged: deterministic A* on a caller-supplied aisle graph, with per-corridor directions and whole-route reservation requests. It is not connected to map loading or the S03 simulator adapter.
- Main is at `942077e`. Local `uv run ci` passed for the merged work: 1565 passed, 4 skipped, 97% coverage, 3 import contracts kept.

## Current state
- Main contains B0 to B17, E1 development results, pure leases/corridors, S03 admission, A* routing, MCP schemas/identity/sanitizers, the fail-closed classifier interface and E3 declarations.
- E2 is implemented only as a simulator comparison harness and has not been run. Do not dispatch it without explicit maintainer authorization. No held-out seeds or paid calls have run.
- E3 declarations are merged but unlabeled. Production entry points and evaluation remain incomplete: incident text source, message schema, catalog compatibility, read-back, court prompt and planner integration. Pending cases or missing target layers must fail closed.
- Database implementation and migrations require separate maintainer approval. PENDING 4, 5, 9 and 12 still block paid calls. Nothing is cut.
- `index (1).html` remains untracked and must not be committed.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, PLAN.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (ADR-028 addendum and ADR-030 to ADR-032), docs/THREAT_MODEL.md, docs/EXPERIMENTS.md (E1 to E3) and docs/GOTCHAS.md. Run git fetch, git status, git branch --show-current, git branch -r, git worktree list and gh pr list.

Main is at 942077e. PRs 50, 51 and 52 are merged. PR 50 added the E3 corpus with all 25 labels pending. PR 51 added the paired S03 E2 simulator harness and manual cloud workflow; E2 has not run. PR 52 added the pure deterministic A* route planner; it is not wired to map loading or S03 admission. Verify these facts against GitHub before acting.

Continue Phase 3 and Phase 4 in AGENTS.md section 18; nothing is cut. Do not run E2, E3, paid calls or held-out seeds without explicit maintainer authorization. Keep pending E3 cases unscored and fail closed for missing labels or target layers. Do not implement the database or migration without separate approval. PENDING 4, 5, 9 and 12 still block paid calls.

Use a new isolated worktree and task branch, tests first with the failing run shown, Conventional Commits with a Co-Authored-By trailer, and never commit to main, force push, merge a PR, or commit `index (1).html`. Before push, require `uv run ci`, clean gitleaks, a reviewed staged diff and a non-main branch. The maintainer reviews and merges.
```
