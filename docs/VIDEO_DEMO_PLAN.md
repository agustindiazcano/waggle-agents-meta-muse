# Waggle Hive: three-minute product demo plan

Updated: 2026-11-04. Planning only; video production has not started.

## Direction

The maintainer requests a finished-product experience while implementation continues.
Use existing behavior where available and purpose-built mocks for missing integration.
The film is a continuous product story, without implementation-status cards in each scene.
This authorizes planning the demo experience, not production G-GLOBAL, paid calls,
migrations, safety changes or fabricated engineering measurements.

Proposed configuration: three cells, ten robots per cell, thirty robot advisors,
three cell organizers and one global coordinator. Highlight one existing robot per
cell as the organizer chassis; do not silently add an eleventh robot. The thirty
advisors and four coordination roles are not a total count of all model roles:
guard, court, diagnosis and planner roles also exist in the architecture.

## Storyboard

| Time | Picture and action | Purpose |
|---|---|---|
| 0:00-0:15 | Global view: three warehouses, thirty robots, trucks and packages; an urgent order arrives | Establish the product and scale of this demo configuration |
| 0:15-0:35 | Global coordinator assigns a transfer; zoom to a cell organizer and then a robot advisor | Make the agent hierarchy visible through one order |
| 0:35-1:05 | Organizer assigns pickup; package attaches to its carrier; a human crosses; safety envelope commands stop and motion resumes when allowed | Show productive motion constrained by deterministic safety |
| 1:05-1:30 | Package label tries to add an override; input screening, schema and tool permissions reject the attempt | Show the relevant defenses and the rejected action |
| 1:30-2:00 | Machine alert, maintenance ticket and part reservation; route proposal, simulator ghost paths and court review select an alternative | Show maintenance and crisis response as one workflow |
| 2:00-2:35 | Truck delay, global reassignment, local pickup and delivery; correlated order/package ids and final counters | Complete the original order across cells |
| 2:35-2:45 | One engineering card with a few verified figures and CI checks | Provide evidence without overwhelming the film |
| 2:45-3:00 | Return to fleet, delivered order, project name, repository and attribution | End on the product outcome |

## Required global scene

The maintainer explicitly confirmed that the global scene is a central deliverable.
Build a complete 3D environment, not only a diagram or a dashboard overview.
Reserve about fifty seconds for global action across the opening (fifteen seconds)
and resolution (thirty-five seconds), with additional hierarchy shots as needed.

- Three warehouses with streets, docks, connecting routes and ten robots per cell.
- Trucks visibly load, travel and unload packages between sites.
- The global coordinator receives the urgent order and assigns work to cell organizers.
- A truck delay triggers reassignment to another warehouse/truck and final delivery.
- Camera continuity: global network, selected warehouse, organizer, robot/package,
  global network again, incident, reassignment and delivery.
- Keep order, package and truck ids consistent across local and global views.
  Fleet, package and order counters must match the same demo-state sequence.

Implement missing global behavior as synchronized demo mocks. The film presents
the intended finished-product experience while implementation continues; do not
insert repeated conceptual/not-implemented status cards. Engineering measurements
and evidence remain sourced separately from the presentation mocks.

## Persistent lower banner and warehouse branding

The maintainer requests a small lower banner plus Meta logos on warehouse floors.
Proposed banner height is about seven percent of the frame (roughly 76 px at 1080p).
Use a dark background, white text and restrained typography. Keep it consistent
through the film, including global/local cuts. Reserve space above it for subtitles
and keep the banner clear of counters, event panels and important scene action.

| Position | Copy | Treatment |
|---|---|---|
| Left | Powered by Meta Muse | Small, readable brand line |
| Right, first line | Agustin Diaz Cano | Small author credit |
| Right, second line | MS Candidate, Systems Engineering | Smaller secondary line |

This is the working copy discussed with the maintainer, including the supplied
author name and credential. Confirm final model/brand wording before final export;
the repository also records the attribution line "Built with Muse Spark Open".
Keep that attribution on the closing card if required by the verified wording.

Use an official Meta logo asset as a floor decal or thin textured plane, rather
than generating an approximate logo or remodeling the GLBs. Place one per warehouse
in an open floor area near its entrance/dock, visible in the global and approach
shots, with moderate contrast and correct floor perspective. Avoid z-fighting and
keep safety overlays and routes readable. Record the asset source in ASSETS.md
when the asset is actually acquired. Banner and floor logos are planned only.

