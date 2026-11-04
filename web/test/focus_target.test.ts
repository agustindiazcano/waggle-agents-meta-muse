import { test } from "node:test";
import assert from "node:assert/strict";
import { focusTarget } from "../src/focus_target.ts";

test("finds the selected entity using its kind and id", () => {
  const frame = { robots: [{ id: "r1", x: 3, y: 4 }], humans: [{ id: "h1", x: 9, y: 2 }] };
  assert.deepEqual(focusTarget(frame, "human", "h1"), { x: 9, y: 2 });
  assert.deepEqual(focusTarget(frame, "robot", "r1"), { x: 3, y: 4 });
  assert.equal(focusTarget(frame, "human", "r1"), null);
});

test("missing entities fail without inventing a position", () => {
  assert.equal(focusTarget({ robots: [], humans: [] }, "robot", "r1"), null);
});
