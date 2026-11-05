# Waggle Hive: Last context

Updated: 2026-11-04. README cleanup and banner prepared in .worktrees/readme-cleanup,
branch docs/readme-cleanup, based on docs/readme-brand-header and main 96158a2.
The maintainer explicitly requested no tests for this documentation-only task
and requested a PR when finished. Published against main as PR 191:
https://github.com/agustindiazcano/waggle-agents-meta-muse/pull/191

Code progress of the project (estimate by eye, code only): 95% on 2026-11-04,
margin about 2 points, using the current PENDING.md audit. Delivery scope is 98%
plus/minus 1 point (ADR-097). This banner is presentation work, task Code % is -;
no product code or experiment result changed.

## Done last

- Implemented the vision nice-to-have on branch feat/vision-label in
  .worktrees/vision-label (ADR-099): vision-v1 strict schema with no package
  id field, vision adapter in waggle.llm, label pipeline in waggle.multimodal
  (sanitizer, guard fail closed, legibility threshold, registry lookup in
  code) and the E7 vision mock runner with a trust-the-label baseline.
  Mock only, not evaluated: no paid call, no result file, fixtures pending
  maintainer label review. Verified locally: 145 targeted tests passed
  (vision, voice, attachments, providers), ruff and mypy --strict clean,
  style 23 passed. PR opened at the maintainer order; no test was run for
  the PR step. The maintainer reviews and merges.
- Maintainer explicitly disabled application suites for documentation-only PRs.
  Added a shared change-scope action and conditional Python/viewer jobs (ADR-098).
  Code changes retain checks; unknown paths and detection failures run suites.
  No local tests run. PR 191 includes this requested workflow change.
- Diagnosed both failed PR 191 CI jobs: the same stale documentation assertion
  expected E10 harness/caller to remain pending. Both runs had 3914 passing tests
  and this single failure. Updated the existing assertion to require implemented
  harness/caller text and the remaining live-evaluation column. No test was
  disabled. No local tests run, as requested; cloud checks validate the push.
- Removed the delivery/rubric checklist from README in favor of SUBMISSION.md,
  removed symbolic provision arguments and updated implementation status against
  source. Schema revision is 15; ADR-097 discards Vertex/cross-family E4 and
  defers voice/vision. Documented existing Meta-only routing and production
  advisor/maintenance/E10 wiring. Historical measured numbers are unchanged.
- No tests run for cleanup, by explicit maintainer instruction. Reviewed source,
  Markdown links and git diff; git diff --check passes. No runtime file changed.
- Added docs/assets/waggle-hive-header.html, original hexagon mark and SVG fleet
  illustration, local Meta symbol with source attribution, and the 1600 by 500
  Chrome screenshot. README embeds it directly below the project title.
- Visual inspection passed. Existing README title test first failed with the
  image before the H1; keeping H1 first fixed it. Focused documentation consistency
  and style checks passed: 42 tests in 6.95s. No full local suite was run.
- Earlier banner publication was blocked by the missing local CI stamp.
  The maintainer subsequently instructed documentation-only publication with no
  tests. Follow that explicit request without fabricating stamps or skipping hooks.

## Current state

- PR 191 merged as 594ac60 while the workflow change was being prepared.
  The CI-only follow-up is PR 192, branch ci/docs-only-scope in this worktree.
  Runs 41936830706 and 41936830633 passed scope detection and skipped Python
  and viewer respectively. No local tests. Maintainer reviews and merges PR 192.
- Preserve main's uncommitted LASTCONTEXT.md and untracked GLB files, plus all
  dirty and unmerged worktrees. No changes were made to those files.
- Video plan: ../waggle-video-demo-plan, docs/video-demo-plan,
  docs/VIDEO_DEMO_PLAN.md. Three-minute product demo using mocks; full global
  scene with three cells and thirty robots; persistent author/Meta banner.
  Video encoding, narration and final attribution still need verification.
- Current priorities are in PENDING.md. Live evaluations remain separate work.
  No paid call, held-out run, migration, secret access or safety change occurred.
- Never merge docs/context-wave3. Preserve the viewer binary pack and asset work.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md first.
The cleaned README and banner were merged in PR 191. The follow-up CI change
lives in .worktrees/readme-cleanup on ci/docs-only-scope, PR 192 against main.
The maintainer explicitly requested no tests and a PR for this documentation-only
task. Review PR 192 for the requested documentation-only suite skipping and do
not rerun tests. No runtime code or historical measurement changed. The HTML
source, local Meta symbol, attribution and 1600 by 500 capture are in docs/assets.
The earlier banner work passed 42 focused docs/style checks; cleanup was reviewed
without tests as requested. Never fabricate a stamp or skip hooks.
The maintainer reviews and merges.
Preserve dirty main context, untracked GLBs and all unmerged worktrees.
Use PENDING.md for current priorities and the 95% plus/minus 2 code estimate;
this presentation task does not change it. Video work stays in its worktree.
No paid call, held-out run, secret access, migration or safety change is
part of this task.
