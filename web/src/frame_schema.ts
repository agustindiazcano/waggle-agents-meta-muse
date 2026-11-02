// Strict validation of the replay file contract (docs/MULTIMODAL_AND_VIEWER_DESIGN.md, part B).
// Mirrors src/waggle/sim/frame.py and src/waggle/replay/replay_format.py. Pure functions: no DOM,
// no I/O. The viewer reads values from a validated frame and never derives ground truth.

export const SCHEMA_VERSION = 1;
export const MAX_FRAME_BYTES = 262_144;
export const MAX_STRING = 64;

export type Mode = "normal" | "reduced" | "stopped";
export type EventKind = "stop" | "geofence" | "denial" | "ticket";

export interface Robot {
  id: string;
  x: number;
  y: number;
  heading: number;
  active: { speed: number; turn: number };
  speed_limit: number | null;
  mode: Mode | null;
}

export interface Human {
  id: string;
  x: number;
  y: number;
  heading: number;
}

export interface Zone {
  id: string;
  polygon_id: string;
  occupant: string | null;
  token: number | null;
}

export interface Machine {
  id: string;
  state: string;
  temperature: number;
  severity: number;
}

export interface FrameEvent {
  kind: EventKind;
  text: string;
}

export interface Frame {
  schema_version: number;
  tick: number;
  dt: number;
  sim_time: number;
  state_hash: string;
  run: { commit: string; seed: number; scenario_id: string; source: "live" | "replay" };
  robots: Robot[];
  humans: Human[];
  zones: Zone[];
  machines: Machine[];
  overlays: Record<string, never>;
  events: FrameEvent[];
}

export interface Header {
  type: "header";
  schema_version: number;
  commit: string;
  seed: number;
  scenario_id: string;
  dt: number;
  world_hash: string;
  frame_count: number;
  resimulable: boolean;
}

export interface Footer {
  type: "footer";
  final_state_hash: string;
  frames_digest: string;
}

export interface Replay {
  header: Header;
  frames: Frame[];
  footer: Footer;
}

export class ReplayError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReplayError";
  }
}

type Obj = Record<string, unknown>;

const MODES: readonly string[] = ["normal", "reduced", "stopped"];
const EVENT_KINDS: readonly string[] = ["stop", "geofence", "denial", "ticket"];
const HEADER_FIELDS = [
  "type",
  "schema_version",
  "commit",
  "seed",
  "scenario_id",
  "dt",
  "world_hash",
  "frame_count",
  "resimulable",
];
const FOOTER_FIELDS = ["type", "final_state_hash", "frames_digest"];
const TOP_FIELDS = [
  "schema_version",
  "tick",
  "dt",
  "sim_time",
  "state_hash",
  "run",
  "robots",
  "humans",
  "zones",
  "machines",
  "overlays",
  "events",
];
const RUN_FIELDS = ["commit", "seed", "scenario_id", "source"];
const ROBOT_FIELDS = ["id", "x", "y", "heading", "active", "speed_limit", "mode"];
const ACTIVE_FIELDS = ["speed", "turn"];
const HUMAN_FIELDS = ["id", "x", "y", "heading"];
const ZONE_FIELDS = ["id", "polygon_id", "occupant", "token"];
const MACHINE_FIELDS = ["id", "state", "temperature", "severity"];
const EVENT_FIELDS = ["kind", "text"];

function isObject(value: unknown): value is Obj {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exact(value: unknown, fields: readonly string[], what: string): Obj {
  if (!isObject(value)) {
    throw new ReplayError(`${what} must be an object`);
  }
  for (const key of Object.keys(value)) {
    if (!fields.includes(key)) {
      throw new ReplayError(`unknown field in ${what}: ${key}`);
    }
  }
  for (const key of fields) {
    if (!(key in value)) {
      throw new ReplayError(`missing field in ${what}: ${key}`);
    }
  }
  return value;
}

function num(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ReplayError(`${what} must be a finite number`);
  }
  return value;
}

