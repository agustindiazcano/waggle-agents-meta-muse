# Waggle Hive: Gotchas

Known traps. Each entry has a symptom and what to do. Prefer a test or a check that prevents the trap. Add new entries when a trap costs more than an hour.

## Template

### Short title
- Symptom: what you see.
- What to do: the fix or the rule.

## MCP and transport

### SSE: results arrive on the stream, and a rejected request can hang the client
- Symptom: the client waits forever after a call. The POST returned a 4xx, but the client is still listening for a result on the stream.
- What to do: the tool result and `tools/list` arrive on the SSE stream, not in the POST response. Open a new session for every attempt and set a read timeout, so a rejected request ends the attempt instead of hanging it.

### Exceptions inside the client session look like transport errors
- Symptom: an application error raised inside the MCP client session block surfaces as a generic transport failure.
- What to do: build model clients and do non-transport work outside the session block. To tell transport from application, write the smallest script that exercises only that connection and run it inside the failing container. If it passes, the bug is in the application flow.

### The server answers 421 behind the demo VM address
- Symptom: requests to the MCP server return 421 when the Host header is not one it expects, for example the public address of the demo VM.
- What to do: the host allowlist (DNS rebinding protection) is working as designed. Set the allowed hosts through configuration and keep the protection on. Do not disable it to make the demo work.

### `tools/list` is not filtered by identity over SSE
- Symptom: a restricted chassis sees tools it cannot call.
- What to do: this is a known gap of the transport. Execution stays gated by the identity allowlist, so the call is denied. Keep the gap listed in `docs/THREAT_MODEL.md` and in the README limits, and keep the test that a restricted identity cannot execute a tool outside its allowlist.

### Audit rows are asynchronous with SSE
- Symptom: a call has an intent row but no result row, or the other way around.
- What to do: write an intent row before forwarding and a correlated result row after execution, linked by the correlation id. Add a test that both rows exist for a completed call and that a failed intent write denies the call.

## Database

### `now()` is the start of the transaction
- Symptom: audit timestamps or latency values inside one transaction are identical or negative.
- What to do: `now()` returns the start time of the enclosing transaction. Use `clock_timestamp()` for audit and latency fields.

### pgvector operators
- Symptom: nearest-neighbor results look wrong, or ranking changes after a query rewrite.
- What to do: `<=>` is cosine distance and `<->` is L2 distance. Use the operator that matches the index operator class and the embedding normalization.

### A chunker splits a heading from its rules
- Symptom: retrieval returns a heading with no content, or rules with no heading, so a procedure loses its context.
- What to do: keep a heading in the same chunk as the text that follows it. Cover this with a test on a document where a heading falls at a chunk boundary.

## Experiments

### Throughput runs
- Symptom: throughput numbers change a lot between runs, or workers restart in the middle of a measurement.
- What to do: pause workers with `docker pause` instead of stopping them, prefill the queue, then unpause together. Report the median and the range over several runs.

### Model verdicts drift and repeats are not independent
- Symptom: the same case gets a different verdict hours later, and repeating a case inside one run looks like extra evidence.
- What to do: repeats inside one run are not independent samples, so count cases, not repeats. Check verdict drift across runs hours apart at least once, and report it. Never repeat a vote to correct a verdict.

### A guard and a court member from the same provider fail together
- Symptom: an outage or a rate limit removes the input guard and a court member at the same moment.
- What to do: plan for the shared failure. Fail closed on untrusted input when the guard cannot score it, and escalate when a court member times out. Record the providers of each layer in the result file.

## Governance

### An async classifier can swallow timeout cancellation
- Symptom: an adapter catches `CancelledError` and returns benign after its deadline.
- What to do: cooperate with cancellation and retain the explicit `deadline.expired()` check in the guard. The regression test rejects that late response. Async deadlines cannot interrupt blocking code in the event loop, so future provider adapters also need transport timeouts. See the [Python timeout contract](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.timeout).

## Git and pull requests

### Merging a stacked pull request chain in the wrong order loses work
- Symptom: every PR of a stack shows as merged, but main lacks most of the commits. PR 5 was merged into main first, then PRs 6 to 14 were merged into their stacked base branches, which were already closed with respect to main. `main` was 36 commits behind the top of the stack.
- What to do: merge a stack from the top down, or retarget each PR to main before merging it. After merging, run `git rev-list --count origin/main..origin/<top-branch>`: it must be 0. If it is not, open one PR from the top branch to main.

## Docker

### Healthchecks that start a heavy process keep an idle service busy
- Symptom: an idle container uses CPU or memory in a steady pattern, and the check itself can time out.
- What to do: use light checks, such as a short Python call to a health endpoint. Avoid checks that load the application or the model client.

## Coordination

### Lease expiry is not physical clearance
- Symptom: a stopped robot loses its lease but still occupies a capacity-one aisle, and a replacement would be admitted into it.
- What to do: use the corridor model with a current trusted occupancy observation. An expired occupied or unknown zone keeps `FAULT_OCCUPIED`; only a current empty observation permits reassignment. Never use the generic logical lease expiry as an entry permit. Tests cover a robot that never releases, an occupied expired corridor and missing occupancy (ADR-031).

### S03 admission needs staging and a clear exit
- Symptom: the original S03 has both robots already inside the reserved aisle, so admission cannot resolve it; parking on the incoming path can also leave the unchanged fast layer holding the opponent outside.
- What to do: retain the original S03 for E1 comparisons and use the explicit `build_s03_admission` integration fixture for before-entry admission. Start at rest outside the zone, request the entire route, and park clear of the opposite approach before release. Keep expired occupied zones faulted. The integration test checks both completed routes, footprint occupancy and the independent collision detector. Admission state is in simulator arrays, but the existing sensor and control rig also holds Python state; do not infer full rollout fork support from the admission-only replay test.

### A route can cross corridors with different fixed orientations
- Symptom: a valid multi-corridor route is denied because one direction was applied to every capacity-one zone.
- What to do: use the route planner's `directions_by_resource` in the complete `CorridorRequest`. The uniform `direction` argument is retained for legacy requests only. Every resource still has to be granted atomically before motion.
