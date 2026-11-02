# Predictive maintenance and E6: design

Status: proposed, nothing is implemented. Covers PLAN.md Phase 6 and PENDING row 96 (predictive maintenance physics and predictor are the largest code gap named there). It orders existing scope and cuts none.

Not read: `docs/MULTI_WAREHOUSE_PLAN.md`, ADR bodies other than 020, 048, 049, 054, 056 and the ADR-050 line quoted in ADR text, the bodies of `src/waggle/db/*.py`, `src/waggle/sim/*.py` and `src/waggle/control/*.py` beyond file lists, signatures and `reflex.py` lines 35 to 57, `src/waggle/llm`, `src/waggle/governance`, any result JSON. `docs/CATALOG_COMPATIBILITY_DESIGN.md` is an open design PR; it is referenced, not repeated.

## What exists and what is missing

| Item | State | Source |
|---|---|---|
| Spare parts inventory, idempotent reservations | Implemented | ADR-048, `src/waggle/db/inventory.py` |
| Machines (ids only), tickets with deterministic id per failure event, dispatch (records a request), purchase orders only at zero stock | Implemented | ADR-049, `src/waggle/db/tickets.py`, `procurement.py` |
| Five maintenance tools; chassis `maintenance` may call `reserve_part`, `dispatch_tech`, `create_purchase_order`, `open_ticket`, `get_inventory`; `tech_repair` may call `open_ticket` | Implemented | `src/waggle/mcp_server/allowlist.py` |
| Provision script for catalog, machines, zones, identities (sample data only) | Implemented | ADR-056 |
| Telemetry threshold to hazard geofence (value against warn and critical, circle around the machine) | Implemented | `src/waggle/control/reflex.py`, ADR-027 |
| Machine-to-part compatibility, technician zone lease, ticket close, reservation release | Proposed | `docs/CATALOG_COMPATIBILITY_DESIGN.md`, PENDING rows 93, 95 |
| Machines in the simulator, degradation physics, hidden onset | Missing | `src/waggle/sim` has no machine module |
| Telemetry stream and its noise model | Missing | none |
| Predictor | Missing | `src/waggle/maintenance/__init__.py` is a docstring only |
| Loop from alert to ticket, reservation, order, dispatch | Missing | none |
| `failure_history`, `machine_telemetry` tables | Missing | named in ADR-020 and `docs/ARCHITECTURE.md`; absent from `src/waggle/db/schema.py` |
| E6 runner, result file, baseline | Missing | `docs/EXPERIMENTS.md` E6 |
| Manual sheet extraction, RAG over manuals | Missing | PLAN.md Phase 6 |

Document conflict, stated and not expanded: PLAN.md says the predictor is a "first-order thermal model fit online", while AGENTS.md 9.8 forbids the simulator and predictor sharing equations. A first-order thermal model is also the simplest choice for the simulator. This design resolves it by giving the simulator a different family (section 2) and keeps the first-order model as the predictor, as PLAN.md and ARCHITECTURE say. If the maintainer reads the documents otherwise, stop here and decide before building (decision D1).

## 1. Design principles

- Ground truth lives in the simulator (5.4). The predictor receives only a telemetry stream of numbers and a tick. It never sees the fault state, the onset tick or the wear value.
- The reflex threshold path (ADR-027) stays the safety floor and does not depend on the predictor. The predictor can only add earlier action. A blind predictor degrades to the threshold, never below it.
- The loop is deterministic code. An LLM never decides to stop, order or dispatch.

## 2. Degradation model (simulator side)

Failure modes per machine class. The mode names come from E6 ("for example"); the maintainer confirms them (D2).

| Mode | Hidden state | Observable effect | Failure criterion |
|---|---|---|---|
| Bearing wear | wear w in [0,1], grows after onset | vibration RMS rises, bearing temperature rises with load | w reaches 1 |
| Lubrication loss | lubricant level l falls after onset | friction heat: temperature rises, vibration rises late | l reaches 0 |
| Misalignment | offset step at onset | vibration at a fixed amplitude step, current rises, temperature rises slowly | offset times load passes a damage budget |

Wear trajectory options.

| Option | Description | Trade-offs |
|---|---|---|
| W1 Linear ramp after onset | w grows at a constant rate | Trivial; the predictor's linear extrapolation would match it, so it proves little |
| W2 Power law with stochastic rate (recommended) | dw/dt = k * load^a * w^b with a rate k drawn per machine per seed, plus a small rate noise term | Accelerating wear is realistic for bearings; the predictor's first-order model does not match it, so lead time is a real test |
| W3 Markov degradation states | discrete healthy, degraded, failing | Easy to explain; coarse, and hides the lead time metric |
| W4 Replay recorded real data | needs real machine logs | Not available; the maintainer would have to supply it |