function int(value: unknown, what: string, min: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < min) {
    throw new ReplayError(`${what} must be an integer of at least ${min}`);
  }
  return value;
}

function str(value: unknown, what: string): string {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_STRING) {
    throw new ReplayError(`${what} must be a non-empty string of at most ${MAX_STRING} characters`);
  }
  return value;
}

function digest(value: unknown, what: string): string {
  if (typeof value !== "string" || !/^[0-9a-f]{64}$/.test(value)) {
    throw new ReplayError(`${what} must be a SHA-256 hex digest`);
  }
  return value;
}

function list(value: unknown, what: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new ReplayError(`${what} must be a list`);
  }
  return value;
}

function utf8Length(text: string): number {
  return new TextEncoder().encode(text).length;
}

function parseJson(text: string, what: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    throw new ReplayError(`${what} is not valid JSON`);
  }
}

export function validateFrame(data: unknown): Frame {
  if (isObject(data) && data["schema_version"] !== SCHEMA_VERSION) {
    throw new ReplayError("unsupported schema version");
  }
  const top = exact(data, TOP_FIELDS, "frame");
  const run = exact(top["run"], RUN_FIELDS, "run");
  const source = run["source"];
  if (source !== "live" && source !== "replay") {
    throw new ReplayError("run.source must be live or replay");
  }
  const outRun: Frame["run"] = {
    commit: str(run["commit"], "run.commit"),
    seed: int(run["seed"], "run.seed", 0),
    scenario_id: str(run["scenario_id"], "run.scenario_id"),
    source,
  };
  const robots = list(top["robots"], "robots").map((item): Robot => {
    const r = exact(item, ROBOT_FIELDS, "robots");
    const active = exact(r["active"], ACTIVE_FIELDS, "robots.active");
    const limit = r["speed_limit"];
    const mode = r["mode"];
    if (mode !== null && (typeof mode !== "string" || !MODES.includes(mode))) {
      throw new ReplayError("robots.mode is unknown");
    }
    return {
      id: str(r["id"], "robots.id"),
      x: num(r["x"], "robots.x"),
      y: num(r["y"], "robots.y"),
      heading: num(r["heading"], "robots.heading"),
      active: { speed: num(active["speed"], "active.speed"), turn: num(active["turn"], "active.turn") },
      speed_limit: limit === null ? null : num(limit, "robots.speed_limit"),
      mode: mode as Mode | null,
    };
  });
  const humans = list(top["humans"], "humans").map((item): Human => {
    const h = exact(item, HUMAN_FIELDS, "humans");
    return {
      id: str(h["id"], "humans.id"),
      x: num(h["x"], "humans.x"),
      y: num(h["y"], "humans.y"),
      heading: num(h["heading"], "humans.heading"),
    };
  });
  const zones = list(top["zones"], "zones").map((item): Zone => {
    const z = exact(item, ZONE_FIELDS, "zones");
    const occupant = z["occupant"];
    const token = z["token"];
    return {
      id: str(z["id"], "zones.id"),
      polygon_id: str(z["polygon_id"], "zones.polygon_id"),
      occupant: occupant === null ? null : str(occupant, "zones.occupant"),
      token: token === null ? null : int(token, "zones.token", 0),
    };
  });
  const machines = list(top["machines"], "machines").map((item): Machine => {
    const m = exact(item, MACHINE_FIELDS, "machines");
    return {
      id: str(m["id"], "machines.id"),
      state: str(m["state"], "machines.state"),
      temperature: num(m["temperature"], "machines.temperature"),
      severity: int(m["severity"], "machines.severity", 0),
    };
  });
  const events = list(top["events"], "events").map((item): FrameEvent => {
    const e = exact(item, EVENT_FIELDS, "events");
    const kind = e["kind"];
    if (typeof kind !== "string" || !EVENT_KINDS.includes(kind)) {
      throw new ReplayError("events.kind is unknown");
    }
    return { kind: kind as EventKind, text: str(e["text"], "events.text") };
  });
  const overlays = top["overlays"];
  if (!isObject(overlays) || Object.keys(overlays).length !== 0) {
    throw new ReplayError("overlays must be empty: this viewer cannot draw overlays yet");
  }
  return {
    schema_version: SCHEMA_VERSION,
    tick: int(top["tick"], "tick", 0),
    dt: num(top["dt"], "dt"),
    sim_time: num(top["sim_time"], "sim_time"),
    state_hash: digest(top["state_hash"], "state_hash"),
    run: outRun,
    robots,
    humans,
    zones,
    machines,
    overlays: {},
    events,
  };
}

