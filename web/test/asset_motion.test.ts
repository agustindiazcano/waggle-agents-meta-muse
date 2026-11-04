import { test } from "node:test";
import assert from "node:assert/strict";
import { animationForMotion, clipForAnimation } from "../src/asset_motion.ts";

test("selects walking only when the recorded position advances", () => {
  const previous = { x: 0, y: 0, time: 1 };
  assert.equal(animationForMotion(previous, { x: 1, y: 0, time: 2 }, "Idle"), "Casual_Walk_inplace");
  assert.equal(animationForMotion(previous, { x: 0, y: 0, time: 2 }, "Casual_Walk_inplace"), "Idle");
});

test("keeps animation for repeated frames and resets on backward seek", () => {
  const previous = { x: 0, y: 0, time: 1 };
  assert.equal(animationForMotion(previous, previous, "Casual_Walk_inplace"), "Casual_Walk_inplace");
  assert.equal(animationForMotion(previous, { x: 1, y: 0, time: 0 }, "Casual_Walk_inplace"), "Idle");
  assert.equal(animationForMotion(null, previous, "Casual_Walk_inplace"), "Idle");
});

test("prefers Idle_11 and falls back to the original idle when absent", () => {
  assert.equal(clipForAnimation("Idle", ["Idle", "Idle_11"]), "Idle_11");
  assert.equal(clipForAnimation("Idle", ["Idle"]), "Idle");
  assert.equal(clipForAnimation("Idle", []), null);
  assert.equal(clipForAnimation("Casual_Walk_inplace", ["Casual_Walk_inplace"]), "Casual_Walk_inplace");
});
