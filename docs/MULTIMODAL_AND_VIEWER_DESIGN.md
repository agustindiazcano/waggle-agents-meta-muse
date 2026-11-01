# Multimodal inputs and technical viewer design

Status: proposed, nothing is implemented. This covers PLAN.md Phase 7 (voice, vision, 3D scene, GLB models, E7, E8 extended, E9) and Phase 7B (viewer v0), and PENDING.md row 33. The maintainer decides; an agent builds it later, branch by branch. The full scope stays; this document only orders it.

## 1. What exists and what is missing

| Item | State | Source |
| --- | --- | --- |
| Phase 7 and 7B task lists, E7 summary (voice id error rate, label accuracy with adversarial text, "images are synthetic") | Exists as a summary, no protocol | PLAN.md, `docs/EXPERIMENTS.md` E7 |
| Roles `voice` (Meta, `META_VOICE_MODEL_ID`) and `vision` (Meta, `META_MODEL_ID`), no fallback declared | Exists in config | `src/waggle/llm/routes.toml` |
| `LlmRequest` carries `request_id`, `role`, `prompt` (text), `task_id` only. No field for image or audio bytes | Gap | `src/waggle/llm/models.py` |
| Read-back and item resolution by code, `Confirmation` produced only by the operator channel, E3-T4 runner | Exists, unit tested, no real transcript connected | ADR-057, `src/waggle/governance/readback.py` |
| Sanitizers by `UntrustedSource` (voice, label, SOP, manual, message) and guard adapter | Exists | `src/waggle/governance/sanitizers.py`, ADR-052 |
| Threat rows: voice and label as untrusted inputs, T1 label injection, T4 wrong item from voice | Exists | `docs/THREAT_MODEL.md` |
| Vision and voice package `src/waggle/multimodal` | Empty (`__init__.py` only) | repo |
| Package registry and `pick_package` success path (labels need a package to read) | Designed, not built | `docs/PACKAGE_MODEL_DESIGN.md`, PENDING row 92 |
| Synthetic FPV render, obstacle class input to the planner, text incident fallback | Described in the planner contract, not built | ARCHITECTURE.md Multimodal, PHASE1_BRIEF |
| Viewer rule: Three.js only renders, state over WebSocket | Decided | ADR-002 |
| Web dependencies approved (Vite, TypeScript, three, @types/three, Playwright; fastapi, uvicorn[standard] for `waggle.api`) with committed lockfile and `npm ci` | Approved, not installed | ADR-029, PENDING row 26 |
| `waggle.api` | Stub (`__init__.py`, `__main__.py`) | `src/waggle/api` |
| `web/` | Placeholder `index.html` only | `web/index.html` |
| Mockup `index (1).html` (Three.js 0.186.1, JavaScript mock simulation), untracked in the repo root | Not read by this design, not touched | PLAN.md Phase 7B, PENDING row 33 |
| Simulator state: `SimState(tick, arrays)`, `Snapshot` with RNG states, `canonical_hash`, `Engine.step/snapshot/fork`. Array names seen: `robot_pose`, `robot_active`, `human_pos`, `human_heading`, `det_flags`, `script_wp` | Exists. No export for a renderer | `src/waggle/sim/state.py`, `engine.py` |
| GLB list (nine files) with license note (Meshy Pro) and `TBD` rows | Exists as a list; no file generated | `ASSETS.md` |
| E8 (latency and cost, extrapolation stub) and E9 (mutation testing and planted defects) | Defined; E9 is regression detection per ADR-029 | `docs/EXPERIMENTS.md` |

Conflicts found. (1) The task text calls E9 part of the 3D/GLB group; ADR-029 and EXPERIMENTS.md define E9 as regression detection, unrelated to GLB. This design follows the repository and keeps E9 in section 6 only for ordering. (2) PLAN.md order puts the viewer (item 5) before multimodal (item 6) while Phase 7 lists the 3D scene first; this design follows AGENTS.md section 18. Neither point is expanded further.

## Part A: Multimodal

### 2. Voice path

Flow: push-to-talk in the browser, audio to the API, `waggle.multimodal.voice` calls role `voice` through `waggle.llm` (the only place for model calls, 5.6), then sanitizer (`UntrustedSource` voice), guard, an intent schema, item resolution by code, read-back, `Confirmation`, then the ordinary MCP path.