export function parseFrameLine(text: string, maxBytes: number = MAX_FRAME_BYTES): Frame {
  if (utf8Length(text) > maxBytes) {
    throw new ReplayError("frame is too large");
  }
  return validateFrame(parseJson(text, "frame"));
}

export function validateHeader(data: unknown): Header {
  if (isObject(data) && "schema_version" in data && data["schema_version"] !== SCHEMA_VERSION) {
    throw new ReplayError("unsupported schema version");
  }
  const h = exact(data, HEADER_FIELDS, "header");
  if (h["type"] !== "header") {
    throw new ReplayError("first line is not a header");
  }
  const dt = num(h["dt"], "header.dt");
  if (dt <= 0) {
    throw new ReplayError("header.dt must be positive");
  }
  if (typeof h["resimulable"] !== "boolean") {
    throw new ReplayError("header.resimulable must be a boolean");
  }
  return {
    type: "header",
    schema_version: SCHEMA_VERSION,
    commit: str(h["commit"], "header.commit"),
    seed: int(h["seed"], "header.seed", 0),
    scenario_id: str(h["scenario_id"], "header.scenario_id"),
    dt,
    world_hash: digest(h["world_hash"], "header.world_hash"),
    frame_count: int(h["frame_count"], "header.frame_count", 1),
    resimulable: h["resimulable"],
  };
}

export function validateFooter(data: unknown): Footer {
  const f = exact(data, FOOTER_FIELDS, "footer");
  if (f["type"] !== "footer") {
    throw new ReplayError("last line is not a footer");
  }
  return {
    type: "footer",
    final_state_hash: digest(f["final_state_hash"], "footer.final_state_hash"),
    frames_digest: digest(f["frames_digest"], "footer.frames_digest"),
  };
}

/** Parse and validate a whole replay file. Throws ReplayError on the first problem. */
export function parseReplay(text: string): Replay {
  const rows = text.split(/\r?\n/);
  while (rows.length > 0 && rows[rows.length - 1] === "") {
    rows.pop();
  }
  if (rows.length < 3) {
    throw new ReplayError("a replay needs a header, a frame and a footer");
  }
  if (rows.some((row) => utf8Length(row) > MAX_FRAME_BYTES)) {
    throw new ReplayError("a line is over the size cap");
  }
  const header = validateHeader(parseJson(rows[0] as string, "header"));
  const footer = validateFooter(parseJson(rows[rows.length - 1] as string, "footer"));
  const frameRows = rows.slice(1, -1);
  if (frameRows.length !== header.frame_count) {
    throw new ReplayError("frame_count does not match the number of frame lines");
  }
  const frames = frameRows.map((row) => parseFrameLine(row));
  let previous = -1;
  for (const f of frames) {
    if (f.tick <= previous) {
      throw new ReplayError("frame ticks must strictly increase");
    }
    previous = f.tick;
    if (
      f.run.commit !== header.commit ||
      f.run.seed !== header.seed ||
      f.run.scenario_id !== header.scenario_id
    ) {
      throw new ReplayError("frame run metadata does not match the header");
    }
  }
  const last = frames[frames.length - 1] as Frame;
  if (footer.final_state_hash !== last.state_hash) {
    throw new ReplayError("footer final_state_hash does not match the last frame");
  }
  return { header, frames, footer };
}
