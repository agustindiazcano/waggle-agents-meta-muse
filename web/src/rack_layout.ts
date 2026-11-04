/** Visual components for a configurable warehouse rack, not a physical design. */
export interface RackPart {
  kind: "upright" | "beam" | "shelf";
  position: [number, number, number];
  size: [number, number, number];
}

/** Build a visual rack layout from repeated components. */
export function rackLayout(bays: number, levels: number): RackPart[] {
  if (!Number.isInteger(bays) || bays < 1 || bays > 10 ||
      !Number.isInteger(levels) || levels < 1 || levels > 6) {
    throw new RangeError("rack needs 1 to 10 bays and 1 to 6 levels");
  }
  const parts: RackPart[] = [];
  const width = 2.4;
  const height = 0.8 * levels + 0.7;
  for (let boundary = 0; boundary <= bays; boundary++) {
    const x = (boundary - bays / 2) * width;
    for (const z of [-0.5, 0.5]) {
      parts.push({ kind: "upright", position: [x, height / 2, z], size: [0.1, height, 0.1] });
    }
  }
  for (let bay = 0; bay < bays; bay++) {
    const x = (bay - (bays - 1) / 2) * width;
    for (let level = 0; level < levels; level++) {
      const y = 0.82 + level * 0.8;
      parts.push({ kind: "shelf", position: [x, y, 0], size: [width, 0.06, 1] });
      for (const z of [-0.5, 0.5]) {
        parts.push({ kind: "beam", position: [x, y - 0.08, z], size: [width, 0.16, 0.08] });
      }
    }
  }
  return parts;
}
