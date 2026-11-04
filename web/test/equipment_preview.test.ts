import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { makeEquipment, disposeEquipment } from "../src/equipment_preview.ts";

test("the conveyor has repeated rollers and the dock has bumpers and a ramp", () => {
  const conveyor = makeEquipment("conveyor");
  assert.equal(conveyor.children.filter((part) => part.name === "roller").length, 12);
  const dock = makeEquipment("dock");
  assert.equal(dock.children.filter((part) => part.name === "bumper").length, 2);
  assert.ok(dock.getObjectByName("ramp"));
  for (const group of [conveyor, dock]) {
    for (const part of group.children) {
      assert.ok(part instanceof THREE.Mesh);
      assert.ok(part.position.toArray().every(Number.isFinite));
    }
    let disposed = 0;
    group.traverse((part) => {
      if (part instanceof THREE.Mesh) part.geometry.addEventListener("dispose", () => disposed++);
    });
    disposeEquipment(group);
    assert.equal(disposed, group.children.length);
  }
});

test("unknown equipment is rejected", () => {
  assert.throws(() => makeEquipment("missing"), /Unknown equipment/);
});
