# Waggle Hive: Experiments Protocol

Principle: measured, not assumed. Every table in the README comes from a script in `experiments/` that runs from a seed and writes a result file. `/experiments` renders those files.

## General method

- Seeds are split before any tuning: development seeds (used while building) and held-out test seeds (run once per configuration).
- Every comparison has a baseline with the layer disabled, same seeds.
- Proportions are reported with Wilson 95% intervals and the raw counts. Continuous values are reported as median and range or percentiles. Small samples are called small.
- Failing seeds are listed, not hidden.
- Layers overlap, so contribution is measured by ablation, not by summing blocks.
- Results record: git commit, seed set, model ids, prompt versions, date.
- Model nondeterminism: each LLM evaluation is repeated and the repeats are reported as repeats, not as independent samples. Verdict drift across runs hours apart is checked once.
- LLM calls are cached by (model, prompt hash, seed) for replay of non-LLM parts. Cached runs are labeled.

## Scenario catalog

Difficulty is raised on purpose so that ablations can show differences.

| ID range | Family | Examples |
|---|---|---|
| S01 to S06 | Blind corners and narrow aisles | Human steps out at a corner as a forklift turns; two robots meet in a one-lane aisle |
| S07 to S12 | Adversarial humans | Human crosses at the worst time against the stopping distance; human stops in the aisle |
| S13 to S18 | Density | 3, 10, 30 robots on the same map |
| S19 to S24 | Combined faults | Machine overheats while a worker dies and a human crosses |
| S25 to S28 | Failures of dependencies | LLM latency spike, LLM outage, database delay, duplicate delivery |
| S29 to S30 | Sensor faults | Telemetry dropout, stuck sensor |
| S31 to S36 | Coordinated handoff | See the table below |

Each scenario has: seed, map, entities, scripted events, declared target layer, expected outcome.

Zone state FAULT_OCCUPIED applies to S31 to S36: a zone is never released while the last known odometry puts a chassis in it.

Coordinated handoff (designed, not implemented):

| ID | Scenario | Target layer |
|---|---|---|
| S31 | Runner killed mid delivery | Lease expiry, fencing token |
| S32 | Duplicate delivery of the same handoff | Idempotency key |
| S33 | Technician waiting at the rendezvous while the part is late | Task dependency, safe hold |
| S34 | Rendezvous contention: two runners for one zone | Lease with capacity one |
| S35 | Stale runner resumes after reassignment and tries to deliver | Fencing token |
| S36 | Handoff message with a forged mission id | Message schema, MCP identity |

## E1: Fast control layer

