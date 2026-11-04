/** An isolated visual gallery. It does not use or modify replay state. */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { galleryModels, modelById } from "./gallery_manifest.ts";
import { loadModel } from "./model_loader.ts";
import { makeRack } from "./rack_preview.ts";
import { PickupPreview } from "./pickup_preview.ts";
import { makeEquipment, disposeEquipment } from "./equipment_preview.ts";

/** Set up a gallery with a single on-demand model and its available clips. */
export function openGallery(
  container: HTMLElement,
  host: HTMLElement,
  selector: HTMLSelectElement,
  clips: HTMLSelectElement,
  status: HTMLElement,
  rackControls: HTMLElement,
  rackBays: HTMLInputElement,
  rackLevels: HTMLInputElement,
): void {
  for (const model of galleryModels) {
    const option = document.createElement("option");
    option.value = model.id;
    option.textContent = model.label;
    selector.append(option);
  }
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x14181f);
  scene.add(new THREE.AmbientLight(0xffffff, 2));
  const light = new THREE.DirectionalLight(0xffffff, 2);
  light.position.set(3, 5, 4);
  scene.add(light, new THREE.GridHelper(20, 20, 0x46535f, 0x303945));
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
  camera.position.set(3, 2.5, 4);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  host.append(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0.8, 0);
  controls.update();
  const loader = new GLTFLoader();
  const cache = new Map<string, GLTF>();
  const clock = new THREE.Clock();
  let current: GLTF | null = null;
  let mixer: THREE.AnimationMixer | null = null;
  let action: THREE.AnimationAction | null = null;
  let pickup: PickupPreview | null = null;
  let rack: THREE.Group | null = null;
  let generation = 0;

  function removeRack(): void {
    if (rack !== null) {
      scene.remove(rack);
      disposeEquipment(rack);
      rack = null;
    }
  }

  function showRack(): void {
    const bays = Number(rackBays.value);
    const levels = Number(rackLevels.value);
    let next: THREE.Group;
    try {
      next = makeRack(bays, levels);
    } catch (error) {
      if (!(error instanceof RangeError)) throw error;
      status.textContent = "Choose 1 to 10 bays and 1 to 6 levels.";
      return;
    }
    removeRack();
    rack = next;
    scene.add(rack);
    status.textContent = "Modular rack. Visual preview only.";
  }

  function setClip(): void {
    if (mixer === null || current === null) return;
    mixer.stopAllAction();
    action = null;
    const clip = THREE.AnimationClip.findByName(current.animations, clips.value);
    if (clip !== null) action = mixer.clipAction(clip).reset().play();
    pickup?.update(clips.value, 0, clip?.duration ?? 0);
  }

  async function show(id: string): Promise<void> {
    const request = ++generation;
    const model = modelById(id);
    mixer?.stopAllAction();
    if (current !== null) mixer?.uncacheRoot(current.scene);
    pickup?.dispose();
    pickup = null;
    action = null;
    if (current !== null) scene.remove(current.scene);
    removeRack();
    current = null;
    mixer = null;
    clips.replaceChildren();
    clips.disabled = true;
    rackControls.hidden = model?.id !== "modular-rack";
    if (model === null) {
      status.textContent = "Unknown model.";
      return;
    }
    if (model.file === null) {
      camera.position.set(8, 6, 11);
      controls.target.set(0, 1.5, 0);
      controls.update();
      if (model.id === "modular-rack") showRack();
      else {
        rack = makeEquipment(model.id);
        scene.add(rack);
        camera.position.set(5, 3.5, 6);
        controls.update();
        status.textContent = `${model.label}. Modular visual preview only.`;
      }
      return;
    }
    camera.position.set(3, 2.5, 4);
    controls.target.set(0, 0.8, 0);
    controls.update();
    status.textContent = `Loading ${model.label}...`;
    let loaded = cache.get(id) ?? null;
    if (loaded === null) {
      loaded = await loadModel(`/models/${model.file}`, (path) => loader.loadAsync(path));
      if (request !== generation) return;
      if (loaded === null) {
        status.textContent = `Model unavailable: ${model.file}`;
        return;
      }
      cache.set(id, loaded);
    }
    if (request !== generation) return;
    current = loaded;
    scene.add(loaded.scene);
    mixer = new THREE.AnimationMixer(loaded.scene);
    if (model.kind === "human") pickup = new PickupPreview(loaded.scene);
    for (const clip of loaded.animations) {
      const option = document.createElement("option");
      option.value = clip.name;
      option.textContent = clip.name;
      clips.append(option);
    }
    clips.disabled = loaded.animations.length === 0;
    if (loaded.animations.some((clip) => clip.name === "Idle_11")) clips.value = "Idle_11";
    setClip();
    status.textContent = `${model.label}. Visual preview only.`;
  }

  selector.addEventListener("change", () => { void show(selector.value); });
  clips.addEventListener("change", setClip);
  rackBays.addEventListener("input", showRack);
  rackLevels.addEventListener("input", showRack);
  function draw(): void {
    const elapsed = Math.min(clock.getDelta(), 0.1);
    if (!container.hidden) {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      if (renderer.domElement.width !== width || renderer.domElement.height !== height) {
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      }
      mixer?.update(elapsed);
      if (action !== null) pickup?.update(clips.value, action.time, action.getClip().duration);
      renderer.render(scene, camera);
    }
    requestAnimationFrame(draw);
  }
  void show(selector.value);
  requestAnimationFrame(draw);
}
