/** Interactive 3D demo scene (?demo3d=1). Reuses the demo/index.html layout and the
 * deterministic state in demo3d_state.ts. Presentation only. */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { demoStateAt, WAREHOUSES, type DemoState } from "./demo3d_state.ts";
import { loadModel } from "./model_loader.ts";

const BASE_URL: string = (import.meta as unknown as { env: { BASE_URL: string } }).env.BASE_URL;
const mat = (c: number, r = 0.6): THREE.MeshStandardMaterial => new THREE.MeshStandardMaterial({ color: c, roughness: r });
function box(w: number, h: number, d: number, c: number, x = 0, y = 0, z = 0): THREE.Mesh {
  const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(c));
  o.position.set(x, y, z); o.castShadow = true; o.receiveShadow = true; return o;
}
function normalized(scene: THREE.Object3D, size: number): THREE.Group {
  let minX = Infinity; let minY = Infinity; let minZ = Infinity;
  let maxX = -Infinity; let maxY = -Infinity; let maxZ = -Infinity;
  scene.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (mesh.geometry) {
      mesh.geometry.computeBoundingBox();
      const bb = mesh.geometry.boundingBox;
      if (bb) {
        minX = Math.min(minX, bb.min.x); minY = Math.min(minY, bb.min.y); minZ = Math.min(minZ, bb.min.z);
        maxX = Math.max(maxX, bb.max.x); maxY = Math.max(maxY, bb.max.y); maxZ = Math.max(maxZ, bb.max.z);
      }
    }
  });
  const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 0.001);
  const s = size / span;
  scene.scale.setScalar(s);
  scene.position.set(-(minX + maxX) / 2 * s, -minY * s, -(minZ + maxZ) / 2 * s);
  const wrap = new THREE.Group(); wrap.add(scene); return wrap;
}

export class Demo3D {
  time = 8; playing = false;
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private robots = new Map<string, THREE.Group>();
  private heroRing!: THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial>;
  private pkg!: THREE.Mesh;
  private trucks: THREE.Group[] = [];
  private workers: (THREE.Group | null)[] = [null, null, null, null];
  private workerFallbacks: THREE.Group[] = [];
  private mixers: THREE.AnimationMixer[] = [];
  private clock = new THREE.Clock();
  private onState: (s: DemoState) => void;
  private onNotice: (msg: string) => void;