- Question: how many human collisions and separation violations happen with and without the fast layer.
- Method: N scenarios (S01 to S18) times seeds. Detector is the independent exact detector from Phase 1.
- Seeds: S01 to S18 with 5 development seeds and 12 held-out seeds each, generated once from a fixed master seed and stored in `data/seeds.json`, disjoint and never regenerated. Each scenario carries a flag `unavoidable_at_spawn`, computed from geometry: a human spawns inside the minimum possible stopping distance of a robot at its speed cap. E1 reports unavoidable cases separately and never hides them. That is 90 development runs and 216 held-out runs per configuration. With 216 runs and zero collisions the Wilson 95% upper bound is about 1.7%. With 100 runs it would be 3.7%.
- Configurations (harness implemented in B17, development seeds run in the cloud, ADR-028), eight, same seeds: `no_control`, `radial_lidar`, `envelope_oracle`, `envelope_lidar`, `envelope_lidar_beacons`, `envelope_occlusion_lidar`, `envelope_occlusion_cpa_lidar`, `envelope_occlusion_cpa_lidar_beacons`. The oracle scan is a noiseless, unoccluded `LidarScan`, so the control code never reads ground truth. Contribution is measured by ablation pairs (any control, swept footprint, real sensing, beacons, occlusion cap, CPA). Control steps are: no control, radial 1D distance, swept footprint, swept footprint plus occlusion cap, and swept footprint plus occlusion cap plus CPA prediction. Sensing is oracle, lidar, or lidar with beacons, and the contribution of envelope with prediction against envelope only is read from the ablation pairs. Envelope with CPA but without the occlusion cap is not run.
- Metrics: collisions with humans, collisions between robots, near-misses, separation violations, false stops, throughput (tasks per hour), loop latency. Proportions with Wilson 95% intervals and raw counts.
- Baseline: no envelope, no e-stop.
- No-control baseline (Phase 1, configuration `no_control`): the waypoint driver of `waggle.sim.scripted` only, which has no safety logic and is not the control layer. Run on development seeds only, written to `results/e1/dev/`. S01 to S18 run on map A (S01 to S15) and map B (S16 to S18). S13 to S18 are 3, 10 and 30 robots on map A and then on map B.
- Definitions (declared per scenario, assumptions): a collision is contact between a robot footprint and a human disc or another robot, closed sets. A separation violation is a gap below 0.5 m, strictly below, and a collision is also a violation. A near miss is no contact and a gap below 0.2 m. All three are counted as episodes, not ticks. Unavoidable cases are counted in the totals, listed separately and also subtracted in a second set of totals.
- Report: counts, intervals, every failing seed, latency as code latency.
- Harness (B17): `waggle.experiments` (`e1_config`, `e1_rig`, `e1_run`, `e1_stats`, `e1_report`). `uv run experiments-dev` runs the chosen configurations on the development seeds only (there is no held-out option and the held-out list is never read) and writes `results/e1/dev/<configuration>_<date>.json`. `uv run report` writes `results/e1/dev/report.md` from the latest file of each configuration, and shows a missing configuration as missing. The full 720 runs are the workflow `.github/workflows/e1.yml` (one job per configuration, started by hand).
- In the rig the control code gets a `LidarScan`, a `RobotOdometry` and `BeaconReport` items, nothing else. The rig runs right after the waypoint driver, reads the requested command from the actuation ring and writes the limited command over it. Odometry noise uses the `robots` random stream, the lidar the `lidar` stream and the beacons the `beacons` stream, one per robot. A raised forklift load changes the speed and braking of the robot, and the control code is given the same figures.
- Reflex limits (watchdog, geofence, e-stop) are off in E1: no scenario of S01 to S18 loses a heartbeat or sets a geofence.
- Known reading rules: a false stop is defined against humans only, so in a scenario without humans every stop is counted as false whatever stopped the robot (two robots in a one lane aisle stop each other). Throughput is compared with `no_control` on the runs both files share. Distance is the path length of all robots over the same runs as `no_control`, and mean speed over request is the limited over the requested speed per control call. Both read slowing without the waypoint cliff: a robot slowed on a long route reaches no waypoint in a short scene (E1 dev run 2, S01 to S08). The aggregate speed over request of the controlled configurations (0.16 to 0.19 in dev run 4) is dominated by the 10 and 30 robot scenes, where other robots count as static structure and followers queue (speed over request 0.04 to 0.26). Read it by scenario, and state the cause next to the number (ADR-028 addendum). Latency is the median of the run medians and the worst run 99th percentile, from the machine that ran the job.

## E2: Leases, fencing and chaos

- Question: do fencing tokens prevent double assignment and stale writes under failures.
- Method: 500 concurrent tasks, kill workers at random points, expire leases early, duplicate deliveries, delay the database.
- Metrics: double assignments, two robots in a one-lane zone, stale-token writes accepted, tasks recovered, tasks stuck, recovery time, deadlocks (robots that stop making progress on a cycle of waits; counted in the S13 to S18 density scenarios).
- Baseline: lease check outside the tool, no token. Expected to show failures. Report them.
- Handoff chaos test (designed, not implemented): S31 to S35 under random kills. Counts of double deliveries and double repair starts. Baseline without fencing, expected to show nonzero counts.
- Property tests with Hypothesis: token monotonicity, mutual exclusion, no accepted write with a stale token.

## E3: Injection matrix

- Question: which layer blocks which attack and what passes when a layer is off.
- Corpus: labels, SOP text, manual text, inter-robot messages, voice transcripts, court-targeted injections. Includes benign near-lookalikes to measure false rejection.
- Method: each case runs with all layers on, then with each layer ablated one at a time: guard off, MCP identity off, schema bounds off, court off.
- The guard is the Muse Glimmer classifier after deterministic sanitizers. The label policy is fixed before the run. Report misses and false rejections on benign near-lookalikes.
- Metrics: attempts that reach a side effect, attempts rejected per layer, false rejections on benign cases.
- Each case declares its target layer before the run.

- Development declarations: [E3 corpus](../data/e3/README.md), 25 synthetic cases in `data/e3/cases.json` for T1 to T6, T11 and T18, including reference near-lookalikes. All labels are pending maintainer review. Construction metadata is not a truth label. This is a small corpus, not an evaluated or held-out set. Tests validate declarations only; no E3 runner or model call is included. Missing production layers and entry points must fail explicitly before an evaluation rather than appear as passes.

## E4: Court

- Question: does a unanimous court of related Muse models reduce unsafe approvals, and at what cost in false blocks.
- Dataset: labeled tasks (benign, risky, ambiguous) with labels written before the run. Dev and test split.
- Configurations:
  - A: single Muse Spark
  - B: two Muse members
  - C: three Muse members with identical prompts (Muse Spark, Muse Spark Open, Muse Glimmer)
  - D: three Muse members with role-specialized checklists (SOP compliance, provenance and injection, operational conflict)
  - E: two Muse members plus a non-Muse member on Vertex, run once on the held-out set within the Vertex cap
  - An LLM never checks inventory, chassis capability or zone invariants: code does.
