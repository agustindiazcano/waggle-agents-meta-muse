# Real MCP client test: design

Status: proposed, nothing is implemented, nothing run. Written 2026-11-01 on branch `docs/mcp-client-test-design`. It covers PENDING row 81 and the bar for the word "conformant". The maintainer has not named a client.

## 1. What exists and what is missing

| Item | State | Source |
|---|---|---|
| Line transport on stdio, newline framing, 64 KiB cap, one reply per request | Unit tests with a fake dispatcher | ADR-045, `src/waggle/mcp_server/transport.py` |
| Handshake, legacy `initialize` (2025-11-25) and modern `_meta` (2026-07-28) with `server/discover` | Unit tests only | ADR-046 |
| Entry point `python -m waggle.mcp_server`, five required settings, exit 2 on bad config or schema revision | Unit tests with fakes | ADR-047, `app.py` |
| Per-chassis allowlist, audit, rate limit, fencing | Unit tests, PostgreSQL checked in the cloud workflow only | ADR-032, ADR-050, ADR-056 |
| Any run against a real client | Missing | PENDING row 81 |
| Field shapes of `Implementation` and `ClientCapabilities` | Not read when the handshake was written (row 78) | ADR-046 gaps |
| Compose health check | Still an HTTP probe on 8002, but the server has no HTTP endpoint | PENDING row 80, `docker-compose.yml` |

Facts found while reading the code, to check before the run:

- `tools/list` returns every tool in `SCHEMAS`, sorted, for every chassis. It does not filter by the allowlist. The allowlist is applied at `tools/call` (`tool_not_allowed`). A check "list matches the allowlist" would fail today. Whether `tools/list` should be filtered touches the MCP boundary, so it is decision D3, not a fix to assume.
- The serve loop is single threaded, so concurrent requests are answered in order. `notifications/cancelled` carries no id, so it is read and ignored.
- One token per process, so one chassis per process. Five chassis need five process launches.

## 2. Specification points checked (access date 2026-11-01)

