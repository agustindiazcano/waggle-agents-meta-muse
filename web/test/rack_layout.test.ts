import { test } from "node:test";
import assert from "node:assert/strict";
import { rackLayout } from "../src/rack_layout.ts";

test("builds repeated uprights and shelves for any bay count", () => {
  const parts = rackLayout(3, 4);
  assert.equal(parts.filter((part) => part.kind === "upright").length, 8);
  assert.equal(parts.filter((part) => part.kind === "shelf").length, 12);
  assert.equal(parts.filter((part) => part.kind === "beam").length, 24);
  assert.deepEqual(parts.find((part) => part.kind === "shelf")?.position, [-2.4, 0.82, 0]);
});

test("refuses invalid bay and shelf counts", () => {
  for (const [bays, levels] of [[0, 3], [11, 3], [1, 0], [1, 7], [1.5, 3], [1, NaN]]) {
    assert.throws(() => rackLayout(bays!, levels!), (error: unknown) => error instanceof RangeError);
  }
});
