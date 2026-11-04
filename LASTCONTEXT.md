# Waggle Hive: Last context

Updated: 2026-11-04. PR 163 (8cfb8fb) and PR 164 (ba2abcf, E8 reporting) are
merged in main. This branch (feat/crisis-planner-adapter, ADR-090) adds the LLM
proposer adapter for the crisis loop (`LlmPlanProposer` and `planner-v1` prompt in
`waggle.llm`, with 9 adapter tests; mock provider only, no paid call) and merges
origin/main at ba2abcf without rewriting history. The maintainer merges the PR,
not the agent. Other agents work in separate worktrees (viewer, global custody,
Meshy assets, E3 labels, organizer); this branch touches none of those areas.

Code progress of the project (estimate by eye, code only): 85% on 2026-11-04,
margin about 3 points. Main now includes PR 163 (viewer gallery, ADR-089) and
PR 164 (E8 reporting at ba2abcf), and this branch adds the per-robot organizer
schema, runtime, loop/message boundaries and E5 C2/C3/C3_REPLAY wiring (ADR-090),
raising advisors/E5 code from 85% to 95%. Measurements, calibration, documents
and delivery do not count. No new published number or README result changed.

## Current state

- Main includes the viewer gallery (20 entries, 17 GLBs and three procedural
  previews), offline importer, camera controls and ADR-089. Gallery task code is
  100%, viewer overall about 68%; visual review, map, overlays and live mode remain.
- E8 adds production control_step timing through the existing E1 ControlRig,
  strict metadata-only llm_calls export summaries and a seeded finite-burst
  extrapolator. The workflow produces three separate cloud benchmark artifacts.
  Provider/role measurements, production exports and calibration remain pending.
- Error latency in the current LLM client is unmeasured and stored as zero.
  E8 never treats those placeholders as measured durations. Extrapolation uses
  successful-call latency and the observed error-row fraction, explicitly labeled
  as an assumption. Cached and denied rows are counted separately.
- The crisis LLM proposer adapter is merged in main (`c7098a7`, PR 165, ADR-090);
  its E10 harness and production caller remain. This branch (`feat/organizer-e5`,
  ADR-091) adds `waggle.governance.organizer`, `waggle.llm.organizer_runtime`
  (`organizer-v1`) and E5 `C2`, `C3` and `C3_REPLAY`. E5 `C4` remains refused
  until the fleet planner exists. E4 production court/cross-family routes, E6
  database-backed diagnosis, MCP SDK validation, real multimodal providers,
  package integrity and E9 remain. No paid call, migration, held-out run or
  safety change was performed in this task.
- LLM provider/logging code is about 93%; court/E4 50%; voice/vision 75%; package
  model 75%; catalog/technician lease 90%; advisors/E5 95%; maintenance/E6 80%;
  rollout/crisis 90%; E2 harness 97%; replay generator 100%. Estimates by eye only.
- Provider balances, caps, secrets, labels, catalog, zones and recordings still
  require the maintainer. G-GLOBAL remains unauthorized, outside the denominator.

## Done last

- Crisis planner adapter (ADR-090, this branch): failing test first
  (ModuleNotFoundError for waggle.llm.crisis_adapter), then planner_v1.txt and
  crisis_adapter.py. Local run: 214 passed (adapter, full validation suite and
  court adapter) with the sandbox workarounds below. The guard adapter tests
  fail locally because the sandbox blocks the asyncio localhost socketpair;
  that file is untouched by this branch.
- Merged origin/main at ba2abcf (PR 164, E8 reporting) into feat/crisis-planner-adapter
  without rewriting history, retaining both the E8 handoff and ADR-090 context.
- E8 reporting (PR 164): both subagents and the runner initially failed with missing
  modules. The review regressions reproduced unmeasured error latency being sampled
  as zero and prompt metadata failing to cover measured roles; both were corrected.
  See docs/E8_RUNNER.md for commands, strict input schema, measurement scope,
  provenance limits, assumptions and remaining work. No new dependencies.

## Preserved work and assets

- Preserve dirty global-custody, Meshy and GLB worktrees and all unmerged work.
  Preserve C:/Users/agusd/.codex/artifacts/waggle-viewer-models-20261104.zip;
  binaries are ignored and imported using web/models.json. Viewer port is 5174,
  gallery URL uses ?gallery=1. Port 5173 belongs to another project.
- Never merge docs/context-wave3: its endpoint diff deletes thousands of lines.
  Remote branch deletion is the maintainer's. Ticket race patch d11c7c5 is
  already represented by 8ae51e3 on main; feat/maintenance-tickets needs no PR.
- Earlier viewer local browser validation lacked Chromium 1248; do not describe
  that local run as passed. Earlier validation notes remain in
  ../waggle-validation-156-163. No asset worktree or unmerged branch was removed.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md first, inspect
git status, branches and worktrees, and fetch origin. PR 163 (8cfb8fb) and PR 164
(ba2abcf, E8 reporting) are merged in main. Review the PR of
feat/crisis-planner-adapter (ADR-090, crisis LLM proposer, mock only) and its CI
before the maintainer merges; agents never merge. Review docs/E8_RUNNER.md for
commands, metadata schema and explicit extrapolation limits; do not treat
unmeasured error latency zeros as measurements. Local Python note: the machine
Python 3.12.4 was removed, so .venv/pyvenv.cfg in this worktree points at a
uv-downloaded 3.12.16 under the session sandbox; mypy cannot load _ctypes there
and the sandbox blocks the asyncio socketpair (guard tests) and the uv cache
lock. Use cloud CI for the full gates. Project code remains about 83% plus/minus
3 points, bounded E8 reporting task 100%, broader E8 collection 75%, viewer 68%,
all judgments. Production E4/E5/E6, the E10 harness and crisis caller, MCP SDK
validation, viewer map/overlays/live and E9 remain; first check other agents'
branches to avoid duplication. No paid call, held-out run, migration or safety
change is authorized by this handoff. Never merge docs/context-wave3 or delete
another agent's work.