| Option | Trade-off | Verdict |
| --- | --- | --- |
| A. Transcript goes to the Director as free text | Simple. A spoken instruction reaches a planner and can steer it | Rejected by 8.6 and T4 |
| B. Transcript to a closed intent schema, then code | The model output is data, validated with extra fields forbidden. Cannot widen access | Recommended |
| C. Transcript only fills a text box the operator edits | Safest. Slower, removes the point of voice | Kept as the degraded text fallback (PLAN.md) |

Recommendation B. Intent schema (strict, versioned `voice-intent-v1`): `intent` in a closed enum (`pick_item`, `deliver_item`, `report_obstruction`, `status_query`, `cancel_last`), `item_ids` and `zone_ids` as strings that are only candidates, `confidence` 0..1. The intent parser is deterministic where possible (existing `resolve_items`); a model, if used, only proposes the enum value and ids, and every id is resolved against the trusted order and catalog in code.

Rules:
1. Who may speak: the audio request carries the authenticated operator identity from the session, never a name said in the audio. An unauthenticated stream is rejected. Speaker identification is not used and not claimed.
2. A voice command may only request what the same operator could request by text. The resulting order goes through the MCP identity, allowlist, schema bounds and audit like any call. Nothing in the audio sets chassis, zone, speed or limits.
3. Consequential commands (`pick_item`, `deliver_item`, anything that creates a motion order) require the ADR-057 read-back: the text comes from the trusted order item, the operator confirms on the operator channel (a button or typed id), and only a typed `Confirmation` authorizes. The words "yes" or "confirmed" in the transcript are never parsed as a confirmation. `status_query` and `report_obstruction` need no confirmation but still produce only a ticket or a read.
4. Screening: if the sanitizer or guard cannot score the transcript, reject and send it to the operator inbox (8.6). A low `confidence` or two candidate ids for one slot is a rejection with a request to repeat, never a guess.
5. Transcription timeout, provider error, or an empty transcript returns an error result and the text fallback; the process continues (6.5).

Gaps stated plainly: no audio field exists in `LlmRequest`; adding one touches the provider interface and needs a test first. The Muse Voice Transcribe request format must be read from current provider documentation before implementing (11.7); this design does not assume it.

### 3. Vision path

Flow: simulator renders a synthetic FPV image of a package or an aisle, `waggle.multimodal.vision` calls role `vision`, output is validated against `vision-v1`, then code compares it with the catalog and package registry.

| Option | Trade-off | Verdict |
| --- | --- | --- |
| A. Model returns the package id, the system trusts it | Fast. One bad read becomes a wrong pick | Rejected |
| B. Model returns raw label text and a class; code resolves against the registry and catalog | The model is a reader, code decides. Needs PENDING row 92 registry | Recommended |
| C. OCR library, no model | Deterministic, but adds a runtime dependency (12.10) and does not cover obstruction | Listed as a maintainer decision (D5), not chosen here |

Recommendation B. Schema `vision-v1`, extra fields forbidden: `label_text` (bounded length), `obstruction_class` (closed enum, includes `none` and `unknown`), `legibility` 0..1. The label text is untrusted: it passes the sanitizer (`UntrustedSource` label) and guard before any later model sees it, and an instruction-like label is data, never an action (T1). Package identification is a code lookup of the sanitized `label_text` against the package registry and catalog (8.7 for parts). No match, more than one match, or `legibility` under a threshold set in config yields `unknown`, which escalates to a text report. The planner may use only `obstruction_class`, as PHASE1_BRIEF states; vision is not in the control loop.

Adversarial label images: cases with printed instructions, a plausible second id in small print, a label contradicting the order, a blurred label, a screen-like overlay. Each declares its target layer before the run (9.4): sanitizer and guard for instruction text, registry lookup for wrong ids, `unknown` handling for blur.

### 4. Failure modes (all fail closed unless stated)

| Component | Failure | Behavior |
| --- | --- | --- |
| Transcription | timeout, error, empty, no budget | error result, text fallback, no order |
| Sanitizer or guard | cannot score | reject, operator inbox |
| Intent schema | parse failure, unknown field, unknown enum | reject |
| Item resolution | zero or several candidates | request repeat, no order |
| Confirmation | missing, stale prompt id, other item | no execution (ADR-057) |
| Vision | invalid output, low legibility, no registry match | `unknown`, text report |
| Budget guard | call would pass the cap | typed denial, no call, logged |
| Fallback model | route used | labeled in the call log; disabled in held-out runs, a failed call counts as a failure (6.9) |
| Audio out, viewer overlays | failure | fail open, never blocks control |

### 5. Cost method

