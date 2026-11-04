import { test } from "node:test";
import assert from "node:assert/strict";
import { parseWorld } from "../src/world_schema.ts";

const hash = "a".repeat(64);
const polygon: [number, number][] = [
  [0, 0],
  [2, 0],
  [2, 1],
  [0, 1],
];
const world = {
  schema_version: 1 as const,
  name: "Warehouse",
  bounds: [0, 0, 20, 10] as [number, number, number, number],
  walls: [polygon],
  racks: [],
  zones: [{ id: "bay", kind: "station", capacity: 1, polygon }],
  hash,
};

test("accepts simulator world geometry bound to the replay hash", () => {
  assert.deepEqual(parseWorld(world, hash), world);
});

test("accepts unbounded simulator zone capacity as null", () => {
  const unbounded = { ...world, zones: [{ ...world.zones[0]!, capacity: null }] };
  assert.deepEqual(parseWorld(unbounded, hash), unbounded);
});

test("rejects a map from another replay", () => {
  assert.throws(() => parseWorld(world, "b".repeat(64)), /hash/);
});

test("rejects unknown fields, malformed polygons and nonfinite bounds", () => {
  assert.throws(() => parseWorld({ ...world, invented: true }, hash), /field/);
  assert.throws(() => parseWorld({ ...world, walls: [[[0, 0], [1, 1]]] }, hash), /polygon/);
  assert.throws(() => parseWorld({ ...world, bounds: [0, 0, Infinity, 2] }, hash), /bounds/);
});
