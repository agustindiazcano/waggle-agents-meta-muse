import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, readFileSync, existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { inspectGlb, syncModels } from "../tools/model_files.mjs";

function glb(document = { asset: { version: "2.0" }, scenes: [{}], meshes: [{}] }) {
  const json = Buffer.from(JSON.stringify(document).padEnd(Math.ceil(JSON.stringify(document).length / 4) * 4));
  const header = Buffer.alloc(20);
  header.write("glTF"); header.writeUInt32LE(2, 4); header.writeUInt32LE(20 + json.length, 8);
  header.writeUInt32LE(json.length, 12); header.writeUInt32LE(0x4e4f534a, 16);
  return Buffer.concat([header, json]);
}

test("validates GLB containers and refuses malformed or external resources", () => {
  assert.deepEqual(inspectGlb(glb()).clips, []);
  assert.throws(() => inspectGlb(Buffer.from("bad")), /GLB/);
  const wrongLength = glb(); wrongLength.writeUInt32LE(20, 8);
  assert.throws(() => inspectGlb(wrongLength), /length/);
  assert.throws(() => inspectGlb(glb({ asset: { version: "2.0" }, scenes: [{}], meshes: [{}],
    images: [{ uri: "https://example.com/texture.png" }] })), /external/);
  const badChunk = glb(); badChunk.writeUInt32LE(0xffffffff, 12);
  assert.throws(() => inspectGlb(badChunk), /chunk/);
});

test("copies only verified models and refuses a mismatch before writing any file", () => {
  const root = mkdtempSync(join(tmpdir(), "waggle-models-"));
  try {
    const source = join(root, "source"); const dest = join(root, "dest"); mkdirSync(source);
    const bytes = glb(); writeFileSync(join(source, "worker.glb"), bytes);
    const entry = { file: "worker.glb", bytes: bytes.length,
      sha256: createHash("sha256").update(bytes).digest("hex"), clips: [] };
    syncModels([entry], source, dest);
    assert.deepEqual(readFileSync(join(dest, "worker.glb")), bytes);
    writeFileSync(join(source, "Worker-1.glb"), bytes);
    syncModels([{ ...entry, file: "Worker-1.glb" }], source, dest);
    assert.deepEqual(readFileSync(join(dest, "Worker-1.glb")), bytes);
    syncModels([entry], source, dest);
    assert.throws(() => syncModels([{ ...entry, sha256: "0".repeat(64) }], source, dest), /hash/);
    assert.throws(() => syncModels([{ ...entry, file: "../worker.glb" }], source, dest), /file/);
    assert.throws(() => syncModels([{ ...entry, clips: ["Idle_11"] }], source, dest), /clips/);
    assert.throws(() => syncModels([entry, { ...entry, file: "missing.glb" }], source,
      join(root, "empty")), /ENOENT/);
    assert.equal(existsSync(join(root, "empty")), false);
    writeFileSync(join(dest, "worker.glb"), "user asset");
    assert.throws(() => syncModels([entry], source, dest), /existing/);
    assert.equal(readFileSync(join(dest, "worker.glb"), "utf8"), "user asset");
  } finally { rmSync(root, { recursive: true, force: true }); }
});
