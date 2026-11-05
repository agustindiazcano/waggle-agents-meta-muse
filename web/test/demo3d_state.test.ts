import { test } from "node:test";
import assert from "node:assert/strict";
import { DURATION_S, demoStateAt, robotCode, ROBOT_CODES } from "../src/demo3d_state.ts";
test("thirty robots with unique codes R-A01..R-C10 and hero R-B04", () => {
  assert.equal(ROBOT_CODES.length, 30);
  assert.equal(new Set(ROBOT_CODES).size, 30);
  assert.equal(robotCode(0, 0), "R-A01");
  assert.equal(robotCode(1, 3), "R-B04");
  assert.equal(robotCode(2, 9), "R-C10");
  const s = demoStateAt(8);
  assert.equal(s.robots.length, 30);
  assert.equal(s.hero.code, "R-B04");
  assert.equal(s.package.id, "PKG-8841");
  assert.equal(s.orderId, "ORD-1042");
});
test("deterministic: same time gives identical state", () => {
  assert.deepEqual(demoStateAt(50), demoStateAt(50));
  assert.ok(JSON.stringify(demoStateAt(10)) !== JSON.stringify(demoStateAt(11)));
});
test("at t=50 hero is stopped and worker-2 is crossing WH-B aisle", () => {
  const s = demoStateAt(50);
  assert.equal(s.hero.stopped, true);
  assert.equal(s.worker2.visible, true);
  assert.ok(s.worker2.z > -6 && s.worker2.z < 1);
  assert.ok(/STOP|Human/.test(s.event.text));
});
test("at t=8 no delivery yet; delivery by t=170", () => {
  assert.equal(demoStateAt(8).counters.delivered, 0);
  assert.ok(demoStateAt(8).subtitle.length > 0);
  assert.ok(demoStateAt(8).trucks.length >= 2);
  assert.equal(demoStateAt(170).counters.delivered, 1);
  assert.equal(DURATION_S, 180);
});
test("time is clamped to the 180 s sequence", () => {
  assert.equal(demoStateAt(-5).time, 0);
  assert.equal(demoStateAt(999).time, 180);
});
