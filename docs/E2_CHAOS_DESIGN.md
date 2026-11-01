# E2 chaos harness: design

Status: proposed. Nothing in this file is implemented. It extends the E2 protocol in `docs/EXPERIMENTS.md` and does not change it. The harness only drives existing code; it changes no ACK, retry, fencing or audit logic.

## What exists and what is missing

| Part | State |
|---|---|
| Pure lease model, corridor model, task model | Done, unit tested |
| PostgreSQL repositories (`TaskRepository`, `CorridorRepository`), SKIP LOCKED claim and recovery, fenced handoff | Done, correctness tests in `postgres.yml` |
| S03 simulator admission ablation | Done, workflow `e2.yml`, not dispatched |
| 500 tasks, killed workers, early expiry, duplicate delivery, database delay | No harness |
| Baseline without fencing | No code |
| Independent oracle that counts double assignments and stale writes | No code |
| S13 to S18 deadlock counts, handoff chaos S31 to S35 | No code |

## Design

### Runs

One run is one fresh database, the schema at the latest revision, 500 tasks and a seeded fault schedule. A run ends when every task is `DONE` or exhausted, or at a tick horizon. Workers are real OS processes, each with its own `Database`, so the locks are the real ones. The seed fixes the schedule (which worker is killed at which step, which lease expires early, which request id is replayed, how long each database call is delayed). It does not fix the operating system scheduling, so two runs with the same seed can differ. The report says so and treats repeats as repeats, not as independent samples (AGENTS.md 9.7).

### Faults

| Fault | How it is injected | Where |
|---|---|---|
| Kill a worker at a random point | The handler and the `complete` callable run behind a kill-point hook chosen from the seed (after claim, after start, inside the handler, before complete, after complete). The process then exits with `os._exit`, so no `finally` runs | Harness handler, not production code |
| Expire a lease early | A worker's `now_tick` jumps forward by a seeded amount, so its attempt looks expired to recovery | Harness clock |
| Duplicate delivery | The same `request_id` and the same stale credential are sent again, during and after recovery | Harness client |
| Delay the database | A wrapper around `Database.transaction` sleeps a seeded time before entering and before commit | Harness wrapper |
| Drop the network | Not in the first version. A killed connection mid-transaction is covered by the kill points | Later |

Ticks come from one shared monotonic source for all workers (the trusted tick table of ADR-041), so only the injected clock jumps differ.

### Oracle

The counts are computed from the database event log and the final rows, never from the answers the repositories gave during the run. Where the log cannot decide, the run is reported as undecided, not as a pass.

| Metric | Computed from |
|---|---|
| Double assignment | Two attempts of one task whose live intervals (claim tick to expiry or end) overlap |
| Stale-token write accepted | An accepted `start`, `complete` or `fail` event whose token is below the task's token at that time |
| Two robots in a one-lane zone | Corridor transitions and trusted occupancy samples: two holders at the same tick on a capacity-one zone |
| Tasks recovered, tasks stuck | Final state of each task against the horizon |
| Recovery time | Ticks from lease expiry to the next claim of that task |
| Deadlocks | Not in this part. They need the S13 to S18 simulator scenes and stay in the simulator component |

### Baseline

The baseline checks the lease outside the tool and carries no token: a worker reads the task, checks expiry in its own process, then writes in a second transaction. It is a subclass of `TaskRepository` that lives in `waggle.experiments` and is never importable from the production path. It must show nonzero counts; if it shows zero, the harness is not sensitive enough and that is reported first. Production code is not edited.

### Statistics and files

Trials are runs. Proportions with Wilson 95 percent intervals and raw counts, failing seeds listed, small samples called small (AGENTS.md 9.5). Event counts (for example total stale writes accepted) are reported next to the run proportions. Result file `results/e2/dev/chaos_<configuration>_<date>.json` with exclusive creation. It records commit, seed set, seeds, worker count, task count, fault parameters, Python, platform, PostgreSQL image and schema revision, and zero LLM calls. Held-out seeds run once per configuration in the cloud; the maintainer commits the result.

### Cloud workflow

A new `workflow_dispatch` workflow `e2_chaos.yml` with the PostgreSQL service container of `postgres.yml`, a `seed_set` input limited to development, and a job timeout. No provider keys. Nothing runs locally except the unit tests of the oracle and the fault schedule, which use no database.

## Build order

| Step | Branch | Content | Depends on |
|---|---|---|---|
| 1 | `feat/e2-oracle` | Oracle over an event log, unit tested with hand-built logs, including logs that contain each violation | none |
| 2 | `feat/e2-fault-schedule` | Seeded schedule of kills, clock jumps, replays and delays, pure and tested | none |
| 3 | `feat/e2-no-fencing-baseline` | Baseline repository in `waggle.experiments`, test that the oracle counts its stale writes | 1 |
| 4 | `feat/e2-chaos-runner` | Worker processes, kill-point hook, delay wrapper, run loop, result file | 1, 2, 3 |
| 5 | `ci/e2-chaos-workflow` | `e2_chaos.yml`, cloud run on development seeds | 4 |
| 6 | `feat/e2-handoff-chaos` | S31 to S35 handoff chaos with its own no-fencing baseline | 4 |

## Decisions for the maintainer

| # | Question | Recommendation |
|---|---|---|
| 1 | Real OS processes with `os._exit` kill points, or in-process simulated kills | Real processes. In-process kills skip the lock release a real crash causes. Cost: results are not bit-exact per seed |
| 2 | Is a no-fencing subclass in `waggle.experiments` acceptable | Yes, with a test that it cannot be imported from `waggle.worker`, `waggle.db` or `waggle.mcp_server` |
| 3 | Worker count and horizon | 8 workers, 500 tasks, horizon 20000 ticks, as assumptions to calibrate on development seeds |
| 4 | The workflow creates a fresh database per run from the schema functions | Same pattern as `postgres.yml`. Say if a migration approval is needed for this |
| 5 | Number of development runs per configuration | 30, so the interval is not wider than needed. Small by any standard; the report says so |

Not claimed by this design: that fencing is correct under real network partitions, that the 500-task result extends to a larger fleet, or that a zero count proves absence of a race. A zero is a count over the runs that happened.
