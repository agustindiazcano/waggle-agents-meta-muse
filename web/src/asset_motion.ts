/** Animation choice from consecutive recorded positions, never a physical state. */
export type HumanAnimation = "Idle" | "Casual_Walk_inplace";

export interface HumanPosition {
  x: number;
  y: number;
  time: number;
}

/** Select a visual clip using only recorded position changes. */
export function animationForMotion(
  previous: HumanPosition | null,
  current: HumanPosition,
  prior: HumanAnimation,
): HumanAnimation {
  if (previous === null || current.time < previous.time) return "Idle";
  if (current.time === previous.time) return prior;
  return current.x !== previous.x || current.y !== previous.y ? "Casual_Walk_inplace" : "Idle";
}

/** Resolve a clip by name, preferring the requested worker idle. */
export function clipForAnimation(animation: HumanAnimation, names: readonly string[]): string | null {
  if (animation === "Idle" && names.includes("Idle_11")) return "Idle_11";
  return names.includes(animation) ? animation : null;
}
