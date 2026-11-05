// Page wiring: file picker, ?demo=1, play, pause, scrub and the hash bar. All text is written
// with textContent. The state hash shown is the one the file records for the frame.

import type { Frame, Replay } from "./frame_schema.ts";
import { parseLiveMessage } from "./live_client.ts";
import { loadReplayBlob } from "./loader.ts";
import { focusTarget } from "./focus_target.ts";
import { openGallery } from "./gallery.ts";
import { advance, initialPlayer, seek, togglePlay } from "./player.ts";
import type { PlayerState } from "./player.ts";
import {
  DEFAULT_OVERLAY_VISIBILITY,
  describeOverlays,
  toggleOverlayLayer,
  type OverlayLayer,
  type OverlayVisibility,
} from "./overlays.ts";
import { Scene } from "./scene.ts";
import { Demo3D, drawDemoMaps } from "./demo3d.ts";
import { parseWorld } from "./world_schema.ts";

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (node === null) {
    throw new Error(`missing element ${id}`);
  }
  return node as T;
}

const errorBox = el<HTMLElement>("error");
const viewer = el<HTMLElement>("viewer");
const canvasHost = el<HTMLElement>("canvas");
const playButton = el<HTMLButtonElement>("play");
const slider = el<HTMLInputElement>("scrub");
const entitySelect = el<HTMLSelectElement>("entity");
const focusButton = el<HTMLButtonElement>("focus");
const fitButton = el<HTMLButtonElement>("fit");
const toggleEnvelopesButton = el<HTMLButtonElement>("toggle-envelopes");
const toggleShadowsButton = el<HTMLButtonElement>("toggle-shadows");
const toggleGhostsButton = el<HTMLButtonElement>("toggle-ghosts");
const hashValue = el<HTMLElement>("hash");
const tickValue = el<HTMLElement>("tick");
const metaValue = el<HTMLElement>("meta");
const worldStatus = el<HTMLElement>("world-status");
const overlayList = el<HTMLElement>("overlays");
const zoneList = el<HTMLElement>("zones");
const eventList = el<HTMLElement>("events");
const gallery = el<HTMLElement>("gallery");
const home = el<HTMLElement>("home");
let galleryInitialized = false;

let scene: Scene | null = null;
let replay: Replay | null = null;
let player: PlayerState = initialPlayer();
let overlayVisibility: OverlayVisibility = DEFAULT_OVERLAY_VISIBILITY;
let lastTime = 0;

function showError(message: string): void {
  replay = null;
  viewer.hidden = true;
  errorBox.hidden = false;
  errorBox.textContent = `Replay rejected: ${message}`;
}

function fillList(host: HTMLElement, rows: string[], empty: string): void {
  host.replaceChildren();
  for (const row of rows.length > 0 ? rows : [empty]) {
    const item = document.createElement("li");
    item.textContent = row;
    host.appendChild(item);
  }
}

function show(frame: Frame): void {
  const selected = entitySelect.value;
  const options = [
    ...frame.robots.map((entity) => ({ value: `robot:${entity.id}`, label: `Robot ${entity.id}` })),
    ...frame.humans.map((entity) => ({ value: `human:${entity.id}`, label: `Human ${entity.id}` })),
  ];
  entitySelect.replaceChildren(...options.map(({ value, label }) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  }));
  if (options.some((option) => option.value === selected)) entitySelect.value = selected;
  focusButton.disabled = options.length === 0;
  hashValue.textContent = frame.state_hash;
  tickValue.textContent = `tick ${frame.tick}, sim time ${frame.sim_time.toFixed(3)} s`;
  const summary = describeOverlays(frame.overlays);
  fillList(
    overlayList,
    [summary.envelopesLabel, summary.shadowsLabel, summary.ghostsLabel],
    "no overlays in this frame",
  );
  fillList(
    zoneList,
    frame.zones.map(
      (z) => `${z.id}: occupant ${z.occupant ?? "unknown"}, token ${z.token ?? "none"}`,
    ),
    "no zones in this frame",
  );
  fillList(
    eventList,
    frame.events.map((e) => `${e.kind}: ${e.text}`),
    "no events in this frame",
  );
  playButton.textContent = player.playing ? "Pause" : "Play";
  slider.value = String(player.index);
  scene?.draw(frame);
}

