/** A prop for inspecting an authored pickup clip in the isolated gallery. */
import * as THREE from "three";

export class PickupPreview {
  readonly prop: THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>;
  private readonly root: THREE.Object3D;
  private readonly left: THREE.Object3D | undefined;
  private readonly right: THREE.Object3D | undefined;
  private readonly leftPoint = new THREE.Vector3();
  private readonly rightPoint = new THREE.Vector3();

  /** Find the two authored hand nodes and create a separate preview box. */
  constructor(root: THREE.Object3D) {
    this.root = root;
    this.left = root.getObjectByName("LeftHand");
    this.right = root.getObjectByName("RightHand");
    this.prop = new THREE.Mesh(
      new THREE.BoxGeometry(0.35, 0.3, 0.28),
      new THREE.MeshStandardMaterial({ color: 0xb98955, roughness: 0.9 }),
    );
    this.prop.name = "Gallery pickup prop";
    this.prop.visible = false;
    root.add(this.prop);
  }

  /** Follow the hands during the preview grip; timing is an artistic assumption. */
  update(clip: string, time: number, duration: number): boolean {
    this.prop.visible = false;
    if (clip !== "Male_Bend_Over_Pick_Up" || this.left === undefined ||
        this.right === undefined || !Number.isFinite(time) || time < 0 ||
        !Number.isFinite(duration) || duration <= 0) return false;
    const progress = (time % duration) / duration;
    this.prop.position.set(0, 0.15, 0.4);
    this.prop.rotation.set(0, 0, 0);
    if (progress >= 0.35 && progress < 0.9) {
      this.root.updateWorldMatrix(true, true);
      this.left.getWorldPosition(this.leftPoint);
      this.right.getWorldPosition(this.rightPoint);
      this.root.worldToLocal(this.leftPoint);
      this.root.worldToLocal(this.rightPoint);
      this.prop.position.copy(this.leftPoint).add(this.rightPoint).multiplyScalar(0.5);
      this.prop.position.y -= 0.08;
    }
    this.prop.visible = true;
    return true;
  }

  /** Remove and release only the prop owned by this preview. */
  dispose(): void {
    this.prop.removeFromParent();
    this.prop.geometry.dispose();
    this.prop.material.dispose();
  }
}
