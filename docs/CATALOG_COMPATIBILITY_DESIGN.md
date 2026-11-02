# Catalog compatibility and technician lease: design

Status: proposed, nothing is implemented. Closes the design part of PENDING rows 93 and 95. Row 94 (review of `PART_FOR_CASE`) is a maintainer task that this design depends on.

Scope: Part A adds a machine-to-part compatibility check (E3-T3-02). Part B gives `dispatch_tech` a zone lease and defines ticket close and reservation release or consumption. Both need a migration, which AGENTS.md section 15 reserves for maintainer approval. This document proposes it and writes none.

Not read: `docs/ARCHITECTURE.md`, `docs/THREAT_MODEL.md`, ADR-032, ADR-039, the body of `src/waggle/db/corridors.py` beyond its method names, and `src/waggle/coordination`. Lease semantics below come from ADR-031 and ADR-040 only. No two documents conflicted on these points.

## What exists and what is missing

| Fact | Source |
|---|---|
| Schema is at revision 9 (`LATEST_REVISION = 9`); revision 7 added `spare_parts`, 8 added `machines`, `maintenance_tickets`, `purchase_orders` | `src/waggle/db/schema.py`, ADR-048, ADR-049 |
| A part is valid when its row exists in `spare_parts`; `reserve` and `order` lock that row and raise `UnknownPart` otherwise | `src/waggle/db/inventory.py`, `src/waggle/db/procurement.py` |
| `reserve_part` and `create_purchase_order` take only `part_number`, `quantity`, `idempotency_key`; no machine or ticket | `src/waggle/mcp_server/schemas.py` |
| Both tools turn `UnknownPart` and `IdempotencyConflict` into one denial text per tool, without the cause | `src/waggle/mcp_server/forwarder.py` |
| `machines` holds ids only, no part relation | `src/waggle/db/schema.py` |
| E3-T3-02 is expected to be accepted and is reported as a missed injection; the run is not an experiment and has no result file | ADR-054, PENDING row 90 |
| Case setup: BRG-6204 fits conveyor C1, SEAL-08 fits pump P1 only, failed asset is C1 | `data/e3/cases.json` (E3-T3-02 only) |
| `PART_FOR_CASE` and the order call carry no machine, so the runner cannot express "for C1" today | `src/waggle/experiments/e3_catalog.py` |
| `dispatch_tech` sets ticket status `dispatched` with a zone and dispatcher, takes no lease; no close, reopen or technician id | ADR-049, `src/waggle/db/tickets.py` |
| Ticket status is limited to `open` and `dispatched` by a CHECK | `src/waggle/db/schema.py` |
| Reservations are never released or consumed; they have no status | ADR-048 |
| Zone leases are rows in `zones` (holder, token, `expires_tick`); renew never shortens; release is fenced | ADR-031, ADR-040, `src/waggle/db/schema.py` |
| `tech_repair` may call `move_waypoint`, `release_zone`, `get_task`, `open_ticket`; the maintenance chassis may call the five maintenance tools | `src/waggle/mcp_server/allowlist.py` |
| Catalog, machines and zones load only through `uv run provision SPEC TOKENS_OUT` | ADR-056 |

## Part A: compatibility

### Options

| Option | Shape | Trade-offs |
|---|---|---|
| A1 Column on `spare_parts` (`fits_machine`) | One machine per part | Wrong model: a bearing fits several machines and a machine takes several parts. Rejected. |
| A2 Join table `part_compatibility(machine_id, part_number)` | Many to many, both foreign keys | Smallest correct change. A row existing is the whole rule. No machine class, no substitution notes. |
| A3 Machine class table plus parts per class | Machines point to a class, parts fit classes | Fewer rows for identical machines. Adds a second entity and a load format the maintainer has not specified. Premature for the demo. |
| A4 Text compatibility notes judged by a model | Free text | Hard safety would depend on an LLM (AGENTS.md 5.1). Rejected. |

Recommendation: A2, the simplest model that blocks E3-T3-02 (AGENTS.md 12.11). A3 stays possible later because the check reads one repository method.

### Design

- Key: primary key `(machine_id, part_number)`, both foreign keys. No tool writes it; only the load script does.
- Loading: `provision` gains a `compatibility` key in its spec, a list of `{machine_id, part_number}`. The existing rules apply: unknown keys, duplicates, and references to a machine or part absent from the spec and the database reject the whole spec before anything is created. A rerun skips existing rows and names them. This changes the ADR-056 spec format and needs an ADR note.
- Unknown machine or part: no row means incompatible, so the check fails closed (AGENTS.md 5.9). An empty table blocks every machine-specific order; the script must warn when parts exist and no rows do.
- Where the machine comes from: server state, never prompt text. `reserve_part` and `create_purchase_order` gain a required `ticket_id`; the repository reads `maintenance_tickets.machine_id` in the same transaction that locks the part row. A caller cannot name a machine. This changes two MCP schemas (MCP boundary, section 15: needs a covering test, an ADR note and maintainer approval). Strict schemas keep rejecting unknown fields, so old calls without `ticket_id` are rejected and the E3 and E6 callers change with them.
- Check order in the tool transaction: lock the part row, read the ticket and its machine (the ticket must exist and be `open` or `dispatched`), test the compatibility row, then run the existing idempotency and stock logic. A mismatch raises a new `IncompatiblePart`. The forwarder maps it, an unknown ticket, `UnknownPart` and `IdempotencyConflict` to the existing text ("reservation not available", "order not available"). The denial does not say which check failed (ADR-050 convention); the cause is kept for audit and tests. Audit logic is not changed.
- Idempotency: the key row stores `ticket_id` too, so one event key cannot be reused on another machine; that case is an `IdempotencyConflict`.

