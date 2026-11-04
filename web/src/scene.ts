// three.js drawing of one frame as primitives, seen from above. It draws what the frame says and
// nothing else. The camera framing uses the extent of the recorded positions only.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import { animationForMotion, clipForAnimation, type HumanAnimation, type HumanPosition } from "./asset_motion.ts";
import { cameraBounds, fitHalf } from "./camera_fit.ts";
import { recenterCamera } from "./camera_navigation.ts";
import type { Frame, OverlayPoint } from "./frame_schema.ts";
import { loadModel } from "./model_loader.ts";
import {
  DEFAULT_OVERLAY_VISIBILITY,
  envelopeColorHex,
  ghostPathColorHex,
  type OverlayVisibility,
} from "./overlays.ts";
import type { Polygon, WorldGeometry } from "./world_schema.ts";

const COLORS = {
  background: 0x14181f,
  grid: 0x2a313d,
  robot: 0x4aa3ff,
  robotReduced: 0xffc247,
  robotStopped: 0xff5a5a,
  human: 0xf08a3c,
  lidarShadowFill: 0x5c6bc0,
  lidarShadowEdge: 0x9fa8da,
};

export class Scene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -100, 100);
  private readonly controls: OrbitControls;
  private readonly worldGroup = new THREE.Group();
  private readonly shadowGroup = new THREE.Group();
  private readonly envelopeGroup = new THREE.Group();
  private readonly ghostGroup = new THREE.Group();
  private readonly robotGroup = new THREE.Group();
  private readonly humanGroup = new THREE.Group();
  private world: WorldGeometry | null = null;
  private overlayVisibility: OverlayVisibility = DEFAULT_OVERLAY_VISIBILITY;
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
    this.scene.add(
      this.worldGroup,
      this.shadowGroup,
      this.envelopeGroup,
      this.ghostGroup,
      this.robotGroup,
      this.humanGroup,
    );
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

  /** Draw only simulator-exported static polygons. */
  setWorld(world: WorldGeometry | null): void {
    this.world = world;
    this.disposeGroup(this.worldGroup);
    if (world === null) {
      this.renderer.render(this.scene, this.camera);
      return;
    }
    const [x0, y0, x1, y1] = world.bounds;
    this.staticPolygon([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], 0.025, 0x293641, -0.05);
    world.walls.forEach((shape) => this.staticPolygon(shape, 1.1, 0x637581));
    world.racks.forEach((shape) => this.staticPolygon(shape, 1.6, 0x61717d));
    const zoneColors: Record<string, number> = {
      station: 0x786143,
      depot: 0x435c82,
      blind_corner: 0x7e4d42,
      one_lane_aisle: 0x355b7c,
      transit: 0x28444d,
      aisle: 0x31525a,
    };
    world.zones.forEach((zone) =>
      this.staticPolygon(zone.polygon, 0.012, zoneColors[zone.kind] ?? 0x31525a, 0, 0.16),
    );
    this.renderer.render(this.scene, this.camera);
  }

  /** Toggle visibility of simulator-supplied overlay groups. */
  setOverlayVisibility(visibility: OverlayVisibility): void {
    this.overlayVisibility = visibility;
    this.envelopeGroup.visible = visibility.envelopes;
    this.shadowGroup.visible = visibility.shadows;
    this.ghostGroup.visible = visibility.ghosts;
    this.renderer.render(this.scene, this.camera);
  }

  private staticPolygon(points: Polygon, height: number, color: number, z = 0, opacity = 1): void {
    const shape = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y)));
    const mesh = new THREE.Mesh(
      new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false }),
      new THREE.MeshBasicMaterial({
        color,
        opacity,
        transparent: opacity < 1,
        depthWrite: opacity === 1,
      }),
    );
    mesh.position.z = z;
    this.worldGroup.add(mesh);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry),
      new THREE.LineBasicMaterial({ color: 0x17252d, transparent: true, opacity: 0.65 }),
    );
    mesh.add(edges);
  }

  /** Frame the camera on the extent of every recorded robot and human position. */
  fit(frames: readonly Frame[], includeWorld = true): void {
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
    if (this.world !== null && includeWorld) {
      [minX, minY, maxX, maxY] = this.world.bounds;
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
    this.drawOverlays(frame);
    this.renderer.render(this.scene, this.camera);
  }

  private drawOverlays(frame: Frame): void {
    this.disposeGroup(this.envelopeGroup);
    this.disposeGroup(this.shadowGroup);
    this.disposeGroup(this.ghostGroup);
    this.envelopeGroup.visible = this.overlayVisibility.envelopes;
    this.shadowGroup.visible = this.overlayVisibility.shadows;
    this.ghostGroup.visible = this.overlayVisibility.ghosts;

    const robotModes = new Map(frame.robots.map((robot) => [robot.id, robot.mode]));
    for (const env of frame.overlays.envelopes ?? []) {
      const color = envelopeColorHex(robotModes.get(env.robot_id) ?? null);
      this.overlayPolygon(this.envelopeGroup, env.polygon, color, color, 0.24, 0.9, 0.02);
    }
    for (const sh of frame.overlays.lidar_shadows ?? []) {
      this.overlayPolygon(
        this.shadowGroup,
        sh.polygon,
        COLORS.lidarShadowFill,
        COLORS.lidarShadowEdge,
        0.28,
        0.75,
        0.015,
      );
    }
    for (const gp of frame.overlays.ghost_paths ?? []) {
      const color = ghostPathColorHex(gp.passed);
      this.ghostPolyline(this.ghostGroup, gp.points, color, 0.03);
    }
  }

  private overlayPolygon(
    target: THREE.Group,
    points: readonly OverlayPoint[],
    fillColor: number,
    edgeColor: number,
    fillOpacity: number,
    edgeOpacity: number,
    z: number,
  ): void {
    const shape = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y)));
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshBasicMaterial({
        color: fillColor,
        transparent: true,
        opacity: fillOpacity,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    mesh.position.z = z;
    target.add(mesh);

    const loopVectors = points.map(([x, y]) => new THREE.Vector3(x, y, z + 0.002));
    const outline = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(loopVectors),
      new THREE.LineBasicMaterial({ color: edgeColor, transparent: true, opacity: edgeOpacity }),
    );
    target.add(outline);
  }

  private ghostPolyline(
    target: THREE.Group,
    points: readonly OverlayPoint[],
    color: number,
    z: number,
  ): void {
    const vectors = points.map(([x, y]) => new THREE.Vector3(x, y, z));
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(vectors),
      new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9 }),
    );
    target.add(line);
    const tip = points[points.length - 1];
    if (tip !== undefined) {
      const marker = new THREE.Mesh(
        new THREE.RingGeometry(0.12, 0.22, 16),
        new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }),
      );
      marker.position.set(tip[0], tip[1], z + 0.002);
      target.add(marker);
    }
  }

  private disposeGroup(group: THREE.Group): void {
    group.traverse((node) => {
      if (
        node instanceof THREE.Mesh ||
        node instanceof THREE.Line ||
        node instanceof THREE.LineSegments ||
        node instanceof THREE.LineLoop
      ) {
        node.geometry.dispose();
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        materials.forEach((material) => material.dispose());
      }
    });
    group.clear();
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
