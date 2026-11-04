// Strict parser for incoming /ws/live messages emitted by waggle.api.sources and waggle.api.bridge.
// Pure functions: no DOM and no network calls here.

import { MAX_FRAME_BYTES, parseFrameLine, ReplayError, type Frame } from "./frame_schema.ts";
import { parseWorld, type WorldGeometry } from "./world_schema.ts";

export type LiveMessage =
  | { readonly kind: "world"; readonly world: WorldGeometry }
  | { readonly kind: "frame"; readonly frame: Frame }
  | { readonly kind: "error"; readonly code: string; readonly tick: number | null };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Parse one text message from /ws/live into a validated world, frame, or server error. */
export function parseLiveMessage(text: string, maxBytes: number = MAX_FRAME_BYTES): LiveMessage {
  if (new TextEncoder().encode(text).length > maxBytes) {
    throw new ReplayError("live message is too large");
  }
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new ReplayError("live message is not valid JSON");
  }
  if (!isRecord(raw)) {
    throw new ReplayError("live message must be an object");
  }
  if (raw["type"] === "world") {
    const { type: _ignored, ...rest } = raw;
    const hash = typeof rest["hash"] === "string" ? rest["hash"] : "";
    return {
      kind: "world",
      world: parseWorld(rest, hash),
    };
  }
  if (raw["type"] === "error") {
    const code = raw["error"];
    if (typeof code !== "string" || code.length === 0 || code.length > 64) {
      throw new ReplayError("invalid live error code");
    }
    const tickVal = raw["tick"];
    if (tickVal !== undefined && (!Number.isInteger(tickVal) || Number(tickVal) < 0)) {
      throw new ReplayError("invalid live error tick");
    }
    return {
      kind: "error",
      code,
      tick: tickVal === undefined ? null : Number(tickVal),
    };
  }
  return {
    kind: "frame",
    frame: parseFrameLine(text, maxBytes),
  };
}
