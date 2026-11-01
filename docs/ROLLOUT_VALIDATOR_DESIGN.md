# Rollout validator and E10: design proposal

Status: proposed, nothing is implemented. This document orders and details ADR-023 (Phase 5C). It changes no rule, no number and no ADR. Planning does not authorize execution, paid calls or held-out evaluation. Dates and measured figures appear only where a source document records them.

Naming: simulation-based plan validation with counterexample feedback. It is not formal verification and not a safety proof. CEGIS and LLM-Modulo are prior art, to be cited after verification (PENDING row 28). The pattern is not claimed as new. Every result states its assumptions: the hidden human prior, the K variants and the horizon H.

## 1. What exists and what is missing

| Item | State | Source |
|---|---|---|
| Plan schema and `parse_plan` (frozen dataclasses, unknown fields rejected, ids checked against map, fleet, inventory) | exists | `src/waggle/validation/plan.py`, ARCHITECTURE.md Plan schema |
| Geofence check, one counterexample code `GEOFENCE_INTRUSION` (node, zone) | exists | `src/waggle/validation/geofence.py`, ADR-060 |
| E3 `plan_validator` runner for E3-T18-01 and 04 | exists, never run as an experiment, no result file | `waggle.experiments.e3_plan_validator`, ADR-060 |
| Engine `snapshot()`, `from_snapshot()`, `fork()` | exists | `src/waggle/sim/engine.py`, ADR-021, ADR-025 |
| `run_rollout(spec)`, `run_variants(specs, workers)`: scenario from seed, lidar on or off, returns detector counts and a state hash | exists, but takes a scenario id and seed, not a plan | `src/waggle/sim/rollout.py` |
| Reflex layer, occlusion cap, arbiter, CPA | exists | `src/waggle/control`, ADR-024, ADR-028 |
| Design basis for cost: K = 5, H = 45 s, lidar every 4 ticks, 5.7 s per rollout | decided, to run in the cloud | ADR-025 addendum, PENDING 31 |
| Plan to motion compiler (A* on the aisle graph, node to commands) | missing | ARCHITECTURE.md Plan schema describes it |
| Belief state, hidden human prior sampler, K variants | missing | ADR-023 |
| Counterexample types other than `GEOFENCE_INTRUSION`, with times, places, clearances | missing | ADR-023 |
| Progress and recoverable-terminal checks, in-memory lease logic in the rollout | missing | ADR-023, PHASE1_BRIEF item 6 |
| Planner loop (at most 3 rounds), crisis templates, E10 harness | missing | PLAN.md Phase 5C, EXPERIMENTS.md E10 |
| Import-linter contract for `waggle.validation` | missing (the package exists, the contract is to be checked) | PHASE1_BRIEF item 6 |

Gap in one sentence (PENDING row 99): the schema and the geofence check do not see the geometry of a path through open transit zones, the clearance to static structure, humans, or other robots, and cannot see deadlocks or lease conflicts.

Conflict noted, not expanded: the task description speaks of "dynamic obstacles via forked rollouts". ADR-023 says the validator does not fork ground truth and that snapshot and fork serve determinism tests and replay. This design follows ADR-023: variants are built from a belief state, and `fork()` is used only to branch a belief-state engine per variant. If the maintainer wants ground-truth forks, that is an ADR-023 change.

## 2. Options and recommendation

### 2.1 Validator scope

| Option | Catches | Misses | Cost | Verdict |
|---|---|---|---|---|
| A. Schema plus geofence only (today) | Unknown ids, hazard zones | Path geometry, clearance, humans, deadlock, leases | none | Insufficient for E10 |
| B. A plus static geometry (path against map and clearance, no dynamics) | Paths through walls or too narrow gaps, undeclared corridors (ROUTE_INFEASIBLE) | Robot-robot and human interaction, deadlock, progress | low, no rollout | Keep as the first stage inside the full validator |
| C. B plus one deterministic rollout without humans | Collisions between robots, separation, deadlock, lease conflicts, no progress | Unseen humans | about one rollout | Intermediate stage |
| D. C plus K human variants (ADR-023) | Everything in C and humans under the stated prior | Humans outside the prior, anything beyond H | K rollouts | Recommended end state |
| E. D plus an extended 120 s check | Late failures after the accepted horizon | none beyond the prior | more | Used as an E10 metric, not as an acceptance gate |

