import { test } from "node:test";
import assert from "node:assert/strict";
import { recenterCamera } from "../src/camera_navigation.ts";

test("recenter preserves the viewing offset and angle", () => {
  const result = recenterCamera(
    { x: 10, y: -5, z: 12 },
    { x: 8, y: -8, z: 0 },
    { x: 20, y: 30, z: 0 },
  );
  assert.deepEqual(result, { x: 22, y: 33, z: 12 });
});

test("no target movement keeps the camera position", () => {
  const target = { x: 2, y: 3, z: 0 };
  const camera = { x: 5, y: 7, z: 9 };
  assert.deepEqual(recenterCamera(camera, target, target), camera);
});
