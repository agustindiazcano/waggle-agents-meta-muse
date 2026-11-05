# Waggle Hive: Last context

Updated: 2026-11-04. PR 178 (`exp/e4-live-runner`, ADR-096) incorporates
main 54aa19e, including merged PRs 175, 176 and 177. Resolved documentation
conflicts, preserving the main audit, live E4 status, README and rollout task
records, and both warning entries. The maintainer reviews and merges PRs.

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

- The maintainer requested publication of the docs PR and explicitly instructed
  no further tests for this documentation task. Publish docs/video-demo-plan
  against main; the maintainer reviews and merges. Earlier focused docs/style
  checks passed 51 tests and the plan commit secret scan found no leaks.
  No local full suite was run and no CI stamp was fabricated.
- Planned a three-minute finished-product demo in docs/VIDEO_DEMO_PLAN.md.
  The maintainer explicitly wants mocks for missing behavior while code work
  continues. Main ae83dab includes PR 178. Preserve dirty capture and global
  worktrees. Encoding and narration remain unverified; no video was produced.
  No product code added; project remains 88% +/-4 by eye on 2026-11-04.
- Updated the video plan with the required global action, persistent banner,
  author credit, floor decals and explicit successor-agent steps. Prior focused
  documentation/style checks passed 51 tests; this update adds documentation only.

- Reproduced PR 178 push CI failure in test_agents_section_3_is_cloud_first:
  AGENTS.md section 3 omitted dev seeds and the exact pre-push check wording.
  Restored the explicit cloud-only development sweep rule and pre-push wording;
  the existing regression test is unchanged. Session brief, style and docs
  consistency checks passed: 48 tests in 3.41s. Cloud CI remains pending.
  This documentation task adds no code; project estimate remains 88% +/-4.

- Resolved PR 178 conflicts against main 54aa19e. Only documentation was edited.
  Focused E4, CLI, style and documentation consistency checks passed: 55 tests
  in 8.91s using the existing environment after a new environment hit disk
  capacity. No paid call or result change. Full regression runs in cloud CI.
- PR 178 previously reported 36 focused E4/CLI/style tests passing, with failure
  coverage for missing caps/model IDs, provider outages, rejected configurations,
  held-out refusal, escalation and result labels. This is mock-backed evidence.

- Rewrote README in PR 177 with the project workflow, implementation status,
  model roles, development results and hackathon requirement/evidence matrix.
  Accepted participant rules and final delivery checks are not claimed complete.
- Preserved the main rollout fix and audit below while resolving PR 177 conflicts.
  PENDING.md keeps rollout task 130 and README task 131. Both GOTCHAS entries remain.
- No further tests were run, as requested by the maintainer for this README task.
  Earlier documentation checks passed 181 tests; lint and strict types passed.
  Full local CI was interrupted. The historical demo replay passed digest-only
  verification but differed at tick 4 on full resimulation; its fixture is unchanged.

- Tests first: 3 failed and 2 passed on the new proximity cases before the fix.
  Afterwards the rollout test file passed 30 tests; focused strict Mypy passed.
  ADR-095 records semantics; GOTCHAS records the detector flag trap.
- Still pending: E1 residual failures, E2 full chaos evaluation/physical wiring,
  E4 real evaluation and Vertex, E10 harness/execution, live safety overlay data,
  E6 production, real voice/vision, package integrity and E9 mutation arm.
- No paid call, held-out run, migration, secret access or dependency addition.
  See the PR test plan for the full gate and publishing status.

## Preserved work and assets


- Preserve dirty global-custody, Meshy and GLB worktrees and all unmerged work.
  Preserve C:/Users/agusd/.codex/artifacts/waggle-viewer-models-20261104.zip;
  binaries are ignored and imported using web/models.json. Viewer port is 5174,
  gallery URL uses ?gallery=1. Port 5173 belongs to another project.
- Never merge docs/context-wave3: its endpoint diff deletes thousands of lines.
  Remote branch deletion is the maintainer's. Ticket race patch d11c7c5 is
  already represented by 8ae51e3 on main; feat/maintenance-tickets needs no PR.
- Earlier viewer local browser validation lacked Chromium 1248; do not describe
  that local run as passed. Earlier validation notes remain in
  ../waggle-validation-156-163. No asset worktree or unmerged branch was removed.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md first.
The maintainer requested the docs PR and explicitly said to run no further tests
for this documentation task. Check publication status of docs/video-demo-plan;
the maintainer reviews and merges. Do not restart local tests for these docs.
For video work, use C:/projects/projects-github-agustindiazcano/waggle-video-demo-plan,
branch docs/video-demo-plan, and read docs/VIDEO_DEMO_PLAN.md. The maintainer wants
a three-minute finished-product experience using mocks while code work continues.
Include the full 3D global scene (three cells, thirty robots, trucks, packages,
coordinator, delay and reassignment), the small persistent lower banner with
"Powered by Meta Muse" on the left and "Agustin Diaz Cano" above
"MS Candidate, Systems Engineering" on the right, and official Meta floor decals.
Verify final attribution copy. These are planned, not built. Start with a
five-second MP4 export proof; encoding and synthetic narration are unverified.
Main ae83dab includes PR 178. Preserve dirty capture/global worktrees. Inspect
status, branches and worktrees, and fetch origin. PR 178 (`exp/e4-live-runner`)
incorporates main 54aa19e, including merged PR 177, with documentation conflicts
resolved. The cloud-first documentation regression was reproduced and fixed;
check the latest cloud CI before maintainer review. Live E4
A/B/C exists (ADR-096); D needs a verified non-Muse route. Real E4 evaluation,
E10 harness and production crisis wiring remain pending. Project code remains
about 88% plus/minus 4 points; court/E4 about 95%, estimated by eye. Preserve
ADR-095 rollout semantics, all pending tasks, warnings and unmerged worktrees.
Do not resume the stopped README tests. The replay fixture is historical and
not a current resimulation pass. Never merge docs/context-wave3. No paid call,
held-out run, migration, secret access or safety threshold change is authorized
by this handoff. Agents never merge PRs.
