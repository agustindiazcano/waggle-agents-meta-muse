import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { PickupPreview } from "../src/pickup_preview.ts";

test("pickup prop follows both hands only during the grip part of the preview", () => {
  const root = new THREE.Group();
  const left = new THREE.Bone(); left.name = "LeftHand"; left.position.set(-0.2, 1, 0.4);
  const right = new THREE.Bone(); right.name = "RightHand"; right.position.set(0.2, 1, 0.4);
  root.add(left, right);
  const preview = new PickupPreview(root);
  preview.update("Male_Bend_Over_Pick_Up", 0, 4);
  assert.equal(preview.prop.visible, true);
  assert.equal(preview.prop.position.y, 0.15);
  preview.update("Male_Bend_Over_Pick_Up", 2, 4);
  assert.deepEqual(preview.prop.position.toArray(), [0, 0.92, 0.4]);
  left.position.y = 1.2; right.position.y = 1.2;
  preview.update("Male_Bend_Over_Pick_Up", 2.1, 4);
  assert.ok(preview.prop.position.y > 1);
  preview.update("Idle_11", 0, 4);
  assert.equal(preview.prop.visible, false);
  preview.dispose();
  assert.equal(preview.prop.parent, null);
});

test("missing hand bones or invalid timing never shows a floating pickup prop", () => {
  const root = new THREE.Group();
  const preview = new PickupPreview(root);
  assert.equal(preview.update("Male_Bend_Over_Pick_Up", 1, 4), false);
  assert.equal(preview.prop.visible, false);
  preview.dispose();
  for (const name of ["LeftHand", "RightHand"]) {
    const hand = new THREE.Bone(); hand.name = name; root.add(hand);
  }
  const withHands = new PickupPreview(root);
  for (const [time, duration] of [[NaN, 4], [-1, 4], [1, 0], [1, Infinity]]) {
    assert.equal(withHands.update("Male_Bend_Over_Pick_Up", time!, duration!), false);
    assert.equal(withHands.prop.visible, false);
  }
  withHands.dispose();
});