Recommendation: W2. Thermal state in the simulator is a two-node model (housing and bearing) with load-dependent heat input, so it is a different family from the predictor's one-node model. Parameters live in `data/sim/degradation.json` (simulator only).

Seeds and stochastic parts: one stream per machine from `make_streams(root_seed, "degradation", n)` (`src/waggle/sim/streams.py`). Onset tick, rate k, load profile and mode are drawn from that stream only. No wall clock, no global random (5.5). Healthy machines (no onset in the horizon) are drawn too, so false alarms can be measured. The load profile is a bounded function of tasks served, so degradation interacts with the warehouse and not only with time.

## 3. Telemetry and noise

| Option | Description | Trade-offs |
|---|---|---|
| T1 Ideal readings | no noise | Hides every false alarm; invalid for E6 |
| T2 Gaussian noise per channel at 1 Hz (recommended start) | temperature, vibration RMS, current, with a per-machine bias drawn at start | Simple, reproducible; noise is not heavy tailed |
| T3 Add drift, dropouts and stuck-at faults | sensor faults as in scenario families S19 to S36 | Needed for the sensor fault families; build after T2 works |

Recommendation: T2 first, T3 as a second branch. Channels follow ARCHITECTURE (temperature, vibration, hydraulic pressure, current); pressure is added only for a mode that uses it. Telemetry is numeric only. Any text field a machine reports (a label, an error string) is untrusted and goes through the guard (8.6); the first version has none.

## 4. Predictor (maintenance side)

| Option | Description | Trade-offs |
|---|---|---|
| P0 Fixed thresholds on temperature and vibration | the E6 baseline | No lead time beyond the limit crossing; fails on loaded versus idle readings |
| P1 Load-corrected residual plus CUSUM on each channel (recommended first alert stage) | residual to a rolling healthy baseline per machine, cumulative sum raises a flag | Few parameters, no fit, explainable, cheap to test |
| P2 First-order thermal model fit online, extrapolated to the limit (recommended second stage) | T' = (T_eq(load) - T) / tau, fit by recursive least squares; time to limit from the fitted curve | In PLAN.md and ARCHITECTURE; gives a lead time estimate. Misspecified for accelerating wear, which is the point of the circularity check |
| P3 Kalman or particle filter with a wear state | latent state estimate | Heavier; justified only if P1 and P2 together miss failures or give lead time errors that make dispatch late |
| P4 Learned classifier or sequence model | trained on a failure log | Opaque component to monitor; AGENTS.md 12.11 forbids it without evidence; needs a large failure log |

Recommendation: P1 raises the flag, P2 estimates time to limit for the alert level. P3 is built only if development seeds show P1 plus P2 miss more than the baseline or estimate time to limit with an error larger than the dispatch lead time. P4 is not planned.

Separation of simulator and predictor (9.8), with enforcement:

| Mechanism | Test |
|---|---|
| Different families: two-node thermal plus power law wear (simulator) versus one-node thermal plus CUSUM (predictor) | review in the ADR; no equation is reused |
| Parameters in separate files: `data/sim/degradation.json` and `data/maintenance/predictor.json` | a test loads both and asserts the key sets and values do not overlap |
| Import contract: `waggle.maintenance.predictor` imports nothing from `waggle.sim`; `waggle.sim` imports nothing from `waggle.maintenance` (already in AGENTS.md 5.8) | import-linter contract plus an AST test on the predictor module |
| Predictor tuning uses a synthetic failure log generated separately (ADR-020), not the simulator | the log generator lives in `experiments/`, not in `waggle.sim` |
| The predictor input type has only `(machine_id, tick, channel values)` | a type test: the input dataclass has no field for fault state |

## 5. Alert policy

Severity levels (PLAN.md): warning logs and slows nearby robots; critical sets a geofence and opens a ticket; emergency stops and alarms. All actions are deterministic.

| Option | Trigger | Trade-offs |
|---|---|---|
| A1 Threshold only | value crosses warn or critical | The baseline. Zero lead time by construction |
| A2 Estimated time to limit under a lead-time target | P2 estimate below L_target with P1 flag on | Gives lead time; a false alarm costs a ticket and a part reservation |
| A3 A2 with a persistence rule | flag on for N consecutive windows | Fewer false alarms, later detection; N is a tuned parameter, tuned on development seeds only |

Recommendation: A3. Cost model, so the threshold is a stated trade-off and not a guess: a false alarm costs one ticket, one reservation and one technician visit; a missed failure costs downtime plus the hazard exposure of robots near the machine. The cost weights are the maintainer's input (D3). Until then the experiment reports counts of each and does not collapse them into one score. L_target must exceed the technician response time (dispatch plus travel), a number the maintainer supplies (D3).

## 6. The loop

