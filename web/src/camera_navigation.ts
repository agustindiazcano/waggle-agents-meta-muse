/** Translate a camera and its target together without changing the view angle. */
export function recenterCamera(
  camera: { x: number; y: number; z: number },
  target: { x: number; y: number; z: number },
  next: { x: number; y: number; z: number },
): { x: number; y: number; z: number } {
  return {
    x: camera.x + next.x - target.x,
    y: camera.y + next.y - target.y,
    z: camera.z + next.z - target.z,
  };
}
