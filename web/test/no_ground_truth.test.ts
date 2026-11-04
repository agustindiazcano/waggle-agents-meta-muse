import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

// The renderer owns nothing (ADR-002). This is a plain text check, not a proof: it fails when
// web/src names a geometry check, a physics step or a safety region, and it pins the imports.
const srcDir = new URL("../src/", import.meta.url);
const files = readdirSync(srcDir).filter((name) => name.endsWith(".ts"));

const FORBIDDEN = [
  /collid|collision/i,
  /intersect/i,
  /distanceTo|distanceToSquared|Math\.hypot|Math\.sqrt|Math\.pow|[\w)]\s*\*\*\s*[\w(]/,
  /Raycaster|Box3|Sphere\b|Plane\b|Frustum/,
  /separation|stopping/i,
  /integrat|velocity|accelerat|physics/i,
  /\bstep\s*\(/,
];

const ALLOWED_IMPORTS = new Set([
  "three",
  "three/addons/loaders/GLTFLoader.js",
  "three/addons/controls/OrbitControls.js",
  "three/addons/utils/SkeletonUtils.js",
  "./asset_motion.ts",
  "./camera_fit.ts",
  "./camera_navigation.ts",
  "./frame_schema.ts",
  "./focus_target.ts",
  "./gallery_manifest.ts",
  "./gallery.ts",
  "./rack_layout.ts",
  "./rack_preview.ts",
  "./live_client.ts",
  "./loader.ts",
  "./model_loader.ts",
  "./overlays.ts",
  "./pickup_preview.ts",
  "./equipment_preview.ts",
  "./player.ts",
  "./scene.ts",
  "./world_schema.ts",
]);

test("web/src has files to check", () => {
  assert.ok(files.length >= 4);
});

for (const name of files) {
  const text = readFileSync(new URL(name, srcDir), "utf-8");
  test(`${name} contains no ground truth computation`, () => {
    for (const pattern of FORBIDDEN) {
      assert.equal(pattern.test(text), false, `${name} matches ${pattern}`);
    }
  });
  test(`${name} imports only allowed modules`, () => {
    const imports = [...text.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1] as string);
    for (const spec of imports) {
      assert.ok(ALLOWED_IMPORTS.has(spec), `${name} imports ${spec}`);
    }
  });
}

test("the detector flags a sample with a collision check", () => {
  assert.equal(FORBIDDEN.some((p) => p.test("if (a.distanceTo(b) < r) collide()")), true);
});

test("the import allowlist rejects unlisted modules", () => {
  assert.equal(ALLOWED_IMPORTS.has("three/addons/physics.js"), false);
});
