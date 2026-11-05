# Waggle Hive: Last context

Updated: 2026-11-05. README evidence audit on docs/readme-evidence in
.worktrees/readme-evidence, based on origin/main e57d41c. Preserve the root
worktree's dirty context, recordings, GLBs and all other worktrees.

Code progress of the project (estimate by eye, code only): 95% on 2026-11-05,
margin about 2 points.
Retains PENDING.md's bottom-up audit; README work adds no product code.
Task Code % is -. Delivery scope estimate remains 98% plus/minus 1 point.

## Done last

- Strengthened the README opening around the decision-to-motion path: physical
  constraints, distributed ownership, counterexample search and execution checks.
- Verified PR 197 is merged at a83d31e. Added a dedicated visual multimodal section
  covering image requests, vision-v1, sanitization/guard, registry resolution,
  typed failures and the E7 mock baseline. Operator release is not launched.
- Verification: 107 targeted vision/attachment/E7 tests and 127 documentation
  checks passed; changed-file style and git diff --check passed.
- Maintainer's percentile wording was a metaphor for technical depth, not a
  requested ranking. The README uses concrete mechanisms and evidence.

- Reviewed the maintainer's README checklist. Added live Meta evidence within
  the first 20 lines, a source/test-size table, simpler route and result tables,
  and the exact author signature plus supplied LinkedIn and portfolio links.
- Source-size snapshot at 8cdf754: 33819 source lines and 37389 test lines.
  Method and scope are in docs/VALIDATION_NOTES.md with reproduction details
  moved from the README. Tests require the link and preserve the documented facts.
- Fixed a submission paragraph that mixed guard roles from two routing profiles.
  Removed the claim that models are responsible for every decision.
- Two documentation-contract tests failed before the linked notes were added.
  The subsequent focused documentation run passed 127 tests.

- Follow-up: added experiment counts, populations, execution modes and outcomes.
  E1: 1440 runs, up to 30 robots/8 humans, full scenario population breakdown.
  E2: 20 runs, 2 robots/0 humans. E8 rollout: 10 robots/4 humans; control
  benchmark: 1 robot/1 human and 600 measured calls.
- Inspected four E4 artifacts: 8 scripted cases each, 32 evaluations. Verified
  muse-spark-1.3 and muse-wonder-1.0 in cloud smoke logs; both tests passed in
  each of runs 41932235675 and 41932240818.
- Maintainer requests direct reporting without repetitive caveats. Updated tables
  preserve execution modes and attribution. 126 docs checks pass in 2.90 seconds.
- Automatic command policy rejected the combined temporary-artifact cleanup
  command. Four waggle-readme-e4-* directories remain under the user's Temp
  directory, outside the repository. They contain downloaded public run artifacts.

- Replaced stale blanket live-testing claims with committed JUnit evidence:
  two passing live Meta text API smoke tests (Spark/Wonder), 184 heavy tests.
- Counted two E1 campaigns separately: 8 configurations x 90 runs each,
  1440 executions total; repeated seeds are not independent samples.
- Added 2D closed-loop simulation detail: fixed 40 Hz step, bicycle/differential
  drive, delayed actuation, noisy LiDAR at 10 Hz, forked rollouts and PostgreSQL.
- Linked cloud E2 chaos and four scripted E4 successes; E9 mutation run failed.
- Latest main CI has 3999 passing tests and four failures, explicitly disclosed.
  Fixed stale E2 result link and relative image-snippet links. Remaining inherited
  failures: E9 fork shim, result layout, and style in demo files/DECISIONS.
- Existing link check failed before repair; 126 focused documentation checks
  then passed. Ruff lint/format passed on the adjusted README contract test.
- No experiment launched, paid call, secret access, safety change or result edit.

## Current state

README changes committed locally as 5c1066c. The pre-push check rejected
publication because the current HEAD has no full CI stamp. Secret scan reported
no issue. No push or PR was attempted after that denial; full local CI is
forbidden by the cloud-first rules. Resolve the gate before publishing.
The maintainer reviews and merges.

## Prompt for the next session

Continue Waggle Hive on docs/readme-evidence in .worktrees/readme-evidence.
Read AGENTS.md, LASTCONTEXT.md and PENDING.md. The README now leads with verified
technical capabilities and executed-run evidence. Review the local diff and
publication gate. Keep true measurement boundaries and do not describe smoke
calls as live court-quality evaluations. Main e57d41c has inherited CI failures;
track them via PENDING rows 138-139. No full local suite or new paid runs.
Preserve other worktrees and root uncommitted files. Maintainer merges PRs.