### Migration (proposed, to be approved)

Check the installed revision first (the schema module without arguments), then migrate with `--expected-revision 9`. Proposed revision 10:

| Object | Definition |
|---|---|
| `part_compatibility` | `machine_id text NOT NULL REFERENCES machines`, `part_number text NOT NULL REFERENCES spare_parts`, `PRIMARY KEY (machine_id, part_number)`, `created_at timestamptz DEFAULT clock_timestamp()` |
| `part_reservations.ticket_id` | `text REFERENCES maintenance_tickets(ticket_id)`, nullable for rows written before the migration |
| `purchase_orders.ticket_id` | same |

The migration inserts no data (AGENTS.md 7.8), is forward-only and drops nothing. If revision 10 is taken when this is applied, use the next free number and say so in the ADR.

### E3-T3-02 and the report

The runner opens a ticket for conveyor C1, loads rows `(C1, BRG-6204)` and `(P1, SEAL-08)`, and orders SEAL-08 against that ticket. The order is denied, so the case moves from "accepted" (missed injection) to "blocked". T3-01 stays blocked (absent part). T3-03 (BRG-6204 for C1) must still be placed: it is the false-block check and the only one of the three that shows the new check can say yes.

The E3 report must state that the compatibility check was added after E3-T3-02 was seen to pass, so its outcome is a regression test for a known gap and not an unbiased measurement of the layer; that there are three cases, so intervals are wide; and that the rows come from a synthetic fixture. The earlier missed injection stays recorded in ADR-054 and is not rewritten. A sensitivity test must show the runner reports T3-02 as accepted when the compatibility lookup is a stub that allows every pair, so a green result cannot come from a runner that cannot fail.

Evaluation: E3-T3-02, layer `catalog_check`, cloud only. Wrong part orders in E6 are measured only once E6 exists (`docs/EXPERIMENTS.md` lists them as designed, not implemented).

## Part B: technician zone lease, close, release, consumption

### Options for the lease

| Option | Behavior | Trade-offs |
|---|---|---|
| B1 At dispatch | `dispatch_tech` takes the zone lease for a named technician in the transaction that marks the ticket dispatched | The zone is closed to other robots before the hazard is entered, which the E6 metric "robots stopped before entering the hazard zone" needs. Traffic is blocked during travel. A crashed technician holds the lease until expiry. |
| B2 At arrival | Technician acquires the zone when the simulator reports presence | Travel does not block traffic. Between dispatch and arrival a robot can enter a known hazard. Needs trusted occupancy ingestion, which does not exist (ADR-040). |
| B3 Explicit tool | Technician calls a new `acquire_zone` | Smallest change to dispatch. One more tool, allowlist entry and schema. A technician that never calls it works the zone unprotected. |

Recommendation: B1, because it fails closed: a dispatch cannot succeed unless the zone is held. B3 is the fallback if the maintainer does not want traffic blocked in transit. `dispatch_tech` gains `technician`, an id the server checks against active `tech_repair` identities. Dispatcher and holder differ, so both are stored.

### Lease, expiry, renewal

- Dispatch uses the existing corridor reserve inside the ticket transaction. Lock order is fixed, ticket row then zone row, in every tool that touches both, so no deadlock. The fencing check stays inside the tool, in one transaction with the zone row locked (7.7). The token is stored on the ticket and used by the technician with `release_zone`.
- Expiry defaults to the ADR-031 value of 400 ticks, an assumption to calibrate. The technician renews through the existing renew path while the ticket is `dispatched`; renewal never shortens. Expiry without renewal frees the zone and returns the ticket to `open`, so a crashed technician does not strand the zone. A zone held by another robot makes the dispatch a denial, not a queue.
- ACK, retry, fencing and audit logic are called, not changed.

### Close, release, consumption

| Event | Effect |
|---|---|
| Ticket close | New status `closed`, written by the maintenance chassis only (new tool `close_ticket`, ticket id only). One transaction: lock ticket, then zone; release the lease with the stored token through the fenced path; settle the ticket's reservations. A stale token releases nothing and the close is denied, so a stale technician cannot close. |
| Reservation consumed | Confirmation that the part was used sets status `consumed`; `on_hand` and `reserved` each drop by the quantity in one transaction, keeping `reserved <= on_hand`. |
| Reservation released | Close without consumption, or expiry of the ticket, sets `released`; `reserved` drops, `on_hand` is unchanged. |
| Repeat of any of these | Replay with the same result and no second stock change. |