No figure is stated here. Cost per voice command and per image comes from `llm_calls` rows for roles `voice` and `vision` grouped by `task_id` (6.6, 14.6), with tokens, latency, provider and a mock or real label. Audio and image inputs may be billed differently from text; the unit must be read from the provider console and recorded with the date before any estimate (14.1 balances are unverified, PENDING rows 4, 5). E8 reports these as distributions per role; planning splits follow 14.3.

### 6. E7 protocol

| Item | Definition |
| --- | --- |
| Question | Does the voice path execute a wrong item, and does the vision path accept a wrong or injected label |
| Voice cases | Spoken item ids, each in several noise variants (levels declared before the run), plus injection utterances and ambiguous ids. Audio is synthetic or recorded by the maintainer; its source is recorded |
| Vision cases | Synthetic labels and aisles rendered by the simulator, correct, blurred, conflicting, and adversarial text. Images are synthetic and the report says so |
| Labels | Written before runs and decided by the maintainer; new cases stay pending until reviewed (10.2) |
| Primary metrics, first | False accepts: wrong executions after read-back, wrong package accepted, injected label acted on. Counts out of cases, Wilson 95% interval |
| Secondary | Item-id error rate in the transcript, false rejects, `unknown` rate, escalation rate |
| Baselines | Voice: no read-back, same seeds; vision: model id trusted without registry check. Contribution by ablation (9.3) |
| Mock run | Deterministic, no network, validates harness and schemas. Reports are labeled "mock" and measure the rule, not a model (as ADR-057 states for E3-T4) |
| Real run | Cloud workflow only, `llm` marker, caps verified first, repeats reported as repeats (9.7). Held-out cases run once per configuration, maintainer commits the file (3.10) |
| Result file | commit, seeds or case set, model ids, prompt versions, date, fallbacks disabled, failing case ids listed |

Implemented, not evaluated applies to every item above until a result file exists.

### 7. GLB models, E8 extended, E9

GLB: nine files listed in `ASSETS.md` (`carrier_bot`, `heavy_forklift_bot`, `parts_runner_bot`, `tech_repair_bot`, `human_worker`, `human_technician`, `industrial_machine`, `warehouse_rack`, `package`), all `TBD`. They come from the maintainer's Meshy account; an agent cannot generate them. Rules proposed: a loader with a primitive fallback per entity (so viewer v0 and tests never need a GLB), file size and triangle budget measured and recorded in `ASSETS.md`, license screenshot in `docs/licenses/`, and the Meta model attribution wording held until PENDING row 8 is answered (flagged, not decided). Assets carry no risk to measurements (ADR-002).

E8 extended: add `voice` and `vision` roles to the latency and cost tables, and viewer frame time as a labeled client-side figure, never mixed with fast-loop code latency (9.9). Large-fleet figures stay labeled extrapolation. E9: the protocol in EXPERIMENTS.md is unchanged; this design only adds that the snapshot schema validator and the viewer's schema-version check are in the planted-defect list (accept an unknown version).

## Part B: Technical viewer

### 8. Snapshot contract

Producer: a pure function in `waggle.sim` (for example `export_frame(engine, schema_version) -> dict`) that copies from `SimState`; the viewer never integrates, predicts or decides collisions (5.4). Anything that is not in the simulator (overlays) is computed by the simulator or by `waggle.control` and shipped as data.

| Field | Meaning | Source |
| --- | --- | --- |
| `schema_version` | integer, bumped on any change | contract |
| `tick`, `dt`, `sim_time` | tick count, fixed step, tick times dt | `SimState.tick` |
| `state_hash` | `canonical_hash` of the state at this tick | `sim.state` |
| `run` | `commit`, `seed`, `scenario_id`, `source` (live or replay) | run metadata |
| `robots[]` | id, pose x y heading, active, speed limit in force, mode (normal, reduced, stopped) | `robot_pose`, `robot_active`, control |
| `humans[]` | id, position, heading | `human_pos`, `human_heading` |
| `zones[]` | id, polygon id, occupant id or null (null means unknown), fencing token number | trusted occupancy (ADR-041) |
| `machines[]` | id, state, temperature, severity | maintenance state |
| `overlays` | optional; see section 10 | sim, control |
| `events[]` | typed events since the last frame (stop, geofence, denial, ticket) | audit and sim |

World geometry (walls, racks, aisles) is sent once in a `world` message with its own `schema_version` and hash, not every tick.

Limits: positions rounded to a fixed decimals count equal to the one `canonical_hash` uses, so the same seed gives identical frames; strings bounded; unknown fields allowed only inside `overlays.extra`, otherwise rejected by the viewer. Rate: simulation tick rate and send rate are different; the bridge sends at most a configured frames per second and always includes `tick` so skipped frames are visible. A frame size cap is set in config and measured (see section 12); an oversize frame is dropped and logged, never truncated silently.

