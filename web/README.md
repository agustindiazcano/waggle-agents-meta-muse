# Waggle Hive viewer

The Vite, TypeScript and three.js viewer reads a strict JSON Lines replay from
`waggle.replay`. It draws the recorded positions and state hashes. It computes no
simulator state and makes no control decisions. Implemented, not evaluated.

## Run

Use Node 24. From `web/`:

```powershell
npm ci
npm run models:sync -- --source C:\path\to\extracted-models
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open `http://127.0.0.1:5174/?gallery=1` for models, or `?demo=1` for the recorded demo.
Drag to orbit, right-drag to pan and use the wheel to zoom. In replay mode, select a
recorded entity and use **Focus** or **Fit all**. A missing GLB leaves a primitive in
the replay and produces a visible unavailable-model message in the gallery.

## Models and distribution

The gallery has 20 entries: 17 Meshy GLBs and three procedural previews (rack,
conveyor and loading dock). There are five robots, four people, three industrial
machines, a rack, a package, a truck, a fire extinguisher and a tree among the GLBs.
The revised worker replaces the old worker in replay mode. The gallery includes
the Black worker and Asian woman worker. Meshy GLBs remain unscaled as delivered;
their appearance and proportions need maintainer review.

Large GLBs are excluded from Git. Keep the separate model archive with this
checkout. `models.json` records each filename, byte count, SHA-256, animation names
and generation provenance. Extract the archive to a separate directory, then run
`models:sync`. The importer checks every file before copying, rejects malformed or
externally referenced GLBs and preserves a different existing destination file.
No API key or network access is needed to import. Original older GLBs remain in
the separate Meshy worktree; they are not deleted or included in the current pack.

The rack preview supports 1 to 10 bays and 1 to 6 levels. The conveyor and dock use
original repeated visual components. Their dimensions do not define simulator
geometry. The added tank and press correspond to the M-05 and M-06 concepts in
the legacy mockup; the existing industrial GLB is the M-04 gallery entry.

Human clips are selectable in the gallery. The pickup clip displays a separate
box that follows the midpoint of the two hand nodes during 35 to 90 percent of
the clip, with an authored offset. This timing is an artistic assumption for
inspection. A missing hand hides the box. The prop is removed on model changes.
The replay has no human pickup action or package pose, so this prop is confined
to the gallery. Replay humans select idle or in-place walk from consecutive
recorded positions, preferring `Idle_11` when present. The replay schema does not
identify chassis or human roles, so replay mode uses one model for each kind.

The maintainer confirmed commercial use under their Meshy Pro plan. Visual review
is pending. `meshy_equipment_tasks.json` records the five added generation tasks
and their actual credit consumption. No generated model is a simulation result.

## Verification

```powershell
npm test
npm run build
npx playwright install chromium
npm run test:browser
npm run test:models
```

`test:browser` checks the replay contract, primitive fallback, play, seek, camera
pan, focus, gallery controls and visible errors. It runs in `viewer.yml` without
the binary model pack. `test:models` explicitly requires the imported pack and
checks that every GLB decodes and exposes the recorded clips; missing assets fail.
Neither is an artistic review. `@playwright/test==1.64.1` is a development-only
dependency for these browser checks, as approved in ADR-029.

| Environment variable | Description | Default |
| --- | --- | --- |
| `WAGGLE_BROWSER_EXECUTABLE` | Optional installed Chromium executable for local browser tests | Playwright-managed Chromium |

`?demo=1` loads `public/demo.jsonl`, identical to the committed fixture from S01,
development seed 7, every four ticks for 120 ticks, commit label `fixture0`.
It is a development replay, not an experiment result.

Map geometry, overlays, live mode and role-specific replay assets remain separate
viewer work. The current viewer does not recompute state hashes or check the
footer digest. `waggle.replay.verify` checks a replay outside the browser.
