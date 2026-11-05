/** Deterministic 180 s presentation state for the interactive demo. Presentation only:
 * not simulator ground truth, audit data or experiment results. Same math as demo/index.html. */
export const DURATION_S = 180;
export const ORDER_ID = "ORD-1042";
export const PACKAGE_ID = "PKG-8841";
export interface WarehouseDef { id: string; x: number; }
export const WAREHOUSES: readonly WarehouseDef[] = [
  { id: "WH-A", x: -95 }, { id: "WH-B", x: 0 }, { id: "WH-C", x: 95 },
];
export function robotCode(cell: number, idx: number): string {
  return `R-${"ABC"[cell] ?? "A"}${String(idx + 1).padStart(2, "0")}`;
}
export const ROBOT_CODES: readonly string[] = Array.from({ length: 30 }, (_, i) => robotCode(Math.floor(i / 10), i % 10));
export interface DemoRobot { code: string; cell: number; idx: number; organizer: boolean; hero: boolean; x: number; z: number; heading: number; stopped: boolean; }
export interface DemoTruck { id: string; x: number; z: number; delayed: boolean; }
export interface DemoState {
  time: number; robots: DemoRobot[]; hero: DemoRobot;
  package: { id: string; x: number; z: number; visible: boolean };
  worker2: { x: number; z: number; visible: boolean };
  trucks: DemoTruck[]; event: { tag: string; text: string }; subtitle: string;
  counters: { delivered: number; inTransit: number; delayedTrucks: number };
  orderId: string;
}
const clamp = (v: number, a: number, b: number): number => Math.max(a, Math.min(b, v));
const lerp = (a: number, b: number, s: number): number => a + (b - a) * s;
export const SUBTITLES: readonly (readonly [number, number, string])[] = [
  [0, 8, "Three warehouses. Thirty robots. One urgent order."],
  [8, 15, `${ORDER_ID}: transfer ${PACKAGE_ID} from WH-A to WH-C. Priority: urgent.`],
  [15, 25, "One global coordinator assigns the transfer to three cell organizers."],
  [25, 35, "Each organizer directs ten robots. Thirty advisors add caution; deterministic code decides."],
  [35, 48, `WH-B organizer assigns pickup. ${PACKAGE_ID} attaches to carrier R-B04.`],
  [48, 58, "A human crosses the aisle. The fast layer commands a stop. No model is in this loop."],
  [58, 65, "Clear. Motion resumes inside the allowed envelope."],
  [65, 78, "A package label tries to add an override instruction."],
  [78, 90, "Screening, strict schema and tool permissions reject it. The order is unchanged."],
  [90, 105, "Machine M-B2 reports overheating. Ticket, diagnosis and part reservation open."],
  [105, 120, "Simulated route variants are reviewed. One safe alternative is selected."],
  [120, 138, "Truck TRK-07 is delayed. The coordinator reassigns the transfer to TRK-12."],
  [138, 155, `${PACKAGE_ID} is loaded, moved and delivered. ${ORDER_ID} is complete.`],
  [155, 165, "Measured evidence, from committed result files. Development seeds only."],
  [165, 180, "Waggle Hive. Models propose. Deterministic code disposes."],
];
export const EVENTS: readonly (readonly [number, string, string])[] = [
  [0, "GLOBAL", `Order received: ${ORDER_ID} / ${PACKAGE_ID}`],
  [15, "COORDINATOR", "Assigns WH-A > WH-B > WH-C transfer"],
  [35, "ORGANIZER WH-B", "Pickup assigned to R-B04"],
  [48, "FAST LAYER", "Human in envelope: STOP (deterministic)"],
  [58, "FAST LAYER", "Envelope clear: resume"],
  [65, "GUARD", "Untrusted label input screened"],
  [78, "MCP BOUNDARY", "Override rejected: schema + allowlist"],
  [90, "MAINTENANCE", "M-B2 overheating: ticket T-331 opened"],
  [105, "COURT REVIEW", "Ghost routes checked; alternative selected"],
  [120, "COORDINATOR", "TRK-07 delayed: reassign to TRK-12"],
  [138, "DELIVERY", `${PACKAGE_ID} delivered; ${ORDER_ID} complete`],
];
/** Pure state at time t (clamped to [0, 180]); identical t always gives identical state. */
export function demoStateAt(rawT: number): DemoState {
  const t = clamp(rawT, 0, DURATION_S);
  const stopped = t >= 48 && t < 58;
  const robots: DemoRobot[] = [];
  for (let cell = 0; cell < 3; cell++) {
    for (let idx = 0; idx < 10; idx++) {
      const code = robotCode(cell, idx);
      const hero = code === "R-B04";
      const phase = idx * 0.7 + cell * 2;
      let x: number; let z: number; let heading: number;
      if (hero) {
        const hx = clamp((t - 35) / 20, 0, 1);
        x = stopped ? 3.6 : lerp(-16, 14, hx); z = -4; heading = Math.PI / 2;
      } else {
        const a = t * 0.25 + phase;
        const rad = idx === 0 ? 7 : 13 + (idx % 3) * 4;
        x = (WAREHOUSES[cell]?.x ?? 0) + Math.sin(a) * rad; z = Math.cos(a * 0.8) * 11; heading = a;
      }
      robots.push({ code, cell, idx, organizer: idx === 0, hero, x, z, heading, stopped: hero && stopped });
    }
  }
  const hero = robots.find((r) => r.hero) as DemoRobot;
  let pkg: DemoState["package"];
  if (t < 40) pkg = { id: PACKAGE_ID, x: hero.x, z: hero.z, visible: false };
  else if (t < 120) pkg = { id: PACKAGE_ID, x: hero.x, z: hero.z, visible: true };
  else if (t < 138) { const s = (t - 120) / 18; pkg = { id: PACKAGE_ID, x: lerp(0, 95, s), z: lerp(-38, -30, s), visible: true }; }
  else pkg = { id: PACKAGE_ID, x: 95, z: 14, visible: true };
  const cross = clamp((t - 42) / 16, 0, 1);
  const worker2 = { x: 6, z: lerp(-6, 1, cross), visible: t >= 42 && t < 62 };
  const trucks: DemoTruck[] = [0, 1, 2].map((i) => {
    const s = (t * 0.012 + i * 0.33) % 1;
    const delayed = i === 0 && t >= 120;
    return { id: i === 1 ? "TRK-12" : i === 0 ? "TRK-07" : "TRK-21", x: delayed ? -40 : lerp(-170, 170, s), z: i === 1 ? 38 : -38, delayed };
  });
  let event = { tag: EVENTS[0]?.[1] ?? "", text: EVENTS[0]?.[2] ?? "" };
  for (const [at, tag, text] of EVENTS) if (t >= at) event = { tag, text };
  let subtitle = "";
  for (const [a, b, text] of SUBTITLES) if (t >= a && t < b) subtitle = text;
  return {
    time: t, robots, hero, package: pkg, worker2, trucks, event, subtitle, orderId: ORDER_ID,
    counters: { delivered: t >= 138 ? 1 : 0, inTransit: t >= 15 && t < 138 ? 1 : 0, delayedTrucks: t >= 120 ? 1 : 0 },
  };
}
