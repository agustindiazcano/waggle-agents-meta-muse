/** A recorded position that the viewer can focus without changing simulator state. */
export interface FocusEntity { id: string; x: number; y: number }

/** Find an entity by its recorded kind and identifier. */
export function focusTarget(
  frame: { robots: readonly FocusEntity[]; humans: readonly FocusEntity[] },
  kind: "robot" | "human",
  id: string,
): { x: number; y: number } | null {
  const entity = (kind === "robot" ? frame.robots : frame.humans).find((item) => item.id === id);
  return entity === undefined ? null : { x: entity.x, y: entity.y };
}