| Step | Actor and identity | Existing tool or new code | Notes |
|---|---|---|---|
| 1 Telemetry read | simulator or machine gateway | new: `waggle.maintenance.monitor` | numbers only |
| 2 Predict | deterministic code | new: `waggle.maintenance.predictor` | no LLM |
| 3 Severity action | control path | `reflex.telemetry_geofences` | emergency and critical act here, not through the loop |
| 4 Open ticket | `maintenance` chassis | `open_ticket` | key `failure:<machine>:<onset_estimate_bucket>`; one event, one ticket (T9) |
| 5 Choose part | deterministic lookup in the manual sheet | new: `waggle.maintenance.sheet` | part number must exist in the catalog; with the compatibility design, a ticket-bound check also applies |
| 6 Reserve | `maintenance` | `reserve_part` | idempotent by key |
| 7 Order if no stock | `maintenance` | `create_purchase_order` | only at zero stock (ADR-049) |
| 8 Dispatch | `maintenance` | `dispatch_tech` | records a request; the zone lease is the compatibility design Part B |
| 9 Parts runner | `parts_runner` | `move_waypoint`, `get_task` | delivery to a safe point; needs the package model (PENDING row 92) |

The failure event key must be stable across ticks: a re-estimated onset must not create a second ticket. Proposal: the key is the machine id plus the tick of the first critical flag, frozen when first raised. The tool identities are the existing authenticated ones; the loop holds no authority of its own (8.1). A new MCP tool is not needed. Whether the loop's identity needs a `maintenance` token provisioned for the sim is a provision-script item (ADR-056).

LLM use.

| Where | Allowed | Conditions |
|---|---|---|
| Extract a manual into a structured sheet, once per machine | Yes, advisory | Manual text is untrusted, passes the guard and sanitizers; output validated against a strict schema; reviewed by the maintainer before it is trusted; a missing sheet means conservative default limits |
| Draft ticket text | Yes | Stored bounded and printable only (ADR-049); never read back into a decision |
| Diagnosis among failure modes using the failure history | Yes, advisory | Proposes a mode; the part number it names is checked against the catalog in code (8.7); disagreement with the sheet escalates |
| Decide severity, stop, geofence, order, dispatch | No | 5.1 |
| Widen what a chassis may call | No | 8.2 |

## 7. Evaluation protocol for E6

Configurations, same seeds, layer disabled for the baseline (9.3).

| Config | Content |
|---|---|
| B0 Reactive | no predictor; reflex thresholds only; ticket opened when the critical limit is crossed |
| B1 Threshold plus loop | A1 alert policy feeding the full loop |
| C1 P1 only | CUSUM flag, A3 |
| C2 P1 plus P2 | recommended design |
| C3 Without manual sheet | conservative default part and limits, to measure the sheet's contribution by ablation, not by summing blocks |

Each failure mode and machine, with its target layer (predictor, loop, catalog check), is declared before the run (9.4).

Metrics.

| Metric | Definition |
|---|---|
| Time to detection | first alert tick minus true onset tick (known to the scorer only) |
| Lead time | failure tick minus first actionable alert tick (ticket opened) |
| False alarms | tickets on healthy machines, per 100 machine-hours, with raw counts |
| Missed failures | failures with no ticket before the failure tick; a predictor blind to a failure is reported as missed, never as detected by the threshold fallback |
| Wrong part orders | orders or reservations for a part that does not fit the failing mode and machine, scored from the ground truth table |
| Duplicate tickets or orders per event | expected 0 (T9, T16) |
| Robots stopped before entering the hazard zone | robots whose geofence stop came before their first entry, over robots that reached the zone |
| Downtime | ticks from failure to repaired state, versus B0 |

Statistics and splits: Wilson 95% intervals on every proportion with raw counts (9.5); small samples called small; failing seeds listed. Development seeds are used for building and for tuning N and L_target. Held-out seeds run once per configuration, in the cloud, and the maintainer commits the result (9.1, 9.10). Repeats of LLM steps (sheet extraction, diagnosis) are reported as repeats (9.7). Result file fields: commit, seed set, config, model ids and prompt versions where an LLM step ran, date, per-seed rows (machine, mode, onset tick, failure tick, alert tick, ticket id, part, order id), counts, intervals, failing seeds. Latency is reported as code latency (9.9). With one machine as PLAN.md says, a seed is one machine; the sample is the number of seeds, so intervals will be wide. The number of seeds and machines is a maintainer decision (D4).

## 8. Invariants and failure-path tests, written first

