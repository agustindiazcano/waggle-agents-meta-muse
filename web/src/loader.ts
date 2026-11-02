// Turns a file, blob or text into either a validated replay or an error message for the page.

import { ReplayError, parseReplay } from "./frame_schema.ts";
import type { Replay } from "./frame_schema.ts";

export const MAX_FILE_BYTES = 128 * 1024 * 1024;

export type LoadResult = { ok: true; replay: Replay } | { ok: false; error: string };

export function loadReplayText(text: string): LoadResult {
  try {
    return { ok: true, replay: parseReplay(text) };
  } catch (error) {
    if (error instanceof ReplayError) {
      return { ok: false, error: error.message };
    }
    return { ok: false, error: "the file could not be read as a replay" };
  }
}

export async function loadReplayBlob(blob: Blob): Promise<LoadResult> {
  if (blob.size > MAX_FILE_BYTES) {
    return { ok: false, error: "the file is over the size cap" };
  }
  let text: string;
  try {
    text = await blob.text();
  } catch {
    return { ok: false, error: "the file could not be read" };
  }
  return loadReplayText(text);
}
