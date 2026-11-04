import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MAX_FRAME_BYTES, ReplayError, parseFrameLine, parseReplay } from "../src/frame_schema.ts";

const HASH = "a".repeat(64);
const HASH2 = "b".repeat(64);

function frame(tick: number, hash: string = HASH): Record<string, unknown> {
  return {
    schema_version: 1,
    tick,
    dt: 0.025,
    sim_time: tick * 0.025,
    state_hash: hash,
    run: { commit: "c0", seed: 7, scenario_id: "S01", source: "replay" },
    robots: [
      {
        id: "robot_0",
        x: 1,
        y: 2,
        heading: 0,
        active: { speed: 1, turn: 0 },
        speed_limit: null,
        mode: null,
      },
    ],
    humans: [{ id: "human_0", x: 5, y: 5, heading: 0 }],
    zones: [{ id: "z", polygon_id: "z", occupant: null, token: null }],
    machines: [],
    overlays: {},
    events: [],
  };
}

function header(count: number): Record<string, unknown> {
  return {
    type: "header",
    schema_version: 1,
    commit: "c0",
    seed: 7,
    scenario_id: "S01",
    dt: 0.025,
    world_hash: HASH,
    frame_count: count,
    resimulable: true,
  };
}

const footer = { type: "footer", final_state_hash: HASH, frames_digest: HASH2 };

function file(h: unknown, frames: unknown[], f: unknown = footer): string {
  return [h, ...frames, f].map((x) => JSON.stringify(x)).join("\n") + "\n";
}

function expectError(fn: () => unknown, pattern: RegExp): void {
  assert.throws(fn, (error: unknown) => error instanceof ReplayError && pattern.test(error.message));
}

test("a valid replay parses", () => {
  const replay = parseReplay(file(header(2), [frame(1), frame(2)]));
  assert.equal(replay.frames.length, 2);
  assert.equal(replay.header.commit, "c0");
});

test("the committed fixture parses", () => {
  const text = readFileSync(new URL("./fixtures/demo.jsonl", import.meta.url), "utf-8");
  const replay = parseReplay(text);
  assert.equal(replay.frames.length, replay.header.frame_count);
});

test("unknown schema_version in a frame is rejected", () => {
  const f = frame(1);
  f["schema_version"] = 2;
  expectError(() => parseFrameLine(JSON.stringify(f)), /schema version/);
});

test("unknown field in a frame is rejected", () => {
  const f = frame(1);
  f["extra"] = 1;
  expectError(() => parseFrameLine(JSON.stringify(f)), /unknown field/);
});

test("unknown field inside a robot is rejected", () => {
  const f = frame(1);
  (f["robots"] as Record<string, unknown>[])[0]!["color"] = "red";
  expectError(() => parseFrameLine(JSON.stringify(f)), /unknown field in robots/);
});

test("missing field in a frame is rejected", () => {
  const f = frame(1);
  delete f["humans"];
  expectError(() => parseFrameLine(JSON.stringify(f)), /missing field/);
});

test("valid overlays are accepted and unknown keys outside overlays.extra are rejected", () => {
  const f = frame(1);
  f["overlays"] = {
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
          [1, 1],
          [3, 1],
          [2, 2],
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
          [2, 1],
        ],
        k: 5,
        horizon_s: 45,
        snapshot_hash: HASH,
      },
    ],
    extra: { custom_tag: "ok" },
  };
  const parsed = parseFrameLine(JSON.stringify(f));
  assert.equal(parsed.overlays.envelopes?.length, 1);
  assert.equal(parsed.overlays.lidar_shadows?.length, 1);
  assert.equal(parsed.overlays.ghost_paths?.length, 1);
  assert.deepEqual(parsed.overlays.extra, { custom_tag: "ok" });

  const bad = frame(1);
  bad["overlays"] = { unknown_top_key: [] };
  expectError(() => parseFrameLine(JSON.stringify(bad)), /unknown field in overlays/);
});

test("a frame over the size cap is rejected", () => {
  const text = JSON.stringify(frame(1));
  expectError(() => parseFrameLine(text, text.length - 1), /too large/);
  assert.equal(MAX_FRAME_BYTES, 262_144);
});

test("a non-finite or wrong typed number is rejected", () => {
  const f = frame(1);
  (f["robots"] as Record<string, unknown>[])[0]!["x"] = "1";
  expectError(() => parseFrameLine(JSON.stringify(f)), /finite number/);
});

test("a bad state hash is rejected", () => {
  expectError(() => parseFrameLine(JSON.stringify(frame(1, "xyz"))), /SHA-256/);
});

test("a frame that is not JSON is rejected", () => {
  expectError(() => parseFrameLine("{nope"), /not valid JSON/);
});

for (const key of ["commit", "seed", "scenario_id", "schema_version"]) {
  test(`header missing ${key} is rejected`, () => {
    const h = header(1);
    delete h[key];
    expectError(() => parseReplay(file(h, [frame(1)])), /missing field|schema version/);
  });
}

test("header with unknown schema_version is rejected", () => {
  const h = header(1);
  h["schema_version"] = 9;
  expectError(() => parseReplay(file(h, [frame(1)])), /schema version/);
});

test("header with unknown field is rejected", () => {
  const h = header(1);
  h["extra"] = true;
  expectError(() => parseReplay(file(h, [frame(1)])), /unknown field/);
});

test("frame_count mismatch is rejected", () => {
  expectError(() => parseReplay(file(header(3), [frame(1), frame(2)])), /frame_count/);
});

test("out of order and repeated ticks are rejected", () => {
  expectError(() => parseReplay(file(header(2), [frame(2), frame(1)])), /strictly increase/);
  expectError(() => parseReplay(file(header(2), [frame(2), frame(2)])), /strictly increase/);
});

test("frame run metadata that differs from the header is rejected", () => {
  const f = frame(1);
  (f["run"] as Record<string, unknown>)["seed"] = 8;
  expectError(() => parseReplay(file(header(1), [f])), /does not match the header/);
});

test("a missing or wrong footer is rejected", () => {
  expectError(() => parseReplay(file(header(1), [frame(1)], { type: "footer" })), /missing field/);
  expectError(
    () => parseReplay(file(header(1), [frame(1)], { ...footer, final_state_hash: HASH2 })),
    /final_state_hash/,
  );
});

test("a file with too few lines is rejected", () => {
  expectError(() => parseReplay(JSON.stringify(header(1))), /header, a frame and a footer/);
});