| Test | Asserts |
|---|---|
| Planted failure detected | a fixed-seed machine with a known onset and rate produces a ticket before the failure tick |
| Blind predictor reported as missed | a predictor stub that never alerts leaves the failure with no ticket, and the scorer counts it as missed |
| No shared parameters | key sets and values of the two parameter files do not overlap |
| Predictor imports nothing from sim | AST test plus import-linter |
| Determinism | same seed gives identical telemetry and identical alerts; different seed differs |
| Healthy machine | no ticket over the horizon for a set of seeds, or the false alarms are counted |
| Idempotent event | the same alert twice opens one ticket, one reservation, one order |
| Re-estimated onset | a shifted onset estimate keeps the frozen event key |
| Wrong part | a sheet naming a non-catalog part is rejected before any tool call; an existing incompatible part is blocked once the compatibility design lands, and until then the E6 runner reports it as a wrong part order |
| Poisoned manual | text naming an injected part number or a tool call changes no decision and no authority |
| Telemetry missing or NaN | treated as unscorable: the loop holds the conservative severity and logs, it does not return a silent pass (11.2) |
| Fail direction | reflex and catalog checks fail closed; tracing and optional retrieval fail open and never block the control path |
| Dispatch before part | no technician dispatch for a ticket without a reservation or an order (to be confirmed with the maintainer, D5) |

## 9. Build order, stacked branches

Names are proposals. Local runs are unit tests only; sweeps and the E6 runs go to a `workflow_dispatch` workflow in the cloud (section 3 of AGENTS.md).

| # | Branch | Content | Depends on | Where | Migration |
|---|---|---|---|---|---|
| 1 | `docs/predictive-maintenance-design` | this document | none | local | no |
| 2 | `feat/sim-machine-degradation` | machine module, W2, two-node thermal, parameter file, streams, determinism and onset tests | maintainer data D2 | local | no |
| 3 | `feat/sim-machine-telemetry` | T2 noise, telemetry stream type | 2 | local | no |
| 4 | `feat/maintenance-predictor` | P1 and P2, parameter file, separation tests, planted and blind tests | 3 | local | no |
| 5 | `feat/maintenance-alert-loop` | severity, A3, frozen event key, loop through existing tools over fakes | 4, compatibility design | local | no |
| 6 | `feat/maintenance-manual-sheet` | strict sheet schema, loader, conservative default; LLM extraction behind the mock provider | 5, guard | local plus mock | no |
| 7 | `feat/failure-history` | synthetic log generator (outside `waggle.sim`), `failure_history` table, diagnosis retrieval | 6 | cloud for the DB test | yes, flagged (new tables; schema revision check first) |
| 8 | `exp/e6-runner` | E6 runner, scorer, baselines B0 to C3, result schema, workflow | 5, 6 | cloud | no |
| 9 | `exp/e6-dev-run` | development seed run, tuning of N and L_target | 8 | cloud | no |
| 10 | `feat/sim-sensor-faults` | T3 dropouts, drift, stuck-at, scenario families S19 to S36 as the layers appear | 3 | local | no |

The held-out E6 run is a separate maintainer-triggered step after branch 9 and is not a branch. `machine_telemetry` (sampled table in ARCHITECTURE) is stored only if the viewer needs history; the experiment does not need it (D6). Any ticket-bound schema change from the compatibility design is its own migration and is not repeated here.

## 10. Decisions for the maintainer

| # | Question | Recommendation |
|---|---|---|
| D1 | Confirm that the simulator uses a two-node thermal plus power law wear model and the predictor a one-node model with CUSUM | Yes; satisfies 9.8 and keeps the PLAN.md predictor |
| D2 | Real machine classes, their count, and the failure modes and wear behavior that matter for the demo | Start with one machine and the three modes in section 2; supply real names and limits when available |
| D3 | Cost weights for false alarm versus missed failure, and the technician response time that sets L_target | Report counts only until given; choose L_target above response time |
| D4 | Number of machines and development and held-out seeds for E6 | Many seeds on one machine; state that the sample is the seed count |
| D5 | May `dispatch_tech` require a reservation or order first, or does a technician go before the part? | Dispatch after a reservation or order, to avoid empty visits; behavior change, needs an ADR |
| D6 | Store telemetry in a table, or keep it in the simulator and result file only | Result file only until the viewer needs it |
| D7 | The part list, compatibility rows and manuals (or manual excerpts) for the machines | Required from the maintainer; the repository holds only sample data (ADR-056) |

## 11. Not claimed by this design

- No code, test, migration or workflow exists for any step above.
- No result: lead time, false alarm rate and missed failure rate are unmeasured. No number here is a result.
- No claim that a first-order model predicts real bearing failures. The simulator is synthetic, and simulated physics proves nothing about real machines.
- No claim of standards compliance, certification, hardware real-time guarantees or large-fleet performance.
- The synthetic failure log is not evidence about real failures.
- The parts runner step depends on the package model, which is not designed to completion (PENDING row 92).
