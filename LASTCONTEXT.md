# Waggle Hive: Last context

Updated: 2026-11-04. README cleanup and banner prepared in .worktrees/readme-cleanup,
branch docs/readme-cleanup, based on docs/readme-brand-header and main 96158a2.
The maintainer explicitly requested no tests for this documentation-only task
and requested a PR when finished. Published against main as PR 191:
https://github.com/agustindiazcano/waggle-agents-meta-muse/pull/191

Code progress of the project (estimate by eye, code only): 88% on 2026-11-04,
margin about 4 points, as reviewed in the previous main audit. Live E4 code
is estimated at 95% on PR 178;
real evaluation remains pending. This documentation resolution adds no code
and does not change the project estimate; task Code % is -. Experiments,
calibration, documents and delivery are excluded.
G-GLOBAL and other unmerged worktrees remain outside the estimate.

## Current state

- Video demo implementation is in .worktrees/video-demo, branch feat/video-demo.
  The deterministic 180 s scene (three warehouses, thirty robots, trucks, hero
  package), global minimap and WH-B cell map, banner, subtitles, synthetic
  narration and per-shot capture are built. All six maintainer GLBs are in
  demo/assets/ under Git LFS: Blue_Delivery_Truck on TRK-12, Shipping_Container
  beside each dock, and four distinct workers (worker-2 crosses the WH-B aisle
  on its Walking clip; the others play Idle_11). Verified with fixed-time
  stills at t=8 and t=50: all six load, no page errors beyond a favicon 404.
  The eight shots were recorded in GitHub Actions (workflow "Waggle Hive demo
  video shots", run 41936582563, all jobs passed) and downloaded to
  output/cloud/shot-<n>/shot-<n>.mp4 in this worktree (git-ignored). Not done:
  assembling the final MP4 and merging the maintainer-recorded audio. Reuse of the same models
  in the production viewer web/ is PENDING row 137, not built here.
- Video handoff is in ../waggle-video-demo-plan, branch docs/video-demo-plan.
  Read docs/VIDEO_DEMO_PLAN.md there. The maintainer wants a three-minute
  finished-product experience with mocks while implementation continues.
  Required: full 3D global scene (three cells, ten robots each, trucks, packages,
  coordinator, delay/reassignment/delivery), about fifty seconds across the film.
  Small lower banner: left "Powered by Meta Muse" (working brand wording), right
  "Agustin Diaz Cano" above "MS Candidate, Systems Engineering". One official Meta
  floor-logo decal per warehouse. Final attribution wording still needs checking.
  All are planned, not built. MP4 encoding and synthetic voice remain unverified.

- PR 178 implements live E4 A/B/C through build_client with fallbacks disabled
  (ADR-096). Live mode refuses baseline and D until a verified non-Muse route
  exists. Caps/model IDs are checked before calls. Results record provider mode,
  realized model IDs and fallback labels. Local tests use mocks with no spend.

- Main includes PRs 163 to 174: viewer gallery and overlays, CourtRuntime and
  CrisisRuntime, organizer E5 C2/C3, SDK fake-backed client test, E8 export,
  E1 diagnosis, scripted E4 CLI and Meta Wonder planning-role routes.
- Merged PR 176 corrects a false acceptance in validation/plan_rollout.py:
  robot contact flags do not include robot-pair separation. The rollout now
  reuses the independent detector's swept robot_robot_gap and existing margin,
  reporting SEPARATION_VIOLATION once per pair. No simulator experiment counters,
  fast-layer threshold, fencing, audit, MCP rule or trajectory was modified.

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
