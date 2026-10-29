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

Each scenario has: seed, map, entities, scripted events, declared target layer, expected outcome.

## E1: Fast control layer

- Question: how many human collisions and separation violations happen with and without the fast layer.
- Method: N scenarios (S01 to S18) times seeds. Detector is the independent exact detector from Phase 1.
- Metrics: collisions with humans, collisions between robots, separation violations, throughput (tasks per hour), loop latency.
- Baseline: no envelope, no e-stop.
- Report: counts, intervals, every failing seed, latency as code latency.

## E2: Leases, fencing and chaos

- Question: do fencing tokens prevent double assignment and stale writes under failures.
- Method: 500 concurrent tasks, kill workers at random points, expire leases early, duplicate deliveries, delay the database.
- Metrics: double assignments, two robots in a one-lane zone, stale-token writes accepted, tasks recovered, tasks stuck, recovery time.
- Baseline: lease check outside the tool, no token. Expected to show failures. Report them.
- Property tests with Hypothesis: token monotonicity, mutual exclusion, no accepted write with a stale token.

## E3: Injection matrix

- Question: which layer blocks which attack and what passes when a layer is off.
- Corpus: labels, SOP text, manual text, inter-robot messages, voice transcripts, court-targeted injections. Includes benign near-lookalikes to measure false rejection.
- Method: each case runs with all layers on, then with each layer ablated one at a time: guard off, MCP identity off, schema bounds off, court off.
- Metrics: attempts that reach a side effect, attempts rejected per layer, false rejections on benign cases.
- Each case declares its target layer before the run.

## E4: Court

- Question: does a cross-family unanimous court reduce unsafe approvals, and at what cost in false blocks.
- Dataset: labeled tasks (benign, risky, ambiguous) with labels written before the run. Dev and test split.
- Configurations: single Muse Spark, two same-family members, three-family unanimous.
- Metrics: false approvals, false blocks, escalation rate, agreement and correlation between pairs (same family vs cross family), latency, cost per task.
- Repeats per case, reported as repeats.

## E5: Per-robot advisors

- Question: do the safety advisor and the organizer improve outcomes beyond the code-only system.
- Configurations: none, safety advisor only, organizer only, both. Same seeds.
- Metrics: near-miss count (separation below a threshold but above collision), false stops, tasks per hour, mean task time, LLM calls and cost per task, behavior under LLM outage.
- If an advisor does not change outcomes, that is the result.

## E6: Predictive maintenance

- Question: how early and how reliably does the system act on machine degradation.
- Setup: one machine, three failure modes (for example bearing wear, lubrication loss, misalignment), seeded hidden onset, noise. Simulator dynamics differ from the predictor model.
- Metrics: lead time between first action and failure, false alarms per 100 machine-hours, missed failures, wrong part orders, tickets per failure event, robots stopped before entering the hazard zone.
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

## Reproduction

```
make experiments-dev    # development seeds
make experiments-test   # held-out seeds, run once per configuration
make report             # regenerate tables and /experiments from result files
```

## Result file schema

`results/<experiment>/<run_id>.json`: commit, date, seed set, configuration, model ids, raw counts, derived metrics, failing seeds, notes.
