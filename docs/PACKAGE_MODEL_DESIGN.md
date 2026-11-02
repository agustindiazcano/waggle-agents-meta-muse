# Package model design

Status: proposed, nothing is implemented. This is the design decision requested by PENDING.md row 92, with context from rows 85 and 86 (ADR-050, ADR-051). The maintainer decides; an agent builds it later, branch by branch.

## 1. What exists and what is missing

| Item | State | Source |
| --- | --- | --- |
| `pick_package` and `deliver_package` schemas (`task_id`, `package_id`, plus `zone_id` for delivery) | Exists. `package_id` is a bounded identifier, `^[A-Za-z0-9_.-]{1,64}$` | `src/waggle/mcp_server/schemas.py`, `src/waggle/db/schema.py` |
| Allowlist and forwarder queue the order after identity, schema, rate limit and audit intent | Exists | `src/waggle/mcp_server/forwarder.py`, ADR-050 |
| Delivery checks that the caller holds a live lease on the zone; the fencing token is not a tool argument | Exists | ADR-050 |
| `motion_orders` queue, one pending order per robot, `resolve(done or failed)` | Exists | `src/waggle/db/motion.py`, ADR-050 |
| `MotionExecutor` runs `move_waypoint`; package orders resolve `failed` at once | Exists | `src/waggle/experiments/sim_motion.py`, ADR-051 |
| Package ids checked against any registry | Missing. ADR-050 says none exists | ADR-050 |
| Package state in the simulator (position, holder, status) | Missing | `src/waggle/sim/state.py` holds named numpy arrays only |
| Zone kinds `station` and `depot` exist in the world format | Exists, usable as pick and drop places | `src/waggle/sim/world.py` |
| Handoff of a task through a zone (atomic, fenced) | Exists, moves no goods | ADR-043, ADR-044 |
| Package label text path | Missing. Threat model lists labels as untrusted input (T1, T18) | `docs/THREAT_MODEL.md` |

Conflict noted: the task description for this design mentions a fencing token on delivery, while ADR-050 states that the fencing token is not an argument of these tools and that the lease holder and expiry are checked. This design follows ADR-050 and does not add a token argument (see decision 6).

## 2. Design choices

### 2.1 Where package state lives

| Option | Trade-offs |
| --- | --- |
| A. Simulator only, loaded from the scenario | Simple, deterministic, forks and snapshots copy it for free. No registry, so `package_id` cannot be validated by the server |
| B. PostgreSQL registry only | Server can validate ids. The simulator would need the database, which breaks determinism and the import contract for `waggle.sim` |
| C. Two parts: pure model in the simulator owns truth; a registry table holds the declared catalogue of ids and is read by the server | The simulator stays pure and deterministic. The server can check an id exists before queueing. Needs a migration and a loader that publishes the scenario packages |

Recommendation: C. The simulator owns ground truth (AGENTS.md 5.4), the registry only declares which ids are valid and never says where a package is. The server never writes package location.

### 2.2 Identity and registry of `package_id`

| Option | Trade-offs |
| --- | --- |
| A. Free text id, accepted if it matches the regex | Today's behavior. An unknown id is only found by the simulator, after queueing |
| B. Registry table `packages(package_id, created_tick, source)` filled by a separate scenario load script, checked in the forwarder before enqueue | Matches AGENTS.md 4 and 8.7 (ids checked in code, sample data loaded by scripts, not by a migration). Fails closed on an unknown id |
| C. B plus a foreign key from `motion_orders.package_id` to the registry | Strongest integrity. Existing rows and tests with free ids need a migration path |

Recommendation: B first, C in a later migration after the maintainer approves it (AGENTS.md 15: migrations need approval). A registry miss is a denial that does not say which check failed, like the other refusals in ADR-050.

### 2.3 Lifecycle and legal transitions

States: `AT_STATION`, `HELD`, `DELIVERED`, `LOST`. In transit is `HELD` while the holder moves; a separate state adds nothing the holder position does not already say.