Determinism: same seed and scenario give byte-identical frame sequence for the same `schema_version`; no wall clock or random in `export_frame` (5.5). A test compares two runs.

### 9. Live versus replay file

| Mode | How | Trade-off |
| --- | --- | --- |
| Live | `waggle.api` (FastAPI) streams frames over WebSocket from the simulator bridge | Interactive, chaos buttons call the scenario format with seeds. Needs a running service, Docker rules 12.14 (non-root, Python healthcheck, image tagged with commit) |
| Replay file | Viewer loads a JSON Lines file recorded by a script, no server | Works for the demo video, offline, deterministic. No interactivity beyond scrub and play |

Recommendation: build both from one frame decoder in the viewer. The replay file starts with a header line: `schema_version`, `commit`, `seed`, `scenario_id`, `dt`, `world` hash, frame count, and ends with the final `state_hash`. The viewer shows the hash bar from the file; it does not recompute. A separate Python command (`uv run replay-verify FILE`) re-runs the simulator from seed and compares hashes per tick; this is the check, not the viewer. Replay files are produced by running the simulator, never edited by hand. A file for the video that was produced on dev seeds is labeled as such. Held-out result files and held-out seeds are not used as viewer fixtures (9.1).

### 10. Overlays and the simulator data each needs

| Overlay | Needs | Notes |
| --- | --- | --- |
| Safety envelope per robot | swept footprint polygon for current speed and stopping distance, from the fast layer | computed in `waggle.control`, shipped as polygon points |
| Separation margin ring | margin value and nearest human or robot id | from the fast layer, no recomputation in the browser |
| Lidar shadow (occluded region) | occlusion polygon or ray endpoints for the scan, `LidarScan.ranges` | scans are large; ship downsampled endpoints at a fixed rate and label it |
| Rollout ghost paths | K variant paths from the validator, per tick sample positions, hash of the input snapshot | ADR-023, ADR-025; from `waggle.sim.rollout`, labeled with K and H used |
| Zone and lease state | occupant, token, expiry tick | trusted store |
| Hazard and machine state | temperature, severity | maintenance state |

Overlays are optional per frame, so the viewer works with the minimum and shows "not provided" instead of inventing geometry. Rollout cost is large (ADR-029 addendum), so ghost paths are produced at a lower rate or precomputed in replay files; any reduced K, H or rate is labeled on screen.

### 11. Mockup move and mock removal

Steps, each a stacked branch: (1) after the mockup file is handed over by the maintainer, copy it to `web/legacy/mockup.html` unchanged, no edit, as a visual reference and as the fallback for the video; (2) build `web/` with Vite and TypeScript from the contract, rendering primitives; (3) port the look (camera, colors, HUD) piece by piece; (4) delete the JavaScript mock simulation in the new code (ADR-002), and add a test that greps `web/src` for any physics or collision code (integration, step functions) and fails; (5) once the real viewer plays a replay file, delete `web/legacy/`, or keep the legacy copy only if the maintainer wants a pre-recorded video that does not depend on the new code (decision D4). The mockup is read only by a human or by an agent the maintainer authorizes; this design did not read it. The attribution text in `web/index.html` waits for PENDING row 8.

### 12. Performance budget as a method

No budget number is claimed. Method: Playwright with a fixed scenario and replay file records frame time percentiles, frame size percentiles and decode time; the sets of robots 3, 10 and 30 match S13 to S18. The maintainer sets the pass line after seeing the first measurement, recorded in `docs/DECISIONS.md`. Measurements are viewer client figures, reported as such, and the README may not cite them as results of the system (the viewer is not a source of results).

### 13. Tests and invariants, written first

| Test | Kind | Fails if |
| --- | --- | --- |
| Frame export is deterministic: two runs, equal frames and hashes | unit, `waggle.sim` | any wall clock or random enters |
| Frame export contains only listed fields and no values the simulator did not hold | unit | extra field |
| `waggle.sim` and `waggle.control` do not import `waggle.api` or web libraries | import-linter (ADR-029) | contract broken |
| Viewer rejects an unknown `schema_version` and shows a visible error, no render | Playwright contract test | silent accept |
| Viewer rejects a frame with an unknown field outside `overlays.extra` and a frame over the size cap | Playwright or Vitest | accept |
| Replay header missing commit, seed, scenario or version is refused | Vitest | accept |
| `web/src` has no integration or collision code | grep test | present |
| Voice: transcript stating "confirmed" does not authorize; unscored transcript is rejected; ambiguous id requests repeat | unit (extends ADR-057) | authorize |
| Vision: injected label text never reaches the Director unfenced; no registry match gives `unknown` | unit with mock provider | passes through |
| Unauthenticated audio is rejected; spoken name does not change identity | unit | accept |
| Audio and image requests with a repeated `request_id` return the cached result | unit | second call made |
| Playwright smoke: replay file loads, play, scrub, hash bar shows file's hash | cloud | fails |