function current(): Frame | null {
  return replay === null ? null : (replay.frames[player.index] ?? null);
}

function render(): void {
  const frame = current();
  if (frame !== null) {
    show(frame);
  }
}

function frame_loop(now: number): void {
  const elapsed = lastTime === 0 ? 0 : now - lastTime;
  lastTime = now;
  if (replay !== null && player.playing) {
    const ticks = replay.frames.map((f) => f.tick);
    player = advance(player, elapsed, ticks, replay.header.dt);
    render();
  }
  requestAnimationFrame(frame_loop);
}

function open(next: Replay): void {
  home.hidden = true;
  gallery.hidden = true;
  errorBox.hidden = true;
  viewer.hidden = false;
  replay = next;
  player = initialPlayer();
  slider.max = String(next.frames.length - 1);
  metaValue.textContent =
    `scenario ${next.header.scenario_id}, seed ${next.header.seed}, commit ${next.header.commit}, ` +
    `${next.header.frame_count} frames, resimulable ${String(next.header.resimulable)}`;
  if (scene === null) {
    scene = new Scene(canvasHost);
  }
  scene.fit(next.frames);
  render();
}

async function openBlob(blob: Blob): Promise<void> {
  const result = await loadReplayBlob(blob);
  if (result.ok) {
    scene?.setWorld(null);
    worldStatus.textContent = "Map geometry: none loaded";
    open(result.replay);
  } else {
    showError(result.error);
  }
}

function flipOverlay(layer: OverlayLayer, button: HTMLButtonElement): void {
  overlayVisibility = toggleOverlayLayer(overlayVisibility, layer);
  button.setAttribute("aria-pressed", String(overlayVisibility[layer]));
  scene?.setOverlayVisibility(overlayVisibility);
}

toggleEnvelopesButton.addEventListener("click", () => {
  flipOverlay("envelopes", toggleEnvelopesButton);
});

toggleShadowsButton.addEventListener("click", () => {
  flipOverlay("shadows", toggleShadowsButton);
});

toggleGhostsButton.addEventListener("click", () => {
  flipOverlay("ghosts", toggleGhostsButton);
});

function showGallery(): void {
  if (player.playing) player = togglePlay(player);
  home.hidden = true;
  gallery.hidden = false;
  viewer.hidden = true;
  if (!galleryInitialized) {
    galleryInitialized = true;
    openGallery(
      gallery,
      el<HTMLElement>("gallery-canvas"),
      el<HTMLSelectElement>("gallery-model"),
      el<HTMLSelectElement>("gallery-clip"),
      el<HTMLElement>("gallery-status"),
      el<HTMLElement>("rack-controls"),
      el<HTMLInputElement>("rack-bays"),
      el<HTMLInputElement>("rack-levels"),
    );
  }
}

playButton.addEventListener("click", () => {
  if (replay === null) {
    return;
  }
  if (!player.playing && player.index >= replay.frames.length - 1) {
    player = seek(player, 0, replay.frames.length);
  }
  player = togglePlay(player);
  render();
});

slider.addEventListener("input", () => {
  if (replay === null) {
    return;
  }
  player = seek(player, Number(slider.value), replay.frames.length);
  render();
});

focusButton.addEventListener("click", () => {
  const frame = current();
  if (frame === null || scene === null) return;
  const separator = entitySelect.value.indexOf(":");
  const kind = entitySelect.value.slice(0, separator);
  if (kind !== "human" && kind !== "robot") return;
  const target = focusTarget(frame, kind, entitySelect.value.slice(separator + 1));
  if (target !== null) scene.focus(target.x, target.y);
});

fitButton.addEventListener("click", () => {
  if (replay !== null && scene !== null) scene.fit(replay.frames);
});

async function loadDemo(): Promise<void> {
  try {
    const response = await fetch("./demo.jsonl");
    if (!response.ok) {
      showError("the demo file could not be fetched");
      return;
    }
    await openBlob(await response.blob());
  } catch {
    showError("the demo file could not be fetched");
  }
}