| From | To | Cause | Check |
| --- | --- | --- | --- |
| `AT_STATION` | `HELD` | `pick_package` executed | Preconditions in 2.4 |
| `HELD` | `DELIVERED` | `deliver_package` executed inside a drop zone | Preconditions in 2.4 |
| `HELD` | `AT_STATION` | Holder removed by a fault (robot failed, E2 chaos) and the package is released at the last pose | Model rule, deterministic |
| `HELD` | `LOST` | Holder drops it outside any station or depot zone | Model rule |
| `DELIVERED`, `LOST` | none | Terminal | Any further order resolves `failed` |

Every other transition is refused and the order resolves `failed`. A package is never created or removed after the scenario load (conservation).

### 2.4 Pick and deliver preconditions

All are evaluated by the simulator at execution time, on ground truth, never from the order text.

| Check | Pick | Deliver |
| --- | --- | --- |
| Robot exists in the simulation, no active order | Yes (as ADR-051) | Yes |
| Package status | `AT_STATION` | `HELD` by this robot |
| Robot pose | Inside the zone where the package lies, within a pick radius (assumption to calibrate) | Inside the order's `zone_id`, which must be of kind `station` or `depot` |
| Robot speed | At most a pick speed bound (assumption to calibrate) | Same bound |
| Capacity | Robot holds fewer packages than its chassis capacity (new parameter, one per class, assumption to calibrate) | Not applicable |
| Zone lease | Not required by ADR-050 for pick | Already checked at queue time (ADR-050); the simulator also checks pose |
| Idempotency | A repeated order id never executes twice; `resolve` returns False on a second resolve (`OrderQueue` contract). A repeated pick of an already held package resolves `failed`, not a second pick | Same |
| Missing or unknown value (pose not finite, unknown zone, unknown package) | Fails closed: `failed` | Fails closed: `failed` |

Both tools resolve `done` in one tick if the checks hold, else `failed`; there is no motion, because the robot must already be in place (a `move_waypoint` order precedes it). Whether pick should instead drive the robot to the package is decision 3.

### 2.5 Interaction with the handoff and the MotionExecutor

| Point | Design |
| --- | --- |
| Handoff of ADR-044 | Unchanged. The handoff completes a task on zone evidence and moves no goods. Delivery of a package into a handoff zone is a separate order and does not complete the task. Completion rules, ACK and retry logic stay as they are |
| MotionExecutor | Gains a `PackageModel` dependency. `_start` dispatches `pick_package` and `deliver_package` to the model instead of resolving `failed` unconditionally. Executor still runs only in the live simulation, never in a rollout fork |
| Rollout forks | The package arrays are part of the snapshot, so a fork predicts with the same goods, but forks never execute orders (ADR-051) |
| Fast layer | Unchanged. Holding a package can only reduce motion, never widen it (AGENTS.md 5.3); a payload may later lower the speed cap, which is a restriction |

### 2.6 Failure modes per component

| Component | Mode | Reason |
| --- | --- | --- |
| Registry check in the forwarder | Fail closed | Unknown, malformed or unreadable id denies the call |
| Package model in the simulator | Fail closed | Any failed precondition resolves `failed`; nothing is reported done that did not happen (ADR-051) |
| Registry loader script | Fail closed | A duplicate or malformed id aborts the load |
| Package events in tracing and viewer overlays | Fail open | Never blocks the control path |
| Audit intent and result rows | Unchanged | Audit logic is not touched |

### 2.7 Label text path (untrusted)

Labels are a field of the scenario package, read only by the vision and ticket flows, never by the simulator logic, so no label text can influence a precondition.

| Step | Design |
| --- | --- |
| Storage | Label text is stored with the package record for the viewer and vision flows, not in the pick or deliver order |
| Before any model | It passes the sanitizers and the guard as an `UntrustedSource` (ADR-052), with a length cap. If screening cannot score it, reject and escalate (AGENTS.md 8.6) |
| After the model | Output is validated against a strict schema. A label cannot name an id, a zone or a tool; the order `package_id` comes only from the authenticated robot's plan, checked against the registry (AGENTS.md 8.7) |
| Evaluation | E3 injection cases T1 and T18 already include package label text as a source; a package-label case set is added there |

## 3. Invariants and tests

Property tests over seeded runs (same seed gives the same result), failure-path tests first.

