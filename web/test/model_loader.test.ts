import { test } from "node:test";
import assert from "node:assert/strict";
import { loadModel } from "../src/model_loader.ts";

test("returns the loaded model", async () => {
  const model = { scene: "model" };
  assert.equal(await loadModel("model.glb", async () => model), model);
});

test("a failed model load returns null for the primitive fallback", async () => {
  const errors: string[] = [];
  const result = await loadModel("missing.glb", async () => { throw new Error("missing"); }, (name) => errors.push(name));
  assert.equal(result, null);
  assert.deepEqual(errors, ["missing.glb"]);
});