The replay-verify command is tested with a tampered file and must fail.

## 14. Build order (stacked branches)

| # | Branch | Content | Depends on | Where | Paid calls | Maintainer assets |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `docs/multimodal-viewer-design` | this document | none | local | no | no |
| 2 | `feat/sim-frame-export` | `export_frame`, contract tests, JSON Lines recorder, `replay-verify` | none | local, light | no | no |
| 3 | `feat/api-frame-stream` | FastAPI app, WebSocket bridge, import-linter contracts, Docker service per 12.14 | 2, ADR-029 install | local light, CI cloud | no | no |
| 4 | `feat/web-viewer-v0` | `web/` Vite, TypeScript, three, primitives, top-down camera, schema checks, replay mode | 2 | CI cloud, Playwright cloud | no | mockup handed over (row 33) |
| 5 | `feat/viewer-overlays` | envelope, margin, lidar shadow, ghost paths, `overlays` fields | 2, 4, fast layer and rollout | cloud for ghost paths | no | no |
| 6 | `feat/llm-multimodal-input` | image and audio fields in the provider interface, mock provider support, budget guard on both | none | local | no (mock) | no |
| 7 | `feat/voice-intent` | `voice-intent-v1`, pipeline, extends ADR-057, E7 voice mock runner | 6, row 92 for items | local | no | no |
| 8 | `feat/vision-label` | `vision-v1`, FPV render from the simulator, registry lookup, adversarial cases, E7 vision mock runner | 6, row 92 | local | no | no |
| 9 | `feat/web-multimodal-ui` | push-to-talk, read-back dialog, text fallbacks, alarms | 4, 7 | cloud | no | no |
| 10 | `feat/glb-loader` | loader with primitive fallback, size checks | 4 | cloud | no | nine GLB files |
| 11 | `exp/e7-multimodal-dev` | E7 workflow, dev cases | 7, 8 | cloud, `llm` | yes, after rows 4, 5, 7, 88 | audio recordings, case labels |
| 12 | `exp/e8-e9-extended` | E8 roles added, E9 planted defects added | 2, 7, 8 | cloud | E8 real latency needs real calls | no |

Held-out E7 runs happen once per configuration in the cloud after the maintainer approves.

## 15. Decisions for the maintainer

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Approve intent schema B for voice with typed operator confirmation for consequential commands | Yes |
| D2 | Who may speak: any authenticated operator, or a named subset per scope | Authenticated operators only, per-operator scope later |
| D3 | Recorded voice and image sources for E7: who records, and are synthetic text-to-speech clips acceptable as a first set | Maintainer records a small set; synthetic clips labeled as such for noise variants |
| D4 | Keep the legacy mockup as the video fallback, or replace it with the replay-file viewer | Replay-file viewer as fallback; keep the legacy copy until it plays one full scenario |
| D5 | Use the vision model for label reading (option B) or add an OCR dependency (option C) | B; C only if B fails on development cases (12.11) |
| D6 | Viewer pass line for frame time after the first measurement | Maintainer sets it after measurement |
| D7 | Muse Model License attribution wording (PENDING row 8) | Maintainer reads the text and decides |
| D8 | Whether a fallback route is declared for `voice` and `vision` (none today) | None until a primary failure is seen |

## Not claimed by this design

- No implemented code, no run, no test of any model, no number measured. No cost, accuracy, latency or frame-rate figure is stated.
- No claim that voice or vision improves any result; both are "implemented, not evaluated" until E7 has a result file.
- No speaker identification, no claim of standards compliance, no real-time guarantee from the browser, no large-fleet claim.
- The viewer is not a source of results; README numbers come from result files only.
- The Muse Voice Transcribe and vision request formats, their billing units and the license attribution wording were not read.

Not read for this design: the mockup `index (1).html`, any result JSON, lockfiles, `src/waggle/llm/providers.py` and routing code beyond the routes file and public dataclasses, `docs/MULTI_WAREHOUSE_PLAN.md`, and the full text of E1 to E6 and E10.
