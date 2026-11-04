/** Original modular display objects; these dimensions carry no simulator meaning. */
import * as THREE from "three";

/** Build an authored conveyor or loading dock for the model gallery. */
export function makeEquipment(id: string): THREE.Group {
  if (id !== "conveyor" && id !== "dock") throw new RangeError(`Unknown equipment: ${id}`);
  const group = new THREE.Group();
  function box(name: string, size: [number, number, number],
    position: [number, number, number], color: number): THREE.Mesh {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size),
      new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.3 }));
    mesh.name = name;
    mesh.position.set(...position);
    group.add(mesh);
    return mesh;
  }
  if (id === "conveyor") {
    for (const z of [-0.55, 0.55]) {
      box("rail", [3.6, 0.18, 0.1], [0, 0.85, z], 0xe6ad27);
      for (const x of [-1.4, 1.4]) box("leg", [0.12, 0.8, 0.12], [x, 0.4, z], 0x526170);
    }
    for (let i = 0; i < 12; i++) {
      const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 1, 16),
        new THREE.MeshStandardMaterial({ color: 0xb8c2c9, metalness: 0.7, roughness: 0.4 }));
      roller.name = "roller";
      roller.position.set(-1.65 + i * 0.3, 0.88, 0);
      roller.rotation.x = Math.PI / 2;
      group.add(roller);
    }
  } else {
    box("platform", [3.8, 1.1, 2.6], [0, 0.55, 0], 0x687583);
    box("deck", [3.8, 0.08, 2.6], [0, 1.14, 0], 0x8d98a2);
    for (const x of [-1.3, 1.3]) {
      box("bumper", [0.25, 0.65, 0.16], [x, 0.78, 1.4], 0x202630);
      box("edge marker", [0.3, 0.08, 2.6], [x, 1.2, 0], 0xe6ad27);
    }
    box("ramp", [1.8, 0.12, 1.5], [0, 1.08, 1.8], 0x89939e).rotation.x = 0.12;
  }
  return group;
}

/** Release meshes and materials owned by a procedural gallery preview. */
export function disposeEquipment(group: THREE.Group): void {
  group.traverse((part) => {
    if (part instanceof THREE.Mesh) {
      part.geometry.dispose();
      const materials = Array.isArray(part.material) ? part.material : [part.material];
      for (const material of materials) material.dispose();
    }
  });
}
