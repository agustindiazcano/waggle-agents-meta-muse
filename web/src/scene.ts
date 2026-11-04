// three.js drawing of one frame as primitives, seen from above. It draws what the frame says and
// nothing else. The camera framing uses the extent of the recorded positions only.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import { animationForMotion, clipForAnimation, type HumanAnimation, type HumanPosition } from "./asset_motion.ts";
import { cameraBounds, fitHalf } from "./camera_fit.ts";
import { recenterCamera } from "./camera_navigation.ts";
import type { Frame } from "./frame_schema.ts";
import { loadModel } from "./model_loader.ts";

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
  private readonly controls: OrbitControls;
  private readonly robotGroup = new THREE.Group();
  private readonly humanGroup = new THREE.Group();
  private readonly robotGeometry = new THREE.BoxGeometry(0.9, 0.55, 0.2);
  private readonly noseGeometry = new THREE.ConeGeometry(0.18, 0.4, 3);
  private readonly humanGeometry = new THREE.CylinderGeometry(0.25, 0.25, 0.3, 16);
  private center = { x: 0, y: 0 };
  private half = 10;
  private extent = { width: 0, height: 0 };
  private robotModel: GLTF | null = null;
  private humanModel: GLTF | null = null;
  private lastFrame: Frame | null = null;
  private readonly humans = new Map<string, { position: HumanPosition; animation: HumanAnimation }>();
  private readonly mixers = new WeakMap<THREE.Object3D, { mixer: THREE.AnimationMixer; active: HumanAnimation | null }>();

  private readonly host: HTMLElement;

  constructor(host: HTMLElement) {
    this.host = host;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setClearColor(COLORS.background);
    this.host.appendChild(this.renderer.domElement);
    this.scene.add(this.robotGroup, this.humanGroup);
    this.scene.add(new THREE.AmbientLight(0xffffff, 2));
    const sun = new THREE.DirectionalLight(0xffffff, 2);
    sun.position.set(3, -5, 10);
    this.scene.add(sun);
    this.scene.add(new THREE.GridHelper(200, 200, COLORS.grid, COLORS.grid).rotateX(Math.PI / 2));
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(0, -0.001, 50);
    this.camera.lookAt(0, 0, 0);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.minZoom = 0.5;
    this.controls.maxZoom = 20;
    this.controls.zoomToCursor = true;
    this.controls.addEventListener("change", () => this.renderer.render(this.scene, this.camera));
    this.resize();
    window.addEventListener("resize", () => this.resize());
    const loader = new GLTFLoader();
    void loadModel("/models/carrier_bot.glb", (path) => loader.loadAsync(path)).then((model) => {
      if (model !== null) {
        this.robotModel = model;
        this.robotGroup.clear();
        if (this.lastFrame !== null) this.draw(this.lastFrame);
      }
    });
    void loadModel("/models/worker_v2.glb", (path) => loader.loadAsync(path)).then((model) => {
      if (model !== null) {
        this.humanModel = model;
        this.humanGroup.clear();
        if (this.lastFrame !== null) this.draw(this.lastFrame);
      }
    });
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
    this.camera.zoom = 1;
    this.controls.target.set(this.center.x, this.center.y, 0);
    this.camera.position.set(this.center.x, this.center.y - 0.001, 50);
    this.extent = { width: maxX - minX, height: maxY - minY };
    this.resize();
  }

  /** Focus a recorded position without changing replay or simulator state. */
  focus(x: number, y: number): void {
    const target = { x, y, z: 0 };
    const position = recenterCamera(this.camera.position, this.controls.target, target);
    this.center = { x, y };
    this.camera.position.set(position.x, position.y, position.z);
    this.controls.target.set(x, y, 0);
    this.camera.zoom = Math.max(1, Math.min(20, this.half / 3));
    this.resize();
  }

  draw(frame: Frame): void {
    this.lastFrame = frame;
    this.fill(this.robotGroup, frame.robots.length, () => {
      const group = new THREE.Group();
      group.add(new THREE.Mesh(this.robotGeometry, new THREE.MeshBasicMaterial()));
      const nose = new THREE.Mesh(this.noseGeometry, new THREE.MeshBasicMaterial({ color: 0xffffff }));
      nose.rotation.z = -Math.PI / 2;
      nose.position.x = 0.6;
      group.add(nose);
      const status = new THREE.Mesh(
        new THREE.RingGeometry(0.65, 0.75, 32),
        new THREE.MeshBasicMaterial({ color: COLORS.robot, side: THREE.DoubleSide }),
      );
      status.position.z = 0.01;
      group.add(status);
      if (this.robotModel !== null) {
        const model = this.orientModel(this.robotModel.scene.clone(true));
        group.add(model);
      }
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
      body.visible = this.robotModel === null;
      node.children[1]!.visible = this.robotModel === null;
      const status = node.children[2] as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
      status.material.color.setHex(color);
      status.visible = this.robotModel !== null;
    });
    this.fill(this.humanGroup, frame.humans.length, () => {
      if (this.humanModel !== null) {
        const model = this.orientModel(clone(this.humanModel.scene));
        this.mixers.set(model, { mixer: new THREE.AnimationMixer(model), active: null });
        return model;
      }
      const mesh = new THREE.Mesh(this.humanGeometry, new THREE.MeshBasicMaterial({ color: COLORS.human }));
      mesh.rotation.x = Math.PI / 2;
      return mesh;
    });
    frame.humans.forEach((human, i) => {
      const node = this.humanGroup.children[i] as THREE.Object3D;
      node.position.set(human.x, human.y, 0);
      node.rotation.z = human.heading + Math.PI / 2;
      const previous = this.humans.get(human.id);
      const position = { x: human.x, y: human.y, time: frame.sim_time };
      const animation = animationForMotion(previous?.position ?? null, position, previous?.animation ?? "Idle");
      this.humans.set(human.id, { position, animation });
      const state = this.mixers.get(node);
      if (state !== undefined && this.humanModel !== null) {
        if (state.active !== animation) {
          state.mixer.stopAllAction();
          const clipName = clipForAnimation(animation, this.humanModel.animations.map((clip) => clip.name));
          const clip = clipName === null ? null : THREE.AnimationClip.findByName(this.humanModel.animations, clipName);
          if (clip !== null) state.mixer.clipAction(clip).play();
          state.active = animation;
        }
        state.mixer.setTime(frame.sim_time);
      }
    });
    const present = new Set(frame.humans.map((human) => human.id));
    for (const id of this.humans.keys()) if (!present.has(id)) this.humans.delete(id);
    this.renderer.render(this.scene, this.camera);
  }

  private orientModel(source: THREE.Object3D): THREE.Group {
    const wrapper = new THREE.Group();
    source.rotation.x = Math.PI / 2;
    wrapper.add(source);
    return wrapper;
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
    this.half = fitHalf(this.extent.width, this.extent.height, aspect);
    this.renderer.setSize(width, height);
    Object.assign(this.camera, cameraBounds(this.half, aspect));
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