| Invariant | Test |
| --- | --- |
| No double pick | Two picks of one package, same or different robots, give one `done` and one `failed` |
| No delivery of an unpicked package | `deliver_package` on an `AT_STATION` package resolves `failed` |
| No package held by two robots | After any tick, each package has at most one holder; a fuzz over random order streams keeps this |
| Conservation | Count of packages over all states is constant; `DELIVERED` and `LOST` are terminal |
| Capacity | A pick over capacity resolves `failed` |
| Position and speed | A pick far from the package, or above the speed bound, resolves `failed` |
| Fail closed | NaN pose, unknown package, unknown zone and unregistered id all resolve `failed` or deny |
| Idempotency | A replayed order id does not change state a second time |
| Determinism | Two runs with the same seed and orders have equal canonical state hashes |
| Fork isolation | Orders in a fork do not change the live package arrays |
| Import contract | `waggle.sim` package module imports no `llm`, `governance`, `maintenance` or `mcp_server` (import-linter) |

## 4. Build order (stacked branches)

Each branch writes the failing test first, then the minimum code. Cloud first for anything long (AGENTS.md 3.8).

| # | Branch | Content | Depends on | Evaluation |
| --- | --- | --- | --- | --- |
| 1 | `docs/package-model-design` | This document and the maintainer decisions | none | not applicable |
| 2 | `feat/package-model-core` | Pure `waggle.sim.packages`: state arrays, transitions, preconditions, invariants, hash inclusion | 1 | Implemented, not evaluated |
| 3 | `feat/package-scenario-load` | Scenario field for packages and stations, world format validation, deterministic placement from the seed | 2 | Implemented, not evaluated |
| 4 | `feat/package-executor` | `MotionExecutor` dispatches package orders to the model; fork isolation test | 2, 3 | Implemented, not evaluated |
| 5 | `feat/package-registry` | Registry table (migration, needs maintainer approval, check current revision first), repository, loader script, forwarder check before enqueue | 1, decision 2 | Implemented, not evaluated |
| 6 | `feat/package-label-path` | Label field, sanitizer and guard integration, schema for any model output | 3, ADR-052 | E3 (injection through package labels), once the E3 runners cover the untrusted-data boundary |
| 7 | `test/package-e2e-slice` | One cloud test: queue, executor, model, resolve, over the real PostgreSQL | 4, 5 | Test only, like ADR-044 |
| 8 | `exp/package-throughput` | Delivered packages per run with the layers on and off, same seeds, Wilson intervals | 7 | E2 (chaos with killed workers) and E10 (crisis replanning), only if the maintainer wants goods as an outcome metric |
| 9 | `feat/package-viewer-overlay` | Held and delivered markers in the technical viewer | 4 | Not evaluated |

Branches 2 to 4 can start without the registry. Branch 5 is the only one that needs a migration.

## 5. Decisions for the maintainer

| # | Question | Recommendation |
| --- | --- | --- |
| 1 | Where does package state live? | Option C: pure model in the simulator, registry table for ids only (2.1) |
| 2 | Add the registry check now, and add the foreign key later? | Check in the forwarder first (branch 5), foreign key in a later migration |
| 3 | Does `pick_package` move the robot, or require it to be in place already? | Require it in place; a `move_waypoint` order comes first. Simpler and testable |
| 4 | Should a held package lower the robot speed cap? | Not in this design; it can only restrict, so it can be added later with its own experiment |
| 5 | Is a fault on a holding robot `AT_STATION` or `LOST`? | `AT_STATION` at the last pose, so conservation is visible; `LOST` only for an explicit drop |
| 6 | Add a fencing token argument to `deliver_package`? | No; keep ADR-050 (lease holder and expiry), since the task says not to change fencing |
| 7 | Are goods part of an outcome metric in E2 or E10 (branch 8)? | Yes, but as an added metric, with its own baseline |

## 6. Not claimed by this design

This design claims no implementation, no measured result and no experiment. It makes no claim of physical grasping, payload dynamics, hardware real-time behavior, standards compliance or large-fleet performance. Pick radius, speed bound and capacity are assumptions to calibrate. The registry says which ids are valid and nothing about where a package is. The label path reduces injection risk only as far as an E3 result will later show. The viewer overlay and the throughput metric are proposals, not evaluated.