## Production sequence and acceptance

1. Export a five-second browser sample to the target MP4 format first. Inspect
   installed browser, capture draft and available encoders. FFmpeg and ffprobe
   were not found on PATH during planning; synthetic narration is not confirmed.
   Resolve encoding before spending time polishing the whole film.
2. Freeze scene ids, palette, English screen copy, narration and shot durations.
   Proposed delivery: 1920 by 1080, 30 fps, H.264 MP4 with AAC if audio is used.
3. Build a small deterministic demo-state runner outside the safety/control core.
   It owns only mock presentation state for global transfers and pending flows.
   The viewer consumes real exported frames where available. Mock events do not
   become simulator ground truth, audit records, experiment files or model logs.
4. Integrate three cells, existing GLBs, trucks, package loading, role selection,
   camera transitions and legible event panels. Counters derive from demo state.
   Every shot has a repeatable start time and can be captured independently.
5. Connect one causal event sequence: order, assignment, pickup, crossing stop,
   injection denial, maintenance alert, route review, delay, reassignment, delivery.
   Mock responses may stand in for pending model/service calls. No paid API is
   needed for capture; do not report mock latency as model performance.
6. Review a silent rough cut for causality, asset proportions, hands, package
   attachment, text size and camera continuity before audio work.
7. Add narration, subtitles, minimal transitions and the verified engineering card.
   Prefer no music as the first version; add licensed music only if useful.
8. Verify full playback, duration, codec, audio level, subtitle timing, attribution,
   secrets-free frames and every numeric claim. Deliver MP4, SRT, script, scene
   captures, demo source and a reproducible export command. The maintainer reviews
   the final render before publication.

## Reuse and evidence

- Main ae83dab includes PR 178. README describes the current limits and routes.
- The viewer has replay, map/overlay code and a separately distributed GLB pack.
- `src/waggle/experiments/demo_capture.py` exports crossing, overheating and
  schema-rejection scenes. Crossing uses oracle sensing; maintenance uses mock
  tools; injection demonstrates a strict schema, not a live semantic guard result.
- The dirty viewer-capture worktree contains a capture script draft. Review and
  coordinate ownership before adapting it; do not overwrite pending work.
- The global-custody worktree contains unmerged code. Do not treat it as merged
  or modify it as part of planning this presentation.
- Verify current CI counts from the selected run before using any count. Do not
  repeat the pasted 3,802-test claim as verified evidence.
- E2 admission and E9 planted-defect figures need their committed result sources
  checked before inclusion. Preserve small sample and selected-defect scope.
- Say automated CI checks unless continuous deployment is actually verified.
- Baseten and Modal are hosting providers, not evidence of independent model
  families. The primary court routes are related Meta models. Fast braking is
  deterministic code; model advisors add bounded caution.

## Boundaries and estimates

The three-minute editorial selection does not remove any project work from scope.
Work goes in a separate task worktree. Keep existing dirty worktrees intact.
No new runtime dependency or external service is necessary by design; an export
utility may be needed after the capability test. Prefer installed tools and make
no purchase. Final effort estimate follows the first successful export and asset
inspection; the pasted promise of completion in hours is not established.

Project code remains approximately 88 percent, plus or minus four points, by eye.
This planning task adds no product code. Mock presentation progress is tracked
separately and must not increase the core project estimate.

## Handoff and next actions

Planning worktree: C:/projects/projects-github-agustindiazcano/waggle-video-demo-plan.
Branch: docs/video-demo-plan, based on main ae83dab. The plan and context updates
are in this worktree, not in the main checkout. Inspect Git status before continuing.

Completed: repository/asset inventory, three-minute storyboard, mock presentation
scope, required global scene, banner specification, floor-logo approach and handoff.
Not completed: new global environment, demo-state runner, camera animation, banner,
logo placement, capture/export proof, narration, montage or final MP4. Do not report
these as built. No new implementation tests, paid calls or production changes.

Next agent: first inspect browser/encoder availability and make the five-second MP4
proof. Inspect the separate GLB pack and review the dirty viewer-capture draft
without overwriting it. Build the global environment and demo sequence in an isolated
implementation worktree, then create the silent rough cut before voice and polishing.
Use this plan as the current video brief; the maintainer's follow-up requests about
global action and branding are incorporated above. Deliver the full three minutes.
