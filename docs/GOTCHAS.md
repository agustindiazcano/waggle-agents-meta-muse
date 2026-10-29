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

## Docker

### Healthchecks that start a heavy process keep an idle service busy
- Symptom: an idle container uses CPU or memory in a steady pattern, and the check itself can time out.
- What to do: use light checks, such as a short Python call to a health endpoint. Avoid checks that load the application or the model client.
