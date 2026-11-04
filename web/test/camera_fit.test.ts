import { test } from "node:test";
import assert from "node:assert/strict";
import { cameraBounds, fitHalf } from "../src/camera_fit.ts";

test("fits the full horizontal extent in a portrait viewport", () => {
  const half = fitHalf(34, 3, 0.5);
  assert.ok(half * 0.5 >= 17);
  assert.ok(half >= 1.5);
});

test("fits the vertical extent in a wide viewport", () => {
  const half = fitHalf(4, 30, 2);
  assert.ok(half >= 15);
  assert.ok(half * 2 >= 2);
});

test("uses camera-relative bounds without applying the center twice", () => {
  assert.deepEqual(cameraBounds(10, 2), { left: -20, right: 20, top: 10, bottom: -10 });
});
