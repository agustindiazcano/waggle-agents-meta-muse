/** Calculate the vertical half-span that contains recorded positions. */
export function fitHalf(width: number, height: number, aspect: number): number {
  return Math.max(width / aspect, height, 4) / 2 + 3;
}

/** Return camera-relative bounds; camera position supplies the world center. */
export function cameraBounds(half: number, aspect: number): {
  left: number; right: number; top: number; bottom: number;
} {
  return { left: -half * aspect, right: half * aspect, top: half, bottom: -half };
}
