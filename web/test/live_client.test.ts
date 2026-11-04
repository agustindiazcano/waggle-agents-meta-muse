import { test } from "node:test";
import assert from "node:assert/strict";
import { parseLiveMessage } from "../src/live_client.ts";

const HASH = "b".repeat(64);

test("parseLiveMessage parses a world message from /ws/live", () => {
  const msg = parseLiveMessage(
    JSON.stringify({
      type: "world",
      schema_version: 1,
      name: "warehouse_v1",
      bounds: [0, 0, 20, 12],
      walls: [
        [
          [0, 0],
          [20, 0],
          [20, 1],
        ],
      ],
      racks: [],
      zones: [
        {
          id: "corridor_n",
          kind: "one_lane_aisle",
          capacity: 1,
          polygon: [
            [2, 2],
            [8, 2],
            [8, 4],
          ],
        },
      ],
      hash: HASH,
    }),
  );
  assert.equal(msg.kind, "world");
  if (msg.kind === "world") {
    assert.equal(msg.world.name, "warehouse_v1");
    assert.equal(msg.world.hash, HASH);
  }
});

test("parseLiveMessage parses a live frame message with overlays", () => {
  const msg = parseLiveMessage(
    JSON.stringify({
      schema_version: 1,
      tick: 3,
      dt: 0.05,
      sim_time: 0.15,
      state_hash: HASH,
      run: {
        commit: "abc1234",
        seed: 42,
        scenario_id: "s01_blind_corner",
        source: "live",
      },
      robots: [],
      humans: [],
      zones: [],
      machines: [],
      overlays: {
        envelopes: [
          {
            robot_id: "robot_0",
            polygon: [
              [0, 0],
              [1, 0],
              [1, 1],
            ],
            margin_m: 0.5,
            nearest_id: null,
          },
        ],
      },
      events: [],
    }),
  );
  assert.equal(msg.kind, "frame");
  if (msg.kind === "frame") {
    assert.equal(msg.frame.tick, 3);
    assert.equal(msg.frame.overlays.envelopes?.length, 1);
  }
});

test("parseLiveMessage parses a server error message and rejects malformed payloads", () => {
  const msg = parseLiveMessage(JSON.stringify({ type: "error", error: "frame_too_large", tick: 9 }));
  assert.equal(msg.kind, "error");
  if (msg.kind === "error") {
    assert.equal(msg.code, "frame_too_large");
    assert.equal(msg.tick, 9);
  }

  assert.throws(() => parseLiveMessage("not-json"), /not valid JSON/);
  assert.throws(() => parseLiveMessage(JSON.stringify({ type: "error", error: "" })), /error code/);
});
