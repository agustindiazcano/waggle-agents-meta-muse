/** Load an optional visual asset; a missing asset leaves the caller's fallback active. */
export async function loadModel<T>(
  name: string,
  load: (name: string) => Promise<T>,
  report: (name: string) => void = (failed) => console.warn(`Model unavailable: ${failed}`),
): Promise<T | null> {
  try {
    return await load(name);
  } catch {
    report(name);
    return null;
  }
}
