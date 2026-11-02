# Waggle Hive viewer (replay file mode)

A Vite, TypeScript and three.js page that loads a replay file written by `waggle.replay`
(JSON Lines: one header line, one frame per line, one footer line), validates it strictly in
TypeScript, and draws a top-down view of robots and humans as primitives. Zones and events are
listed in a side panel. A hash bar shows the state hash the file records for the current frame.

## Run

```
cd web
npm ci
npm run dev        # then open the printed URL; pick a .jsonl file, or add ?demo=1
npm run typecheck
npm test           # node:test, no extra dependencies
npm run build
```

`?demo=1` loads `public/demo.jsonl`, a copy of `test/fixtures/demo.jsonl` (a test checks they are
equal). The fixture was produced once with `waggle.replay.recorder` from scenario S01, development
seed 7, every 4th tick for 120 ticks, commit label `fixture0`. It is a development seed file, not a
result.

## What it does not do

- It does not compute collisions, distances, safety envelopes or any ground truth. It draws what
  the frame says (ADR-002). A test scans `src` for such code.
- It does not recompute or check state hashes. Checking a replay is `waggle.replay.verify`.
- It does not draw overlays: a frame with a non-empty `overlays` object is rejected.
- It does not draw walls, racks or zone polygons, because the replay file carries only the world
  hash, not the world geometry.
- It does not check `frames_digest` in the footer (no hashing in the page).
- No live WebSocket mode, no GLB models, no browser test.
