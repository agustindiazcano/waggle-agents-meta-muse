import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { galleryModels, modelById } from "../src/gallery_manifest.ts";

test("lists every requested model and the configurable rack without duplicate ids or paths", () => {
  assert.equal(galleryModels.length, 25);
  assert.equal(new Set(galleryModels.map((model) => model.id)).size, 25);
  const files = galleryModels.flatMap((model) => model.file === null ? [] : [model.file]);
  assert.equal(new Set(files).size, 22);
  assert.equal(galleryModels.filter((model) => model.kind === "robot").length, 5);
  assert.equal(modelById("modular-rack")?.file, null);
  for (const id of ["worker-black", "worker-asian-woman", "flat-carrier", "tank", "press",
    "conveyor", "truck", "extinguisher", "tree", "dock", "worker-1", "worker-2", "worker-3", "worker-4", "shipping-container"]) assert.ok(modelById(id), id);
});

test("selects the new worker model and rejects unknown ids", () => {
  assert.equal(modelById("worker")?.file, "worker_v2.glb");
  assert.equal(modelById("missing"), null);
});

test("the distributable manifest pins every GLB offered by the gallery", () => {
  const manifest = JSON.parse(readFileSync(new URL("../models.json", import.meta.url), "utf-8")) as {
    models: { id: string; file: string; bytes: number; sha256: string; clips: string[] }[];
  };
  const expected = galleryModels.filter((model) => model.file !== null).map((model) => model.file);
  assert.deepEqual(manifest.models.map((model) => model.file).sort(), expected.sort());
  for (const model of manifest.models) {
    assert.equal(modelById(model.id)?.file, model.file);
    assert.ok(Number.isInteger(model.bytes) && model.bytes > 20);
    assert.ok(/^[a-f0-9]{64}$/.test(model.sha256));
    assert.ok(Array.isArray(model.clips));
  }
});
