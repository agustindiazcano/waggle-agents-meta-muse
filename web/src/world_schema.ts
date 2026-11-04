// Static geometry exported by waggle.sim.frame.export_world, never authored by the viewer.
export type Point = [number, number];
export type Polygon = Point[];
export interface WorldGeometry {
  schema_version: 1;
  name: string;
  bounds: [number, number, number, number];
  walls: Polygon[];
  racks: Polygon[];
  zones: { id: string; kind: string; capacity: number | null; polygon: Polygon }[];
  hash: string;
}

function object(value: unknown, fields: string[]): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("world must be an object");
  }
  const result = value as Record<string, unknown>;
  if (Object.keys(result).length !== fields.length || fields.some((key) => !(key in result))) {
    throw new Error("invalid world field");
  }
  return result;
}

function text(value: unknown): string {
  if (typeof value !== "string" || value.length === 0 || value.length > 256) {
    throw new Error("invalid world text");
  }
  return value;
}

function list(value: unknown): unknown[] {
  if (!Array.isArray(value) || value.length > 10000) {
    throw new Error("invalid world list");
  }
  return value;
}

function polygon(value: unknown): Polygon {
  const points = list(value);
  if (points.length < 3) {
    throw new Error("invalid world polygon");
  }
  return points.map((point) => {
    const pair = list(point);
    if (
      pair.length !== 2 ||
      !pair.every((v) => typeof v === "number" && Number.isFinite(v))
    ) {
      throw new Error("invalid world polygon point");
    }
    return pair as Point;
  });
}

/** Validate an export_world sidecar and bind it to the replay's world hash. */
export function parseWorld(value: unknown, expectedHash: string): WorldGeometry {
  const obj = object(value, [
    "schema_version",
    "name",
    "bounds",
    "walls",
    "racks",
    "zones",
    "hash",
  ]);
  if (obj.schema_version !== 1) {
    throw new Error("unsupported world version");
  }
  if (obj.hash !== expectedHash || !/^[a-f0-9]{64}$/.test(String(obj.hash))) {
    throw new Error("world hash does not match replay");
  }
  const bounds = list(obj.bounds);
  if (
    bounds.length !== 4 ||
    !bounds.every((v) => typeof v === "number" && Number.isFinite(v)) ||
    Number(bounds[2]) <= Number(bounds[0]) ||
    Number(bounds[3]) <= Number(bounds[1])
  ) {
    throw new Error("invalid world bounds");
  }
  return {
    schema_version: 1,
    name: text(obj.name),
    bounds: bounds as WorldGeometry["bounds"],
    walls: list(obj.walls).map(polygon),
    racks: list(obj.racks).map(polygon),
    zones: list(obj.zones).map((entry) => {
      const zone = object(entry, ["id", "kind", "capacity", "polygon"]);
      if (
        zone.capacity !== null &&
        (!Number.isInteger(zone.capacity) || Number(zone.capacity) < 1)
      ) {
        throw new Error("invalid world zone capacity");
      }
      return {
        id: text(zone.id),
        kind: text(zone.kind),
        capacity: zone.capacity === null ? null : Number(zone.capacity),
        polygon: polygon(zone.polygon),
      };
    }),
    hash: String(obj.hash),
  };
}
