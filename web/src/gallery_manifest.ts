/** Generated models available for visual inspection, separate from replay state. */
export interface GalleryModel {
  id: string;
  label: string;
  file: string | null;
  kind: "robot" | "human" | "equipment";
}

export const galleryModels: readonly GalleryModel[] = [
  { id: "carrier", label: "Parcel carrier robot", file: "carrier_bot.glb", kind: "robot" },
  { id: "forklift", label: "Autonomous forklift", file: "heavy_forklift_bot.glb", kind: "robot" },
  { id: "parts", label: "Parts runner robot", file: "parts_runner_bot.glb", kind: "robot" },
  { id: "repair", label: "Technician support robot", file: "tech_repair_bot.glb", kind: "robot" },
  { id: "flat-carrier", label: "Flat platform robot", file: "flat_carrier_bot.glb", kind: "robot" },
  { id: "worker", label: "Warehouse worker (revised)", file: "worker_v2.glb", kind: "human" },
  { id: "worker-black", label: "Black warehouse worker", file: "worker_black.glb", kind: "human" },
  { id: "worker-asian-woman", label: "Asian woman warehouse worker", file: "worker_asian_woman.glb", kind: "human" },
  { id: "technician", label: "Maintenance technician", file: "human_technician_pickup.glb", kind: "human" },
  { id: "machine", label: "Industrial machine", file: "industrial_machine.glb", kind: "equipment" },
  { id: "tank", label: "Industrial tank (M-05)", file: "industrial_tank.glb", kind: "equipment" },
  { id: "press", label: "Industrial press (M-06)", file: "industrial_press.glb", kind: "equipment" },
  { id: "conveyor", label: "Roller conveyor", file: null, kind: "equipment" },
  { id: "rack", label: "Warehouse rack", file: "warehouse_rack.glb", kind: "equipment" },
  { id: "modular-rack", label: "Modular rack", file: null, kind: "equipment" },
  { id: "package", label: "Package", file: "package.glb", kind: "equipment" },
  { id: "truck", label: "Delivery truck", file: "delivery_truck.glb", kind: "equipment" },
  { id: "extinguisher", label: "Fire extinguisher", file: "fire_extinguisher.glb", kind: "equipment" },
  { id: "tree", label: "Tree", file: "tree.glb", kind: "equipment" },
  { id: "dock", label: "Loading dock", file: null, kind: "equipment" },
];

/** Return a known model or null for an unknown identifier. */
export function modelById(id: string): GalleryModel | null {
  return galleryModels.find((model) => model.id === id) ?? null;
}
