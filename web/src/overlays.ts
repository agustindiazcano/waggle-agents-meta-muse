// Pure helpers for formatting and toggling simulator-supplied safety overlays
// (docs/MULTIMODAL_AND_VIEWER_DESIGN.md section 10). No geometry is invented here.

import type { FrameOverlays, Mode } from "./frame_schema.ts";

export type OverlayLayer = "envelopes" | "shadows" | "ghosts";

export interface OverlayVisibility {
  readonly envelopes: boolean;
  readonly shadows: boolean;
  readonly ghosts: boolean;
}

export const DEFAULT_OVERLAY_VISIBILITY: OverlayVisibility = {
  envelopes: true,
  shadows: true,
  ghosts: true,
};

export interface OverlaySummary {
  readonly envelopesLabel: string;
  readonly shadowsLabel: string;
  readonly ghostsLabel: string;
}

export function toggleOverlayLayer(
  current: OverlayVisibility,
  layer: OverlayLayer,
): OverlayVisibility {
  return {
    ...current,
    [layer]: !current[layer],
  };
}

export function envelopeColorHex(mode: Mode | null): number {
  if (mode === "stopped") return 0xff5a5a;
  if (mode === "reduced") return 0xffc247;
  return 0x4aa3ff;
}

export function ghostPathColorHex(passed: boolean): number {
  return passed ? 0x4be39a : 0xff6b6b;
}

export function describeOverlays(overlays: FrameOverlays): OverlaySummary {
  const envelopes = overlays.envelopes ?? [];
  const shadows = overlays.lidar_shadows ?? [];
  const ghosts = overlays.ghost_paths ?? [];

  let envelopesLabel = "Safety envelopes: not provided";
  if (envelopes.length > 0) {
    const first = envelopes[0]!;
    const minMargin = Math.min(...envelopes.map((e) => e.margin_m));
    const nearest = first.nearest_id ?? "none";
    const noun = envelopes.length === 1 ? "envelope" : "envelopes";
    envelopesLabel = `Safety envelopes: ${envelopes.length} ${noun} (margin ${minMargin.toFixed(2)} m, nearest ${nearest})`;
  }

  let shadowsLabel = "Lidar shadows: not provided";
  if (shadows.length > 0) {
    const stride = shadows[0]!.sample_stride;
    const noun = shadows.length === 1 ? "shadow" : "shadows";
    shadowsLabel = `Lidar shadows: ${shadows.length} ${noun} (downsampled stride ${stride})`;
  }

  let ghostsLabel = "Rollout ghosts: not provided";
  if (ghosts.length > 0) {
    const passCount = ghosts.filter((g) => g.passed).length;
    const failCount = ghosts.length - passCount;
    const first = ghosts[0]!;
    ghostsLabel = `Rollout ghosts: ${ghosts.length} paths (${passCount} pass, ${failCount} fail | K=${first.k}, H=${first.horizon_s.toFixed(1)}s)`;
  }

  return { envelopesLabel, shadowsLabel, ghostsLabel };
}