  constructor(host: HTMLElement, onState: (s: DemoState) => void, onNotice: (msg: string) => void) {
    this.onState = onState; this.onNotice = onNotice;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setSize(Math.max(1, host.clientWidth), Math.max(1, host.clientHeight));
    this.renderer.shadowMap.enabled = true;
    host.appendChild(this.renderer.domElement);
    this.scene.background = new THREE.Color(0x11161d);
    this.scene.fog = new THREE.Fog(0x11161d, 220, 520);
    this.camera = new THREE.PerspectiveCamera(50, Math.max(1, host.clientWidth) / Math.max(1, host.clientHeight), 0.1, 800);
    this.camera.position.set(0, 82, 108); this.camera.lookAt(0, 0, 0);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.scene.add(new THREE.AmbientLight(0xaabbcc, 1.5));
    const sun = new THREE.DirectionalLight(0xffffff, 2.4); sun.position.set(60, 90, 40); sun.castShadow = true; this.scene.add(sun);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(460, 300), mat(0x1a2027, 0.95));
    ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; this.scene.add(ground);
    for (const z of [-38, 38]) this.scene.add(box(360, 0.12, 14, 0x232a33, 0, 0.06, z));
    for (const x of [-95, 0, 95]) this.scene.add(box(14, 0.12, 90, 0x232a33, x, 0.06, 0));
    for (const w of WAREHOUSES) this.buildWarehouse(w.x);
    this.buildRobots(); this.buildTrucks();
    this.pkg = box(1.6, 1.1, 1.3, 0xc9a227); this.scene.add(this.pkg);
    for (let i = 0; i < 4; i++) {
      const fb = new THREE.Group();
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 1.8, 12), mat(0xe2574c, 0.8));
      body.position.y = 0.9; fb.add(body); fb.visible = false; this.scene.add(fb); this.workerFallbacks.push(fb);
    }
    void this.loadWorkers();
    void this.loadContainers();
    window.addEventListener("resize", () => {
      const w = Math.max(1, host.clientWidth); const h = Math.max(1, host.clientHeight);
      this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); this.renderer.setSize(w, h);
    });
    this.apply(demoStateAt(this.time));
    const loop = (): void => {
      const dt = Math.min(this.clock.getDelta(), 0.05);
      if (this.playing) { this.time = (this.time + dt) % 180; this.apply(demoStateAt(this.time)); }
      for (const m of this.mixers) m.update(dt);
      this.controls.update(); this.renderer.render(this.scene, this.camera);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  private buildWarehouse(wx: number): void {
    const g = new THREE.Group(); g.position.set(wx, 0, 0);
    g.add(box(56, 1, 40, 0x2e3947, 0, 0.5, 0));
    g.add(box(56, 4, 0.6, 0x3d4c5e, 0, 2, -20)); g.add(box(56, 4, 0.6, 0x3d4c5e, 0, 2, 20));
    g.add(box(0.6, 10, 40, 0x2e3947, -28, 5, 0)); g.add(box(0.6, 10, 40, 0x2e3947, 28, 5, 0));
    for (let i = -2; i <= 2; i++) for (const s of [-1, 1]) {
      g.add(box(20, 5, 2.4, 0x3a4756, s * 11, 2.5, -8 + ((i + 2) % 2) * 16));
      for (let k = 0; k < 4; k++) g.add(box(2.6, 1.6, 1.8, k % 2 ? 0xc9a227 : 0x7a8794, s * 11 + (k - 1.5) * 4.4, 3.6, -8 + ((i + 2) % 2) * 16));
    }
    g.add(box(18, 3, 6, 0x39434e, 0, 1.5, 23));
    this.scene.add(g);
  }
  private buildRobots(): void {
    for (const r of demoStateAt(0).robots) {
      const g = new THREE.Group(); g.scale.setScalar(1.45);
      g.add(box(2.2, 0.9, 1.5, r.organizer ? 0xffd34d : 0xd7dde3, 0, 0.65, 0));
      const top = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.5, 16), mat(0x222a33, 0.35));
      top.position.y = 1.35; g.add(top);
      if (r.hero) {
        this.heroRing = new THREE.Mesh(new THREE.TorusGeometry(2.6, 0.07, 8, 40), new THREE.MeshBasicMaterial({ color: 0x35d07f, transparent: true, opacity: 0 }));
        this.heroRing.rotation.x = Math.PI / 2; this.heroRing.position.y = 0.15; g.add(this.heroRing);
      }
      this.scene.add(g); this.robots.set(r.code, g);
    }
  }
  private buildTrucks(): void {
    // Procedural blue truck: the 71 MB GLB exceeds the 25 MB importer cap (see PENDING row 137).
    for (let i = 0; i < 3; i++) {
      const g = new THREE.Group();
      g.add(box(3, 2.4, 7, 0x3f6fb5, 0, 1.7, 0));
      g.add(box(2.8, 2, 3, 0xe8edf2, 0, 1.4, 5));
      this.scene.add(g); this.trucks.push(g);
    }
  }
  private async loadWorkers(): Promise<void> {
    const loader = new GLTFLoader();
    const base = `${BASE_URL}models/`;
    const spots: [number, number][] = [[-115, 18], [6, -12], [-14, 26], [16, -14]];
    for (let i = 0; i < 4; i++) {
      const file = `worker-${i + 1}.glb`;
      const gltf = await loadModel(file, (name) => loader.loadAsync(base + name), () => undefined);
      if (gltf === null) {
        const fb = this.workerFallbacks[i]; if (fb) { fb.visible = true; fb.position.set(spots[i]?.[0] ?? 0, 0, spots[i]?.[1] ?? 0); }
        this.onNotice(`GLB unavailable: ${file} - showing primitive fallback. Run: npm run models:sync -- --source ../demo/assets`);
        continue;
      }
      const m = normalized(gltf.scene, 1.8);
      m.position.set(spots[i]?.[0] ?? 0, 0, spots[i]?.[1] ?? 0);
      m.rotation.y = i === 1 ? 0 : Math.PI;
      this.scene.add(m); this.workers[i] = m;
      const clip = gltf.animations.find((a) => a.name === (i === 1 ? "Walking" : "Idle_11")) ?? gltf.animations[0];
      if (clip) { const mx = new THREE.AnimationMixer(m); mx.clipAction(clip).play(); this.mixers.push(mx); }
    }
  }
  private async loadContainers(): Promise<void> {
    const loader = new GLTFLoader();
    const base = `${BASE_URL}models/`;
    const gltf = await loadModel("Shipping_Container.glb", (name) => loader.loadAsync(base + name), () => undefined);
    if (gltf === null) {
      for (const w of WAREHOUSES) this.scene.add(box(12, 3, 3, 0x4c6a8a, w.x + 36, 1.5, 28));
      this.onNotice("GLB unavailable: Shipping_Container.glb - showing primitive fallback containers.");
      return;
    }
    const proto = normalized(gltf.scene, 12);
    for (const w of WAREHOUSES) { const m = proto.clone(true); m.rotation.y = Math.PI / 2; m.position.set(w.x + 36, 0, 28); this.scene.add(m); }
  }
  setTime(t: number): void { this.time = Math.max(0, Math.min(180, t)); this.apply(demoStateAt(this.time)); }
  private apply(s: DemoState): void {
    for (const r of s.robots) { const g = this.robots.get(r.code); if (g) { g.position.set(r.x, 1, r.z); g.rotation.y = r.heading; } }
    this.heroRing.material.opacity = s.time >= 35 && s.time < 65 ? 0.8 : 0;
    this.heroRing.material.color.set(s.hero.stopped ? 0xff5252 : 0x35d07f);
    this.pkg.visible = s.package.visible; this.pkg.position.set(s.package.x, 2.2, s.package.z);
    s.trucks.forEach((tr, i) => { const g = this.trucks[i]; if (g) { g.position.set(tr.x, 1, tr.z); g.rotation.y = Math.PI / 2; } });
    const w2 = this.workers[1]; const fb2 = this.workerFallbacks[1];
    if (w2) { w2.visible = s.worker2.visible; w2.position.set(s.worker2.x, 0, s.worker2.z); }
    else if (fb2) { fb2.visible = s.worker2.visible; fb2.position.set(s.worker2.x, 0, s.worker2.z); }
    this.onState(s);
  }
  focusGlobal(): void { this.camera.position.set(0, 82, 108); this.controls.target.set(0, 0, 0); }
  focusCell(cell: number): void { const wx = WAREHOUSES[cell]?.x ?? 0; this.camera.position.set(wx, 45, 60); this.controls.target.set(wx, 0, 0); }
  focusHero(): void { const s = demoStateAt(this.time); this.camera.position.set(s.hero.x + 18, 10, s.hero.z + 24); this.controls.target.set(s.hero.x, 1, s.hero.z); }
}