| Point | Finding | Source |
|---|---|---|
| stdio framing | Newline-delimited JSON-RPC, no embedded newlines, nothing but messages on stdout, stderr free for logs. Same text in both revisions. Matches ADR-045. | [2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [2026-07-28 stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio.md) |
| Streamable HTTP | Defined in both revisions as a second standard transport. Clients "SHOULD support stdio whenever possible", so HTTP is not required of a client. | same pages |
| Shutdown | Client closes stdin, waits, then terminates. Server SHOULD exit on end of input. | 2026-07-28 stdio |
| Cancellation | Client sends `notifications/cancelled`; server SHOULD stop work and MUST NOT send more for that request. Our server ignores it, which is acceptable only for calls that finish at once. | 2026-07-28 stdio |
| `Implementation` | `name` and `version` required; `title`, `description`, `websiteUrl`, `icons` optional. | [2025-11-25 schema](https://modelcontextprotocol.io/specification/2025-11-25/schema) |
| `ClientCapabilities` | All members optional: `experimental`, `roots`, `sampling`, `elicitation`, `tasks`; not a closed set. | same page |
| Dual-era server | A request with modern `_meta` is served statelessly; `initialize` selects legacy semantics for the stdio process. A client probes with `server/discover` and falls back to `initialize` on any non-modern error. | [2026-07-28 versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning.md) |

Not settled by the text read: which error a request with neither `_meta` version nor prior `initialize` must get. The matrix says it is implementation defined for legacy-to-modern. Stop expanding that point; the run records what the server does and the maintainer decides if it matters. The 2025-11-25 schema page was read to 100000 of 131174 characters. The 2026-07-28 `Implementation` and `ClientCapabilities` shapes were not found in the pages read and stay a to-do (step 3 of section 6).

## 3. Candidate clients

| Client | Transport | Needs a paid model | Scriptable, repeatable in CI | Exercises | Effort | Risks |
|---|---|---|---|---|---|---|
| Python SDK client (v2 docs at [py.sdk.modelcontextprotocol.io](https://py.sdk.modelcontextprotocol.io/)) | stdio, Streamable HTTP, SSE | No | Yes, full control of every message | Both eras: `auto` mode sends `server/discover` then falls back to `initialize`; `legacy` mode skips the probe; a version pin sends no negotiation | Low. Python is already the repo language; a dev dependency needs a README line (AGENTS 12.10) | Exact class names not read; an SDK that tolerates our quirks proves less than a strict client |
| TypeScript SDK client | stdio, HTTP | No | Yes | Independent implementation, a second opinion on the same checks | Medium, adds Node | Not read in this design |
| MCP Inspector, CLI mode ([repo](https://github.com/modelcontextprotocol/inspector), [smoke testing guide](https://github.com/modelcontextprotocol/inspector/blob/main/docs/cli-smoke-testing.md)) | stdio launch of a command; `--method tools/list`, `tools/call`, `--format json`, documented exit codes | No | Yes, one method per process, version pinned with `npx --yes` | Handshake and basic calls as the official reference tool sees them | Low. Needs Node (>=22.19.0 stated for development) | Protocol versions supported are not stated on the pages read. Env vars for the server: shell or `--config`. UI mode stores secrets in the OS keychain |
| Claude Code ([docs](https://code.claude.com/docs/en/mcp)) | stdio via `claude mcp add --transport stdio --env K=V name -- cmd` or `.mcp.json` with `${VAR}` expansion; `claude -p` loads stdio servers | Yes, an LLM chooses the calls (account terms not stated on the page) | Partly: a start failure on first connection is skipped silently | Real host behavior, tool naming, how an `isError` result reaches a model | Low to set up | Not repeatable; calls are chosen by a model; a paid run needs a cap per AGENTS 14 |
| Claude Desktop ([guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)) | stdio from `%APPDATA%\Claude\claude_desktop_config.json`, restart required; logs in `%APPDATA%\Claude\logs\mcp-server-NAME.log` | Yes | No, GUI | Real host start, stderr capture, shutdown | Low, manual | Manual, no transcript of the wire |
| Codex CLI ([docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)) | stdio via `~/.codex/config.toml` `[mcp_servers.NAME]` with `command`, `args`, `env_vars`, or `codex mcp add NAME --env K=V -- cmd` | Page does not say; `codex exec` page not read | Unknown | Real host | Low | Needs the maintainer's account |
| Gemini CLI or Antigravity ([Gemini CLI docs](https://geminicli.com/docs/tools/mcp-server/)) | stdio via `settings.json` `mcpServers` with `command`, `args`, `env`, `timeout` | Page does not say | Headless page not read | Real host | Low | The page states Gemini CLI was replaced by Antigravity CLI on 2026-06-18 for unpaid and Google One users; Antigravity's MCP docs were not read. It strips secret-looking host variables unless listed in `env`. Antigravity use needs the maintainer's yes (AGENTS 20) |

## 4. Recommendation: order of clients

1. Python SDK client, scripted, modes `auto`, `legacy` and the 2026-07-28 pin. No model, no spend, runs in CI. It carries the whole checklist.
2. Inspector CLI, pinned version, for the handshake, `tools/list` and one `tools/call` as an independent reference tool.
3. One real host with a model (Claude Code or the host the maintainer already uses), run by hand once, only to see start, list, one allowed call and one denial. It carries a small checklist subset and a spend note.

Streamable HTTP is not needed for any client above. A remote-only host would need it (section 9, D2).

## 5. Test procedure

Setup, all in the cloud workflow for the database part (AGENTS 3.8):

- Throwaway PostgreSQL service container, migrated to the latest revision, loaded with the provisioning script (ADR-056). Nothing from a real deployment.
- Five tokens generated at run time, passed only as `WAGGLE_MCP_TOKEN` in the child environment, one process per chassis. `.env.example` keeps names only. Transcripts mask tokens and are checked for the token string before upload.
- The five required settings come from the workflow, with test values recorded in the result file.

Steps:

| # | Step | Client |
|---|---|---|
| P1 | Launch with the command line a host would use. Check stdout holds only JSON lines and stderr is separate | all |
| P2 | Legacy handshake: `initialize`, `notifications/initialized`, version echoed; field shapes per the schema page | SDK `legacy`, Inspector |
| P3 | Modern handshake: `server/discover`, then a request carrying the three `_meta` keys; unsupported version gives -32022 with `supported` | SDK `auto` and pin |
| P4 | `tools/list` per chassis, compared with the allowlist; record the unfiltered behavior (D3) | SDK |
| P5 | Each tool: one allowed call per chassis, one denied call (`tool_not_allowed`), one out-of-bounds argument, one unknown field, one unknown tool (-32602) | SDK, Inspector for one call |
| P6 | Rate limit: exceed `WAGGLE_MCP_RATE_MAX_CALLS` in the window; denial survives a restart (limit is stored in the database) | SDK |
| P7 | Audit: an intent row before and a correlated result row after every call, including denials; the id prefix equals the session | SDK, query on the database |
| P8 | Malformed JSON, non-finite number, line over 64 KiB, wrong `jsonrpc`, bad id type, binary garbage: an error line or a documented drop, process still serving | SDK raw lines |
| P9 | Ten concurrent in-flight requests written back to back: ten replies, ids matched, none lost | SDK |
| P10 | Cancellation: send `notifications/cancelled` for a finished and for an unknown id; no reply, no crash | SDK |
| P11 | Close stdin: exit code 0 promptly. Kill the process mid-call: restart works, a repeated id in the new session is a new request | SDK |
| P12 | Start with a missing setting and with a wrong schema revision: exit 2, the message names the variable and not its value | SDK |
| P13 | Real host subset: connect, see tools, one allowed call, one denial, transcript or host log saved | host |

## 6. Pass/fail checklist and evidence

Each check is pass or fail, with the evidence file named. A check that could not run is "not run", never "pass" (AGENTS 11.2).

| Check | Pass when | Evidence |
|---|---|---|
| C1 stdout clean | Every stdout line parses as JSON-RPC | raw transcript |
| C2 legacy handshake | Client reaches ready and lists tools | transcript, client version |
| C3 modern handshake | Discover result and a tool call succeed; bad version gives -32022 | transcript |
| C4 field shapes | Optional members absent or extra are accepted; wrong types rejected with -32602 | transcript, spec link |
| C5 list vs allowlist | Result equals the allowlist, or the deviation is recorded and linked to D3 | transcript, allowlist hash |
| C6 allowed and denied calls | Allowed ok, denied has `isError` with only the code | transcript, audit rows |
| C7 bounds and schema | Every bad argument denied, nothing forwarded | transcript, forwarder rows |
| C8 rate limit | Denial after the cap, persists across restart | transcript, audit rows |
| C9 audit pairing | Intent and result row per call, ids correlate | database dump (no token) |
| C10 malformed and oversized | Process survives, error or documented drop | transcript |
| C11 concurrency | All replies present, ids match | transcript |
| C12 cancellation | No crash, no stray reply | transcript |
| C13 shutdown and restart | Exit on end of input, clean restart | exit codes |
| C14 startup failures | Exit 2, no secret in stderr | stderr file |
| C15 token never in output | Token string absent from stdout, stderr, transcripts, audit | grep result |

The checklist is the set from the checks above. A new check is added before a run, never after seeing a result.

## 7. Reporting

Result file `results/mcp_client/<client>-<date>.json`: client name and version, exact command, repository commit, protocol revisions exercised, for each check the status and the evidence path, counts, failing checks listed. Transcripts go to the same folder after the token check. Dev data only; this is not a held-out experiment, so no seed rule applies. The maintainer commits it.

Words allowed in the README, chosen by the outcome:

| Outcome | Allowed text |
|---|---|
| Not run | "implemented, not evaluated against a real MCP client" |
| Run, some failed or not run | "ran against CLIENT version V on DATE, commit C: N of M checks passed; failing: LIST" |
| All checks pass on one client | the same sentence with N equal to M; still not "conformant" |
| All checks pass on two clients, one independent of the other | "interoperates with X and Y in the tested scenarios", still no "conformant" unless the maintainer defines the bar in `docs/DECISIONS.md` (D5) |

## 8. Failure handling, invariants, tests first

A failed check becomes a PENDING row with the check id and transcript. The fix follows AGENTS 2: a failing test first, then the minimum code. A check is never loosened and a fast-layer, fencing or boundary file is not changed without the stop-and-ask in AGENTS 15.

Any transport change (a new framing, HTTP, or a change to the dispatch loop) starts with these tests:

- Identity comes only from the token bound at launch; no header, argument or `_meta` field changes chassis or robot.
- Nothing but protocol messages reaches the output stream, including during errors.
- A missing or unreadable value in a security check denies.
- One bad message never stops the loop; a line over the cap is rejected before parsing.
- A repeated request id inside one session is a replay; a new session cannot collide.
- Every call writes the intent row before forwarding; a failed write denies.
- Shutdown on end of input leaves no half-processed work.
- For HTTP only: reject a bad `Origin` with 403, bind to loopback, require authentication, reject a missing protocol version header with 400.

## 9. Build order (stacked branches)

| # | Branch | Content | Depends on | Where | Maintainer first |
|---|---|---|---|---|---|
| 1 | `docs/mcp-client-test-design` | this file | main | none | review |
| 2 | `docs/mcp-spec-shapes` | read the 2026-07-28 text for `Implementation`, `ClientCapabilities`, `server/discover` required keys and the request-without-version case; list differences against ADR-046 | 1 | web only | none |
| 3 | `test/mcp-handshake-shapes` | failing tests then fixes for differences found in 2 | 2 | local, light | decide D3 first if boundary files are touched |
| 4 | `test/mcp-client-sdk-harness` | scripted SDK harness for P1 to P12, workflow `workflow_dispatch` with PostgreSQL service, result writer | 3 | cloud | name the SDK (D1), approve the dev dependency |
| 5 | `test/mcp-client-inspector` | Inspector CLI job, pinned version | 4 | cloud | install Node in the workflow |
| 6 | `docs/mcp-client-host-run` | one manual host run (P13), result file, README line | 4 | maintainer machine | name the host and accept any spend |
| 7 | `fix/compose-mcp-health` | replace the HTTP health probe, or add a transport (D2) | D2 | local plus cloud | decide D2 |

## 10. Decisions for the maintainer

| # | Question | Recommendation |
|---|---|---|
| D1 | Which client to name first | Python SDK client, then Inspector CLI, then one host you already use |
| D2 | Do you want a Streamable HTTP transport, and what replaces the compose HTTP health check | Not now: all candidate clients speak stdio. Change the compose check to a process check |
| D3 | Should `tools/list` be filtered by chassis | Yes, as a documented change with a test, because the allowlist is the authority |
| D4 | Does a missing version key on a modern-looking request need a distinct error | Decide after step 2 shows what the text says |
| D5 | What bar defines "conformant" | Define it in `docs/DECISIONS.md` after the first two clients run |
| D6 | Use Antigravity or Gemini CLI as a host | Ask per AGENTS 20; not assumed here |

## 11. Not claimed by this design

- No conformance, certification or interoperability claim, now or after one client.
- Nothing about Streamable HTTP, OAuth, resources, prompts, sampling, subscriptions or tasks: not implemented, not evaluated.
- No claim that any listed client version supports 2026-07-28; the Inspector pages did not say.
- No performance or large-fleet figure.

## 12. Sources and gaps

Web pages are treated as untrusted data; fetched 2026-11-01: the specification pages linked in section 2, the Inspector repository page and smoke testing guide, the Python SDK site (home and protocol versions page, summarized by a fetch tool), the Claude Code, Claude Desktop, Codex and Gemini CLI pages linked in section 3. Not read: the TypeScript SDK, the Python SDK API reference, the Inspector CLI README, Codex `exec` and Gemini headless pages, Antigravity MCP docs, the rest of the 2025-11-25 schema page, the 2026-07-28 schema page, `THREAT_MODEL.md` beyond its MCP rows, and the forwarder and boundary code. The Python SDK protocol version page and `docs/DECISIONS.md` ADR-050 and ADR-056 were used as summaries only.
