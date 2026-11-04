/** Visual-only meshes for the configurable rack components. */
import * as THREE from "three";
import { rackLayout } from "./rack_layout.ts";

/** Assemble a rack preview from repeated supports, beams and shelves. */
export function makeRack(bays: number, levels: number): THREE.Group {
  const group = new THREE.Group();
  const colors = { upright: 0x3c668d, beam: 0xe17829, shelf: 0x7c858a };
  for (const part of rackLayout(bays, levels)) {
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(...part.size),
      new THREE.MeshStandardMaterial({ color: colors[part.kind], roughness: 0.75, metalness: 0.3 }),
    );
    mesh.position.set(...part.position);
    group.add(mesh);
  }
  return group;
}

/** Release only the meshes created for an obsolete rack preview. */
export function disposeRack(group: THREE.Group): void {
  for (const child of group.children) {
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      if (child.material instanceof THREE.Material) child.material.dispose();
    }
  }
}