/** Draw both maps from the same DemoState as the 3D scene. */
export function drawDemoMaps(s: DemoState, mm: HTMLCanvasElement | null, cm: HTMLCanvasElement | null): void {
  if (mm) {
    const g = mm.getContext("2d"); if (g) {
      g.clearRect(0, 0, 300, 180); g.fillStyle = "#8fa3b5"; g.font = "11px Arial";
      g.fillText("GLOBAL MAP - live unit positions", 8, 14);
      WAREHOUSES.forEach((w, i) => { const x = 18 + i * 96; g.strokeStyle = "#3d4c5e"; g.strokeRect(x, 24, 84, 120); g.fillStyle = "#cfe0ee"; g.fillText(w.id, x + 4, 38); });
      for (const r of s.robots) {
        const x = 60 + (r.x + 140) / 280 * 190; const y = 34 + (r.z + 55) / 110 * 130;
        g.fillStyle = r.hero ? "#ffd34d" : r.organizer ? "#ffb84d" : "#7de2a8";
        g.beginPath(); g.arc(x, y, r.hero ? 4 : 2.5, 0, 7); g.fill();
        if (r.hero || r.organizer) { g.fillStyle = "#fff"; g.font = "9px Arial"; g.fillText(r.code, x + 5, y + 3); }
      }
      for (const tr of s.trucks) { const x = 60 + (tr.x + 140) / 280 * 190; g.fillStyle = "#6fb7ff"; g.fillRect(x - 4, tr.z < 0 ? 28 : 150, 8, 6); }
      g.fillStyle = "#ffd34d"; g.font = "10px Arial"; g.fillText(`${s.orderId}  ${s.package.id}  hero: R-B04`, 8, 168);
    }
  }
  if (cm) {
    const g = cm.getContext("2d"); if (g) {
      g.clearRect(0, 0, 300, 180); g.fillStyle = "#8fa3b5"; g.font = "11px Arial";
      g.fillText("WH-B MAP - unit codes and status", 8, 14);
      g.strokeStyle = "#3d4c5e"; g.strokeRect(14, 22, 272, 140);
      for (const r of s.robots.filter((r) => r.cell === 1)) {
        const x = 150 + r.x / 60 * 260; const y = 92 + r.z / 46 * 130;
        g.fillStyle = r.stopped ? "#ff5252" : r.hero ? "#ffd34d" : "#7de2a8";
        g.beginPath(); g.arc(x, y, r.hero ? 5 : 3.5, 0, 7); g.fill();
        g.fillStyle = "#fff"; g.font = "9px Arial"; g.fillText(r.code + (r.stopped ? " STOP" : ""), x + 6, y + 3);
      }
      if (s.worker2.visible) { g.fillStyle = "#e2574c"; g.beginPath(); g.arc(150 + s.worker2.x / 60 * 260, 92 + s.worker2.z / 46 * 130, 4, 0, 7); g.fill(); }
      g.fillStyle = "#c9a227"; g.fillRect(146, 86, 8, 8); g.fillStyle = "#fff"; g.font = "9px Arial"; g.fillText(s.package.id, 158, 94);
    }
  }
}
