import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MAX_FILE_BYTES, loadReplayBlob, loadReplayText } from "../src/loader.ts";

const fixture = readFileSync(new URL("./fixtures/demo.jsonl", import.meta.url), "utf-8");

test("a good file loads", () => {
  const result = loadReplayText(fixture);
  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.replay.frames.length, result.replay.header.frame_count);
  }
});

test("a bad file returns a clear error and no replay", () => {
  const result = loadReplayText("not a replay");
  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.ok(result.error.length > 0);
    assert.equal("replay" in result, false);
  }
});

test("a file with one tampered frame field returns an error", () => {
  const rows = fixture.split("\n");
  rows[1] = (rows[1] as string).replace('"overlays":{}', '"overlays":{"x":1}');
  const result = loadReplayText(rows.join("\n"));
  assert.equal(result.ok, false);
});

test("a Blob is read as text", async () => {
  const result = await loadReplayBlob(new Blob([fixture]));
  assert.equal(result.ok, true);
});

test("a Blob over the file cap is refused before reading", async () => {
  const fake = { size: MAX_FILE_BYTES + 1, text: () => Promise.reject(new Error("read")) };
  const result = await loadReplayBlob(fake as unknown as Blob);
  assert.equal(result.ok, false);
});

test("a Blob that fails to read returns an error", async () => {
  const fake = { size: 10, text: () => Promise.reject(new Error("read")) };
  const result = await loadReplayBlob(fake as unknown as Blob);
  assert.equal(result.ok, false);
});