function connectLive(scenarioId: string): void {
  home.hidden = true;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/ws/live?scenario=${encodeURIComponent(scenarioId)}`;
  const ws = new WebSocket(url);
  gallery.hidden = true;
  errorBox.hidden = true;
  viewer.hidden = false;
  if (scene === null) {
    scene = new Scene(canvasHost);
  }
  metaValue.textContent = `live scenario ${scenarioId}`;
  let fitted = false;
  ws.addEventListener("message", (ev) => {
    try {
      const msg = parseLiveMessage(String(ev.data));
      if (msg.kind === "world") {
        scene?.setWorld(msg.world);
        worldStatus.textContent = `Map geometry: ${msg.world.name}`;
      } else if (msg.kind === "frame") {
        if (!fitted) {
          scene?.fit([msg.frame]);
          fitted = true;
        }
        show(msg.frame);
      } else {
        showError(`live stream error: ${msg.code}`);
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : "invalid live message");
      ws.close();
    }
  });
  ws.addEventListener("error", () => {
    showError("live WebSocket connection failed");
  });
}

function openDemo3d(): void {
  home.hidden = true;
  gallery.hidden = true; viewer.hidden = true; errorBox.hidden = true;
  const host = el<HTMLElement>("demo3d");
  host.hidden = false;
  const hud = el<HTMLElement>("demo3d-hud"); const evBox = el<HTMLElement>("demo3d-event");
  const subs = el<HTMLElement>("demo3d-subs"); const timeLabel = el<HTMLElement>("demo3d-time");
  const notice = el<HTMLElement>("demo3d-notice"); const scrub = el<HTMLInputElement>("demo3d-scrub");
  const playBtn = el<HTMLButtonElement>("demo3d-play");
  const mm = document.getElementById("demo3d-minimap") as HTMLCanvasElement | null;
  const cm = document.getElementById("demo3d-cellmap") as HTMLCanvasElement | null;
  let demo: Demo3D | null = null;
  demo = new Demo3D(el<HTMLElement>("demo3d-canvas"), (s) => {
    hud.textContent = "";
    const b = document.createElement("b"); b.textContent = "WAGGLE HIVE";
    hud.append(b, document.createElement("br"), "Warehouses: 3  Robots: 30", document.createElement("br"),
      `Order ${s.orderId}  ${s.package.id}`, document.createElement("br"),
      `Delivered: ${s.counters.delivered}  In transit: ${s.counters.inTransit}  Delayed trucks: ${s.counters.delayedTrucks}`);
    evBox.textContent = `${s.event.tag}: ${s.event.text}`;
    subs.textContent = s.subtitle; subs.style.display = s.subtitle ? "block" : "none";
    timeLabel.textContent = `t=${s.time.toFixed(1)}s`;
    if (document.activeElement !== scrub) scrub.value = String(s.time);
    if (cm) cm.style.display = s.time >= 25 && s.time < 120 ? "block" : "none";
    drawDemoMaps(s, mm, cm);
    playBtn.textContent = demo?.playing ? "Pause" : "Play";
  }, (msg) => { notice.textContent = msg; });
  const wanted = new URLSearchParams(window.location.search).get("t");
  if (wanted !== null && Number.isFinite(Number(wanted))) demo.setTime(Number(wanted));
  playBtn.addEventListener("click", () => { if (demo) demo.playing = !demo.playing; });
  scrub.addEventListener("input", () => { demo?.setTime(Number(scrub.value)); });
  host.querySelectorAll<HTMLButtonElement>("[data-focus]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!demo) return;
      const f = btn.dataset.focus;
      if (f === "global") demo.focusGlobal();
      else if (f === "hero") demo.focusHero();
      else if (f === "WH-A") demo.focusCell(0);
      else if (f === "WH-B") demo.focusCell(1);
      else if (f === "WH-C") demo.focusCell(2);
    });
  });
}

const searchParams = new URLSearchParams(window.location.search);
const liveScenario = searchParams.get("live");
if (searchParams.get("demo3d") === "1") {
  openDemo3d();
} else if (liveScenario !== null && liveScenario.length > 0) {
  connectLive(liveScenario);
} else if (searchParams.get("demo") === "1") {
  void loadDemo();
} else if (searchParams.get("gallery") === "1") {
  showGallery();
}
requestAnimationFrame(frame_loop);