Recommendation: build D in stages B, C, D (section 8), so every stage is testable and useful alone. E runs only as an evaluation of accepted plans (EXPERIMENTS.md E10 metric), never as a loosened or widened gate.

### 2.2 Hidden human prior sampling

| Option | Trade-off |
|---|---|
| Uniform spawn over free map cells | Simple, but ignores declared scenario density and aisle use |
| Scenario density prior with occluded-region spawns (ADR-023) | Matches the declared density, covers humans behind occlusions. Needs a prior declared per scenario |
| Adversarial search over spawn points | Stronger, but it is search, not sampling, and its guarantee is hard to state |

Recommendation: the scenario density prior of ADR-023. Reject a sample at sampling when a human starts inside the minimum stopping distance of a robot at t = 0 (ADR-023). Record the rejected count in the result. The prior is declared in the scenario file, versioned, and written into every result. Adversarial search stays a later option, listed in "Not claimed".

### 2.3 K variants and aggregation

| Option | Trade-off |
|---|---|
| K = 5, accept only if all K pass (ADR-023, ADR-025) | Conservative, fixed cost, decided |
| Majority or quantile | Accepts plans that fail in some variants. Violates the ADR-023 rule and loosens a safety check. Not offered |
| Larger K for held-out only | More coverage, more cost, cloud only. Allowed as a sensitivity run, labeled |

Recommendation: K = 5, all-pass, as decided. Aggregation is a pure function: the plan passes only if the set of counterexamples across all K variants is empty. A variant that fails to run (error, timeout, missing value) counts as a failure, fail closed.

### 2.4 Horizon and pass criterion

| Option | Trade-off |
|---|---|
| H = 45 s, receding at H/2 (ADR-023, ADR-025) | Decided design basis, 5.7 s per rollout recorded |
| H = 30 or 60 s | Sensitivity runs of E10, reported, not a second default |
| Mission completion required within H | Rejected by ADR-023: completion is a metric, not a requirement |

Pass criterion (ADR-023, restated, no change): in every one of the K rollouts over [0, H], zero collisions, zero separation violations, zero hazard geofence intrusions, zero deadlocks, no lease conflict, feasible route, progress for every active robot, and a recoverable state at H. A plan with `escalate` set is routed to the operator and is not validated as motion.

## 3. Counterexample feedback to the planner

Types (ADR-023): COLLISION, SEPARATION_VIOLATION, GEOFENCE_INTRUSION, CORRIDOR_DEADLOCK, LEASE_CONFLICT, ROUTE_INFEASIBLE, NO_PROGRESS, UNSAFE_TERMINAL_STATE. The existing `Counterexample(code, node, zone)` grows into a frozen record; its three fields stay valid.

| Field | Content | Bound |
|---|---|---|
| `code` | One of the eight types | Closed enum |
| `variant` | Index 0 to K-1, or `none` for static checks | Integer |
| `time_s` | Simulation time of first occurrence | Float, seconds |
| `node` | Plan node label | Existing label only |
| `entities` | Robot ids, zone ids, and the kind `human` without a human identity | At most 4, ids checked against the map and fleet |
| `place` | Zone id, or x and y in metres | Numbers or known id |
| `min_clearance_m` | Smallest clearance reached | Float, metres |
| `rule` | Name of the violated rule | Closed enum |

Rules for the feedback message:
- It is built from typed fields by code. No field carries free text from the plan, from SOP text, from labels or from incident text. The plan `rationale` is never included (ADR-023).
- Ids are echoed only after a lookup in the trusted map and fleet. An unknown value is replaced by a fixed token.
- At most 5 counterexamples per round, ordered by time, then by severity (COLLISION first), then by variant. Excess is summarised as a count per code.
- The message is serialized as JSON with a fixed key order and treated by the planner side as data.
- The planner output is parsed again by `parse_plan`; the validator never trusts a repaired plan.

## 4. Loop bound

