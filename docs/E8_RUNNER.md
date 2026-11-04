# E8 latency and cost runner

Implemented, not evaluated for provider latency, provider cost or real fleets.
This runner never calls a provider and needs no paid credentials. It adds no
dependency and changes no production safety behavior. Existing README numbers
remain backed by their original files.

## Production control code latency

Run the `Waggle Hive E8 code latency benchmark` workflow. It runs on E8 pull
requests and supports manual dispatch after merge. Three jobs repeat the same
fixed synthetic S01 benchmark, including the existing occlusion, CPA and beacon
configuration. The benchmark does not load development or held-out seed lists.
The files live under `results/e8/dev` for compatibility with the artifact layout,
but `seed_set` is explicitly `benchmark` rather than an evaluation seed set.

The measured timer is the existing `ControlRig` timer around production
`control_step`. Sensor generation, simulator physics and networking are outside
it. Warmup ticks are discarded. Each JSON gives the machine, commit, date,
configuration, scenario, seed, tick counts, call count and nearest-rank p50/p95/p99
in seconds. Repeats are separate artifacts, not independent scenario samples.
This is code latency inside the simulator, not a hardware real-time guarantee.
One scenario does not characterize the complete E1 workload.

Equivalent cloud command:

```powershell
uv run python -m waggle.experiments.e8_run fast --ticks 200 --warmup-ticks 20 --output results/e8/dev/control.json
```

Ticks and warmup are bounded at 100000 each; the workflow also has a timeout.
Every output is opened exclusively and an existing file is never replaced.
Only the maintainer commits result artifacts.

## Call-log reports

Export only metadata rows from `llm_calls`, keeping each mode in a separate
export. Exporting production database rows is a separate operator step; the
runner does not access a database or inspect credentials. Supply the source
commit and prompt versions from the run manifest. The parser cannot authenticate
caller-supplied provenance. No prompt or response text is accepted.

The input has exactly five keys:

```json
{
  "source": "llm_calls",
  "mode": "http",
  "commit": "source-run-commit",
  "prompt_versions": {"advisor": "version-from-run-manifest"},
  "records": [
    {
      "request_id": "request-from-table",
      "task_id": "task-from-table",
      "role": "advisor",
      "provider": "meta",
      "model_id": "model-from-table",
      "status": "ok",
      "tokens_in": 1,
      "tokens_out": 1,
      "latency_s": 0.25,
      "cost_usd": 0.001,
      "fallback_label": null
    }
  ]
}
```

The values above illustrate the schema and are not measurements. `mode` must be
`http` or `mock`; task and fallback identifiers may be null. Unknown fields,
missing provenance, empty samples, unknown statuses and invalid numeric values
raise errors. Prompt versions are mandatory even for mock exports.

```powershell
uv run python -m waggle.experiments.e8_run calls --input calls-export.json --output results/e8/dev/calls.json
```

Summaries preserve every row, repeated request identifiers, fallback labels and
the four statuses. Only `ok` rows contribute provider latency, token totals and
cost, matching the current `PostgresCallLog.cost_by_task` convention. Error,
denied and cached counts remain visible. A group with no successful calls has
null latency. Null task identifiers have a separate cost entry. Costs and
latency are grouped by role, provider and realized model. Mock mode remains
explicit and cannot be treated as evidence of provider performance or pricing.

## Finite-burst extrapolation

```powershell
uv run python -m waggle.experiments.e8_run calls --input calls-export.json --fleet-size 1000 --calls-per-robot 1 --concurrency 10 --seed 0 --output results/e8/dev/extrapolation.json
```

Extrapolation requires exactly one provider/model/role combination. Split the
export before invoking it when routes differ. Successful rows supply measured
latencies; the error fraction over successful and error rows supplies the
failure probability. Production error latencies are unmeasured and stored as
zero. Failed-call durations therefore use the successful-call distribution as
an explicit modeling assumption, never those placeholder zeros. Denied and
cached rows are excluded from attempted calls. A source with no attempted calls
or no positive successful latency raises an error. Failed calls consume sampled latency.
All calls arrive at time zero, workers take the next call immediately, and each
latency and failure is sampled independently with a local seeded generator.
No retries or per-robot dependency order are modeled. At most 1000000 calls are
simulated. The same inputs and seed reproduce the same extrapolation.

The JSON labels the result `extrapolation`, records all inputs and raw counts,
and lists assumptions and unvalidated effects: rate limits, queue arrival
processes, correlations, network/database contention and hardware performance.
It does not validate large-fleet performance. A mock source produces a synthetic
extrapolation only. A sampled burst with zero duration has null throughput.

Remaining E8 work includes reviewed production exports, measurements by role
and model, representative workload coverage and calibration of the assumptions.
This runner does not close E9 mutation testing or authorize paid evaluations.