- The default court for the live demo is whatever the held-out results support.
- Metrics: false approvals, false blocks, escalation rate, agreement and pairwise error correlation (Muse pairs, and Muse versus non-Muse in E), latency, cost per task.
- Repeats per case, reported as repeats.

## E5: Per-robot advisors

- Question: do the safety advisor and the organizer improve outcomes beyond the code-only system.
- Configurations: none, safety advisor only, organizer only, both, and the fleet planner as an extra configuration (never a replacement for the code-only baseline). Same seeds.
- Metrics: near-miss count (separation below a threshold but above collision), false stops, tasks per hour, mean task time, LLM calls and cost per task, behavior under LLM outage.
- If an advisor does not change outcomes, that is the result.

## E6: Predictive maintenance

- Question: how early and how reliably does the system act on machine degradation.
- Setup: one machine, three failure modes (for example bearing wear, lubrication loss, misalignment), seeded hidden onset, noise. Simulator dynamics differ from the predictor model.
- Metrics: lead time between first action and failure, false alarms per 100 machine-hours, missed failures, wrong part orders, tickets per failure event, robots stopped before entering the hazard zone.
- Designed, not implemented: diagnosis accuracy among the three failure modes with and without the failure history, wrong part orders, duplicate purchase orders (idempotency key per failure event).
- Baseline: fixed threshold on temperature and vibration, no model, no manual sheet.
- Circularity check: predictor parameters are never shared with the generator.

## E7: Multimodal

- Voice: transcription error rate on item ids over a spoken set with background noise variants, plus rate of wrong executions after read-back.
- Vision: accuracy of label and obstruction verification on synthetic images, including images with adversarial text on the label.
- Report that images are synthetic.

## E8: Latency and cost

- Fast loop latency (percentiles, as code latency).
- LLM latency distributions per model and role.
- Cost per task, by role, from the `llm_calls` table.
- Extrapolation to large fleets: a stub that samples the measured latency distributions and failure rates. Reported as extrapolation, with the assumptions listed and what is not validated.

## E9: Regression detection

- Question: if a safety check, a threshold or a validator is weakened, do the tests and the experiments notice, and which layer notices first.
- Setup (designed, not implemented): mutation testing of `waggle.control` and the validator rules with a mutation tool run only in the cloud, plus a hand-written list of planted defects (a margin lowered, a cap that can raise speed, a stale scan accepted, a fencing comparison inverted). Each planted defect declares the test or experiment expected to catch it before the run.
- Metrics: mutants killed over mutants generated, with the surviving mutants listed, and planted defects caught over planted, with the first detector named for each.
- Report surviving mutants and undetected defects in full. A mutant that is equivalent to the original is marked as such by hand, not dropped.

## E10: Crisis replanning

- Question: does an LLM planner with counterexample feedback recover from compound faults better than a strong deterministic baseline, and how often does an accepted plan still fail.
- Setup (designed, not implemented): compound-fault templates combining the thermal fault that triggers the geofence, blocked aisles, a robot dead mid hand-off (zone state FAULT_OCCUPIED), and urgent orders by text or voice, with an optional vision input and an always available text incident report. Held-out seeds.
- Configurations:
  - strong deterministic recovery baseline: A* routing, reassignment, lease release, and the same repair moves that the planner prompt describes
  - Muse open loop
  - Muse with validator feedback
  - Muse with validator feedback and the role-specialized court
- Metrics: violations in validation and in execution, deadlocks, recovery time, iterations, calls, cost, escalations, and the fraction of accepted plans that produce a violation in an extended 120 s rollout or in execution.
- Sensitivity: a run with H in 30, 45 and 60 seconds.
- Report what the LLM adds beyond the deterministic baseline per template. The validation is simulation-based, not a proof, and the hidden human prior, K and H are stated with every result.

## Reproduction

```
make experiments-dev    # development seeds
make experiments-test   # held-out seeds, run once per configuration
make report             # regenerate tables and /experiments from result files
```

## Result file schema

Held-out results: `results/<experiment>/heldout/<run_id>.json` with `"seed_set": "heldout"`.
Development results: `results/<experiment>/dev/<run_id>.json` with `"seed_set": "dev"`.

Each file records: commit, date, seed set, configuration, model ids, raw counts, derived metrics, failing seeds, notes. A test checks that every JSON under a `heldout/` folder has seed_set heldout and every one under `dev/` has dev. Agents never write under `heldout/`; the safety guard denies it.