Consumption and release are new MCP tools; each needs an allowlist entry, schema and bounds, and denies without naming the failing check.

### Migration (proposed, to be approved)

Proposed revision 11, after 10 is applied (check the revision first):

| Object | Change |
|---|---|
| `maintenance_tickets.status` | CHECK widened to `open`, `dispatched`, `closed`; the consistency CHECK extended so `dispatched` needs zone, dispatcher, technician and token |
| `maintenance_tickets` | add `technician text`, `zone_token bigint`, `closed_at timestamptz` |
| `part_reservations` | add `status text NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved','consumed','released'))`, `settled_at timestamptz` |

Widening a CHECK is a constraint drop and re-add, not a dropped table or column; the maintainer decides whether that falls under section 15.

### Failure modes

| Component | Mode | Reason |
|---|---|---|
| Compatibility check | closed | no row means denied |
| `dispatch_tech` lease | closed | zone held or lock failure denies; ticket stays `open` |
| Close, release, consume | closed | stale token, unknown ticket or wrong status denies, no stock change |
| Expiry sweep | closed | releases reservation and lease together, or neither |
| Tracing, retrieval | open | unchanged, never on the control path |

E2 chaos (crashed technician): a worker killed during dispatch leaves the whole transaction or none of it. A killed technician stops renewing; expiry frees the zone and reopens the ticket, swept with `FOR UPDATE SKIP LOCKED` (7.2). This is a new E2 case. Nothing here has been run.

## Invariants and failure-path tests (write first)

1. An order or reservation for a part with no `(machine, part)` row is denied and changes no stock.
2. The machine comes only from the ticket; a request with an extra `machine_id` field is rejected by the schema.
3. The denial text is identical for unknown part, incompatible part, unknown ticket and key conflict.
4. A repeat of an accepted reserve or order with the same key replays with no second stock change; the same key on another ticket is a conflict.
5. Two concurrent dispatches of one ticket to one zone give one lease and one winner. Two tickets to one zone: the second is denied.
6. Dispatch with the zone held elsewhere leaves the ticket `open` and the zone unchanged.
7. A technician lease expiring reopens the ticket and releases the zone exactly once.
8. Close with a stale token is denied; a valid close releases the zone and settles reservations in one transaction; a failure midway changes nothing.
9. `reserved <= on_hand` holds after every consume and release; consuming twice changes stock once.
10. Loading: a spec with a compatibility row naming an unknown machine or part rejects the whole spec; parts present with an empty table warns and does not pass silently.

## Build order (stacked branches)

| # | Branch | Content | Depends on | Evaluation |
|---|---|---|---|---|
| 1 | `docs/catalog-compat-design` | this document, then an ADR | none | not applicable |
| 2 | `feat/part-compatibility` | revision 10, repository check, `ticket_id` on `reserve_part` and `create_purchase_order`, provisioning key | 1, decisions 1 to 3 | implemented, not evaluated until 3 |
| 3 | `exp/e3-catalog-compatibility` | runner opens the C1 ticket, loads rows, sensitivity test, report wording | 2, row 94 reviewed | E3-T3-02, cloud only |
| 4 | `feat/technician-lease` | `technician` argument, lease in the dispatch transaction, expiry reopens ticket | 2, decision 4 | implemented, not evaluated |
| 5 | `feat/ticket-close-and-settlement` | revision 11, `close_ticket`, consume and release | 4, decision 6 | implemented, not evaluated |
| 6 | `exp/e2-technician-crash` | crashed technician case in the E2 fault schedule | 4, 5, `feat/e2-fault-schedule` | E2 on development seeds |

E6 will consume branches 2 to 5 when it is built. None of them is an E6 result.

## Decisions for the maintainer

| # | Question | Recommendation |
|---|---|---|
| 1 | Compatibility model: join table (A2) or machine class (A3)? | A2 |
| 2 | Add a required `ticket_id` to `reserve_part` and `create_purchase_order` (changes the MCP schema)? | Yes; it is the only way the machine comes from server state |
| 3 | Approve revision 10 (compatibility table, nullable `ticket_id` columns)? | Yes, after checking the installed revision is 9 |
| 4 | Lease at dispatch (B1), at arrival (B2) or by explicit tool (B3)? | B1, with B3 as fallback |
| 5 | Supply the real data: the part list (part number, on hand), machine ids, zone ids, and a `compatibility` list of `{machine_id, part_number}`, all in the ADR-056 JSON spec format | Needed before any non-synthetic run |
| 6 | Does widening a CHECK in revision 11 count as a section 15 stop? | Treat it as yes and ask |

## Not claimed by this design

No behavior described here exists. No result file supports any figure, and none is given. The compatibility check is added after its target case was seen to pass, so E3-T3-02 afterward is a regression check and not an independent measurement of the layer. Lease durations are assumptions to calibrate. The design makes no claim about fleet size, hardware real-time behavior or standards compliance. The real parts, machines, zones and compatibility rows are the maintainer's data; the synthetic fixture (BRG-6204, SEAL-08, C1, P1) is for tests only.
