// three.js drawing of one frame as primitives, seen from above. It draws what the frame says and
// nothing else. The camera framing uses the extent of the recorded positions only.

import * as THREE from "three";
import type { Frame } from "./frame_schema.ts";

const COLORS = {
  background: 0x14181f,
  grid: 0x2a313d,
  robot: 0x4aa3ff,
  robotReduced: 0xffc247,
  robotStopped: 0xff5a5a,
  human: 0xf08a3c,
};

export class Scene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -100, 100);
  private readonly robotGroup = new THREE.Group();
  private readonly humanGroup = new THREE.Group();
  private readonly robotGeometry = new THREE.BoxGeometry(0.9, 0.55, 0.2);
  private readonly noseGeometry = new THREE.ConeGeometry(0.18, 0.4, 3);
  private readonly humanGeometry = new THREE.CylinderGeometry(0.25, 0.25, 0.3, 16);
  private center = { x: 0, y: 0 };
  private half = 10;

  private readonly host: HTMLElement;

  constructor(host: HTMLElement) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setClearColor(COLORS.background);
    this.host.appendChild(this.renderer.domElement);
    this.scene.add(this.robotGroup, this.humanGroup);
    this.scene.add(new THREE.GridHelper(200, 200, COLORS.grid, COLORS.grid).rotateX(Math.PI / 2));
    this.camera.position.set(0, 0, 50);
    this.camera.lookAt(0, 0, 0);
    this.resize();
    window.addEventListener("resize", () => this.resize());
  }

  /** Frame the camera on the extent of every recorded robot and human position. */
  fit(frames: readonly Frame[]): void {
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const frame of frames) {
      for (const item of [...frame.robots, ...frame.humans]) {
        minX = Math.min(minX, item.x);
        maxX = Math.max(maxX, item.x);
        minY = Math.min(minY, item.y);
        maxY = Math.max(maxY, item.y);
      }
    }
    if (!Number.isFinite(minX)) {
      return;
    }
    this.center = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
    this.half = Math.max(maxX - minX, maxY - minY, 4) / 2 + 3;
    this.resize();
  }

  draw(frame: Frame): void {
    this.fill(this.robotGroup, frame.robots.length, () => {
      const group = new THREE.Group();
      group.add(new THREE.Mesh(this.robotGeometry, new THREE.MeshBasicMaterial()));
      const nose = new THREE.Mesh(this.noseGeometry, new THREE.MeshBasicMaterial({ color: 0xffffff }));
      nose.rotation.z = -Math.PI / 2;
      nose.position.x = 0.6;
      group.add(nose);
      return group;
    });
    frame.robots.forEach((robot, i) => {
      const node = this.robotGroup.children[i] as THREE.Group;
      node.position.set(robot.x, robot.y, 0);
      node.rotation.z = robot.heading;
      const body = node.children[0] as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
      const color =
        robot.mode === "stopped"
          ? COLORS.robotStopped
          : robot.mode === "reduced"
            ? COLORS.robotReduced
            : COLORS.robot;
      body.material.color.setHex(color);
    });
    this.fill(this.humanGroup, frame.humans.length, () => {
      const mesh = new THREE.Mesh(this.humanGeometry, new THREE.MeshBasicMaterial({ color: COLORS.human }));
      mesh.rotation.x = Math.PI / 2;
      return mesh;
    });
    frame.humans.forEach((human, i) => {
      (this.humanGroup.children[i] as THREE.Object3D).position.set(human.x, human.y, 0);
    });
    this.renderer.render(this.scene, this.camera);
  }

  private fill(group: THREE.Group, count: number, make: () => THREE.Object3D): void {
    while (group.children.length < count) {
      group.add(make());
    }
    while (group.children.length > count) {
      group.remove(group.children[group.children.length - 1] as THREE.Object3D);
    }
  }

  private resize(): void {
    const width = Math.max(1, this.host.clientWidth);
    const height = Math.max(1, this.host.clientHeight);
    const aspect = width / height;
    this.renderer.setSize(width, height);
    this.camera.left = this.center.x - this.half * aspect;
    this.camera.right = this.center.x + this.half * aspect;
    this.camera.top = this.center.y + this.half;
    this.camera.bottom = this.center.y - this.half;
    this.camera.position.set(this.center.x, this.center.y, 50);
    this.camera.updateProjectionMatrix();
  }
}
