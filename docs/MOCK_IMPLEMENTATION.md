# Waggle Hive: Mock implementation sequence

Maintainer authorization: on 2026-10-31 the maintainer approved the remaining implementation plan, including database implementation and migrations, fencing, audit and MCP wiring. Use the mock provider. This does not authorize paid calls, held-out execution, new spend caps or secret changes. E3 labels remain a maintainer decision. Human review and merge remain required. No scope is removed.

## Implementation order

Each row is split into reviewable task branches. Tests include successful paths and rejection or recovery paths. An implemented harness is not an experiment result.

| Order | Work | Acceptance and failure checks | State |
|---|---|---|---|
| 1 | Bind explicit aisle graphs to loaded maps, then feed planned waypoints and complete requests into S03 | Deterministic path, blocked edge and unreachable goal rejection, omitted corridor rejection, no movement without admission, original E1 S03 unchanged | Map binding and S03 wiring implemented; review pending |
| 2 | PostgreSQL schema and repositories, task queue, workers, recovery and mission handoff | Compare persistent and pure transitions; concurrent claim exclusion; stale token denial inside the effect transaction; occupied expiry remains faulted; duplicate handoff is idempotent | Corridor reference verified in PR 56; queue/recovery and worker iteration implemented, cloud verification pending; physical handoff and daemon next |
| 3 | Audit and rate-limit repositories, MCP transport, dispatch and tools | Thirty concurrent calls across connections respect the limit; failed intent write denies; result correlation; forbidden identity/tool pairs deny; tool errors remain results | Approved, pending |
| 4 | Structured mock completions, director, catalog resolution, deterministic assignment, court orchestration and operator inbox | Valid command reaches one robot under fast control; ambiguity, rejected vote, invalid output and timeout escalate; preserve the existing unanimity rule | Pending |
| 5 | Production untrusted-input entry points and E3 evaluator | Sanitization before classification; no unreviewed label scored; missing target implementations cause an error; ablations use production paths | Pending maintainer labels and integration |
| 6 | Plan schema, belief state, validation rollouts, counterexamples, bounded crisis loop and E10 harness | Invalid plans reject; no more than three planner iterations; escalation on exhaustion; reflex control remains active; development cloud comparisons | Pending |
| 7 | Simulator snapshots, replay bridge and technical viewer overlays | Renderer consumes simulator state only; envelope, lidar and ghost overlays; replay state hashes; retain the mockup until its prerequisites exist | Pending |
| 8 | Machine degradation, independent predictor, severity, manual sheets, retrieval, catalog, tickets, parts and procurement | Seeded faults; conservative missing-data behavior; wrong part rejected; one event cannot duplicate a ticket or order; E6 baseline | Pending |
| 9 | Bounded safety advisor and organizer, fleet proposal validation, voice and vision adapters, read-back and text fallback | Advisors cannot widen motion; turn and budget limits; message schema; wrong spoken item cannot execute without confirmation; E5 and E7 harnesses | Pending |
| 10 | Extended E8, E9, GLB assets, reproducible deploy, measured README, video and submission | Measurements trace to result files; image tags use commit; recorded demo fallback; published limits match actual results | Pending |

## Execution rules

- Use isolated worktrees, task branches, failing tests before implementation and Conventional Commits with a Codex co-author trailer.
- Keep protected changes explicit in every PR. Approval is recorded above; do not request it again for the same scope.
- Add no runtime dependency without recording its purpose and maintainer approval. Do not select a real provider HTTP client as part of mock routing.
- Full E2 and other long runs execute in cloud workflows. Do not invoke E3 before reviewed labels and production entry points exist. Paid calls and held-out runs still require specific execution authorization.
- Before pushing: green `uv run ci` on HEAD, reviewed diff, gitleaks, clean tree and a non-main branch. The existing pre-push gate remains unchanged.
- Update LASTCONTEXT.md and PENDING.md as each task finishes. Report unresolved E1 failures and missing evaluation without changing published measurements.