| Item | Rule | Source |
|---|---|---|
| Maximum rounds | 3 validations per incident (ADR-023). Each round is one plan and one validation | ADR-023 |
| Exhausted | Escalate to the operator. Affected robots hold safely (stopped outside shared capacity-1 zones, or holding valid leases) | ADR-023 |
| Receding horizon | Execute at most H/2, then revalidate from the new belief state | ADR-023 |
| Revalidation rounds | A new incident state starts a new 3-round budget. A per-incident cap on total revalidations is a maintainer decision (decision 5) | proposed |
| Planner failure | Timeout, schema rejection or provider error counts as a round, never retried inside the round beyond the LLM layer cap (AGENTS.md 6.3) | AGENTS.md 6 |
| Baseline | The deterministic recovery planner runs without the LLM and passes through the same validator | EXPERIMENTS.md E10 |

## 5. Determinism and seeding of variants

- Each variant seed is derived by code from the scenario seed, the snapshot RNG state and the variant index with a fixed hash. No wall clock, no network, no global random (AGENTS.md 5.5).
- A variant is a pure function of (belief state, plan, variant seed, parameters). `run_variants`-style process parallelism may reorder execution but not results; results are returned in variant order, as `run_variants` does today.
- Parallelism uses the standard library and is a cloud and speed matter only; a test compares workers = 1 against workers > 1 on the state hash.
- The predictor and the simulator share no equations or parameters (AGENTS.md 9.8). The validator rollout uses the production dynamics and the production reflex layer (ADR-023). The human prior is a sampling distribution and is not tuned on held-out seeds.
- The in-memory lease logic in the rollout is covered by the Hypothesis equivalence test already required in Phase 3 exit criteria (PHASE1_BRIEF item 6). If that test does not exist when the lease stage starts, the lease checks stop there and the maintainer is asked.

## 6. Failure modes (fail closed)

| Component | Failure | Behavior |
|---|---|---|
| Plan parser | Any schema or id error | `PlanRejected`, counts as a round, no echo of content |
| Geofence input | Hazard set missing or unreadable | Reject the plan, escalate |
| Path compiler | No path, undeclared corridor | `ROUTE_INFEASIBLE` with the zone |
| Belief builder | Tracker or map value missing | Reject, escalate. Never assume free space |
| Human sampler | Cannot produce K valid variants within a cap | Reject, escalate. Report the count |
| Variant rollout | Exception, timeout, state hash mismatch on replay | Variant counts as failed |
| Aggregator | Fewer than K results | Reject |
| Planner loop | Rounds exhausted, provider budget guard denies a call | Escalate to the operator, robots hold safely |
| Reflex layer inside the rollout | Unchanged. Nothing above it widens what it allows (AGENTS.md 5.3) | Rollout cannot be used to raise a speed cap |
| Tracing and logging | Fail open, never block validation | AGENTS.md 5.9 |

## 7. Cost and latency method

- No figure is invented. The recorded basis is ADR-025: K = 5, H = 45 s, lidar every 4 ticks, 5.7 s per rollout, a number measured on the repository code and recorded in PENDING 31.
- The new measurement is the whole validation call for 1, 5 and 10 robots: path compile, belief build, K rollouts, aggregation. It is measured with a monotonic timer around the call and reported as code latency inside the simulator, with workers used, CPU model and commit (AGENTS.md 9.9, ADR-028).
- Wall time for 3 rounds is derived from the measured per-call figure; any fleet size beyond the measured scenes is labeled extrapolation with assumptions listed.
- The measurement runs in a new `workflow_dispatch` workflow on a GitHub-hosted runner (AGENTS.md 3.8, 3.9). Reducing K, H or lidar rate is allowed for the live demo only and is labeled (ADR-025 addendum).
- If the measured cost makes the loop doubtful, work stops and the maintainer is asked (ADR-025 consequence).

## 8. Composition with the geofence check and the reflex layer

| Stage | Check | Order |
|---|---|---|
| 1 | `parse_plan` | First |
| 2 | `check_geofence` against the trusted hazard set | Cheap, always before any rollout |
| 3 | Static geometry: path, clearance, undeclared corridors | Before any rollout |
| 4 | K rollouts with the production reflex layer and lease logic | Only if 1 to 3 pass |
| 5 | Aggregation and progress and terminal-state checks | Last |

