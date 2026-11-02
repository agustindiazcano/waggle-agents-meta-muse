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
  /envelope|separation|margin|stopping/i,
  /integrat|velocity|accelerat|physics/i,
  /\bstep\s*\(/,
];

const ALLOWED_IMPORTS = new Set(["three", "./frame_schema.ts", "./loader.ts", "./player.ts", "./scene.ts"]);

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
