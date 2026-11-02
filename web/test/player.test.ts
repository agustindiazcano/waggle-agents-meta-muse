import { test } from "node:test";
import assert from "node:assert/strict";
import { advance, initialPlayer, seek, togglePlay } from "../src/player.ts";

const ticks = [4, 8, 12, 16];
const dt = 0.025;

test("paused player does not move", () => {
  const next = advance(initialPlayer(), 1000, ticks, dt);
  assert.equal(next.index, 0);
});

test("playing at 1x moves by recorded simulation time", () => {
  let p = togglePlay(initialPlayer());
  assert.equal(p.playing, true);
  p = advance(p, 100, ticks, dt);
  assert.equal(p.index, 1);
});

test("playing stops at the last frame", () => {
  let p = togglePlay(initialPlayer());
  p = advance(p, 100000, ticks, dt);
  assert.equal(p.index, 3);
  assert.equal(p.playing, false);
});

test("seek clamps into range", () => {
  assert.equal(seek(initialPlayer(), -5, 4).index, 0);
  assert.equal(seek(initialPlayer(), 99, 4).index, 3);
  assert.equal(seek(initialPlayer(), 2, 4).index, 2);
});