The geofence check is not replaced (ADR-060). It stays as stage 2 and keeps its E3 role. The rollout contains the reflex layer, so a plan that relies on the reflex layer to avoid a human is accepted only when the reflex layer does avoid it in all K variants. At execution the reflex layer still runs and can only reduce motion. An accepted plan is a check under stated assumptions, not a replacement for it.

## 9. E10 evaluation protocol

| Item | Proposal |
|---|---|
| Scenarios | Compound-fault templates of EXPERIMENTS.md E10 (thermal geofence, blocked aisle, robot dead mid hand-off, urgent orders by text), each with a text incident report. Each template declares its target layer before the run (AGENTS.md 9.4) |
| Configurations | The four of EXPERIMENTS.md: deterministic recovery baseline; Muse open loop; Muse with validator feedback; Muse with validator feedback and the role-specialized court |
| Validator-disabled baseline | Muse open loop is the validator-disabled arm. A shadow arm runs the validator on open-loop plans without feeding back, to measure false accepts of plans that later fail |
| Ablation | Add stages one by one on the same seeds: geofence only, plus static geometry, plus one rollout, plus K variants. Contribution is measured by ablation, not by summing blocks (AGENTS.md 9.3) |
| Same seeds | All arms use the same scenario seeds and the same execution seeds |
| Ground truth of failure | Execution in the simulator with the ground-truth human, and an extended 120 s rollout (EXPERIMENTS.md) |
| Metrics, first | False accepts: accepted plans that produce a collision, separation violation or geofence intrusion in execution or in the 120 s rollout, with raw counts. Then false rejects (plans the baseline executes safely), violations in validation and in execution, deadlocks, recovery time, rounds, calls, cost, escalations |
| Statistics | Proportions with Wilson 95 percent intervals and raw counts. Small samples called small. Failing seeds listed. LLM repeats reported as repeats, not independent samples (AGENTS.md 9.5, 9.7) |
| Sensitivity | H in 30, 45 and 60 s, and K in 1, 5 and 10 (K sweep is an addition, labeled) |
| Seeds | Development seeds while building. Held-out seeds run once per configuration, in the cloud, committed by the maintainer (AGENTS.md 9.1, 9.2). Seeds are split before tuning; the human prior is not tuned on held-out |
| LLM calls | Real-model arms run only in the cloud workflow, with the mock provider for tests and with spend caps checked first (AGENTS.md 3, 14) |
| Result file | commit, date, seed set, configuration, model ids, prompt versions, K, H, lidar rate, human prior id and version, variant seeds rule, raw counts, derived metrics with intervals, failing seeds, rejected-sample counts, latency method and runner, notes (AGENTS.md 9.6) |
| Reporting | State what the LLM adds per template, including when it adds nothing. State that validation is simulation-based under the stated prior |

## 10. Invariants and failure-path tests (write first)

| Test | Checks |
|---|---|
| Sensitivity, planted unsafe plan | A plan that drives a robot through a planted human variant, a wall gap narrower than the footprint, or two robots into one capacity-1 corridor is rejected with the expected code. The same plan with the planted fault removed is accepted |
| Mutant validator | A test double that accepts every plan is run through the same suite and must fail the sensitivity tests. The suite asserts that it fails |
| Mutant on aggregation | An aggregator that accepts when K minus 1 variants pass must fail a test where one variant fails |
| Determinism | Same plan, belief and seed give the same counterexamples and state hashes; workers = 1 equals workers > 1 |
| Fail closed | Missing hazard set, missing track, fewer than K results, variant exception each yield rejection, never an empty pass |
| Bounded loop | A planner stub that never fixes the plan stops after 3 rounds and escalates |
| Feedback hygiene | Injected text in rationale, labels and incident text never appears in the feedback; unknown ids are replaced |
| No widening | A plan cannot raise a speed cap or shrink an envelope; the rollout and execution reflex output agree on the same inputs |
| Import contract | `waggle.validation` imports no LLM, governance or MCP server module; `waggle.sim` and `waggle.control` do not import it |
| Coverage of E3 | E3-T18-01 and 04 results are unchanged after the full validator is added |

