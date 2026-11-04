import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_OVERLAY_VISIBILITY,
  describeOverlays,
  envelopeColorHex,
  ghostPathColorHex,
  toggleOverlayLayer,
} from "../src/overlays.ts";

const HASH = "a".repeat(64);

test("describeOverlays reports not provided when frame overlays are empty", () => {
  const summary = describeOverlays({});
  assert.equal(summary.envelopesLabel, "Safety envelopes: not provided");
  assert.equal(summary.shadowsLabel, "Lidar shadows: not provided");
  assert.equal(summary.ghostsLabel, "Rollout ghosts: not provided");
});

test("describeOverlays formats counts, margins, stride and K/H provenance", () => {
  const summary = describeOverlays({
    envelopes: [
      {
        robot_id: "robot_0",
        polygon: [
          [0, 0],
          [1, 0],
          [1, 1],
        ],
        margin_m: 0.45,
        nearest_id: "human_0",
      },
    ],
    lidar_shadows: [
      {
        robot_id: "robot_0",
        polygon: [
          [2, 0],
          [4, 0],
          [3, 2],
        ],
        sample_stride: 4,
      },
    ],
    ghost_paths: [
      {
        variant_index: 0,
        robot_id: "robot_0",
        passed: true,
        points: [
          [0, 0],
          [2, 2],
        ],
        k: 5,
        horizon_s: 45,
        snapshot_hash: HASH,
      },
      {
        variant_index: 1,
        robot_id: "robot_0",
        passed: false,
        points: [
          [0, 0],
          [1, 1],
        ],
        k: 5,
        horizon_s: 45,
        snapshot_hash: HASH,
      },
    ],
  });
  assert.ok(/1 envelope.*margin 0\.45 m.*nearest human_0/.test(summary.envelopesLabel));
  assert.ok(/1 shadow.*stride 4/.test(summary.shadowsLabel));
  assert.ok(/2 paths \(1 pass, 1 fail \| K=5, H=45\.0s\)/.test(summary.ghostsLabel));
});

test("overlay colors and visibility toggles are pure functions", () => {
  assert.equal(envelopeColorHex("stopped"), 0xff5a5a);
  assert.equal(envelopeColorHex("reduced"), 0xffc247);
  assert.equal(envelopeColorHex("normal"), 0x4aa3ff);
  assert.equal(ghostPathColorHex(true), 0x4be39a);
  assert.equal(ghostPathColorHex(false), 0xff6b6b);

  const next = toggleOverlayLayer(DEFAULT_OVERLAY_VISIBILITY, "ghosts");
  assert.equal(next.envelopes, true);
  assert.equal(next.shadows, true);
  assert.equal(next.ghosts, false);
});