Order of test writing in every branch: failing test first, shown failing for the right reason, then the minimum code (AGENTS.md 2.2).

## 11. Build order (stacked branches)

| Branch | Content | Depends on | Runs in cloud |
|---|---|---|---|
| `feat/validation-counterexample-types` | Frozen counterexample record, enum, bounded feedback serializer, hygiene tests, import-linter contract | `main` with ADR-060 present (PENDING 100 done) | no |
| `feat/validation-path-compiler` | Plan node to path (A* on the aisle graph, avoid and corridor rules), clearance, ROUTE_INFEASIBLE | previous | no |
| `feat/validation-belief-state` | Belief builder from static map and tracked entities, human prior sampler, K seeds, rejected-sample count | previous | no |
| `feat/validation-plan-rollout` | Plan-driven rollout over an engine fork with reflex layer, detectors to counterexamples, aggregation, progress and terminal checks, mutant tests | previous, lease-equivalence test | cost measurement only |
| `feat/validation-latency-workflow` | `workflow_dispatch` measurement of the whole call | previous | yes |
| `feat/crisis-planner-loop` | Versioned planner prompt, 3-round loop, escalation, mock provider tests | rollout branch, `waggle.llm` | no (mock) |
| `exp/e10-harness-dev` | Templates with incident reports, four configurations, shadow arm, result writer | loop branch | development runs yes |
| `exp/e10-sensitivity` | H and K sweeps, 120 s check | harness | yes |

Held-out E10 runs happen once, after the maintainer approves, and the maintainer commits the files. Each branch ends with ruff, mypy --strict, tests, import-linter and a failure-path test (AGENTS.md 16).

## 12. Decisions for the maintainer

| N | Question | Recommendation |
|---|---|---|
| 1 | Build the full rollout validator at all, and when? | Yes. Full scope stays (PENDING 99 is a decision, not a cut). Start with the first two branches now, they need no rollout and no spend; the rollout branches follow Phase 5A and 5B. G4 (Nov 2) requires E10 on development seeds, so order the branches as in section 11 |
| 2 | Is stage B (static geometry) accepted as an early, standalone gate before the rollout exists? | Yes, labeled "implemented, not evaluated" until E10 runs |
| 3 | Human prior: scenario density with occluded spawns, who declares the density per scenario? | ADR-023 prior, declared in each scenario file and reviewed by the maintainer |
| 4 | Ground-truth forks versus belief-state variants (conflict with the task wording) | Keep ADR-023: belief state, no ground-truth fork |
| 5 | Cap on total revalidations per incident beyond 3 rounds | Add a cap, proposed value to be set by the maintainer after the latency measurement |
| 6 | Add the shadow arm (validator on open-loop plans, no feedback) and the K sweep to E10? | Yes, they measure false accepts directly. They are additions to EXPERIMENTS.md and need approval |
| 7 | Cloud workflow for the latency measurement and E10 dev runs | Approve a new `workflow_dispatch` workflow; runs stay cloud only |

## 13. Not claimed by this design

- Not formal verification, not a safety proof, no guarantee beyond the hidden human prior, the K variants and the horizon.
- No claim that CEGIS or LLM-Modulo are covered; citations are to be added after verification (PENDING row 28). No novelty claim for the pattern.
- No latency, throughput or cost figure for the new validator. Only the ADR-025 basis is quoted, as recorded.
- No claim about large fleets, hardware real-time behavior, standards compliance or certification.
- No claim that an accepted plan is safe in execution; that is what the E10 false-accept metric measures, and the reflex layer remains the safety layer against humans.
- No result: no harness, no run, no held-out seed was touched in writing this document.

## 14. Not read

Not read: result JSON, lockfiles, `.venv`, the full `DECISIONS.md` beyond ADR-023, 025, 028, 060 and the snapshot and replay passages found by search, `MULTI_WAREHOUSE_PLAN.md`, `E2_CHAOS_DESIGN.md`, the body of `e3_plan_validator.py`, `data/e3/cases.json` beyond its T18 ids, the rest of `THREAT_MODEL.md` beyond the T18 rows, and the internals of `src/waggle/control` and `src/waggle/sim` beyond file lists and `rollout.py`. Existing docs tests were not read except for names.
