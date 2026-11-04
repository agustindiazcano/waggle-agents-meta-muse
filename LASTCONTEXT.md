# Waggle Hive: Last context

Updated: 2026-11-04. E8 reporting work is isolated in exp/e8-latency-runner,
worktree ../waggle-e8-runner, based on main 8cfb8fb (PR 163 merged).
The shared root is on feat/crisis-planner-adapter with another agent's test;
this task did not switch its branch or edit its files. Two requested subagents
implemented call metrics and extrapolation in their own worktrees; their files
were reviewed and copied into the E8 integration branch, with no shared edits.

E9 update (2026-11-04): branch exp/e9-planted-defects in worktree
../waggle-e9-planted-defects adds the planted-defect campaign (ADR-091):
4 defects, copy-only runner, baseline check, result writer; first run
4 of 4 killed, in results/e9/dev/planted.json. Cloud mutation arm remains.

Code progress of the project (estimate by eye, code only): 83% on 2026-11-04,
margin about 3 points. This judgment stays at the same rounded value: the bounded
E8 reporting task is 100% written with tests, while the broader E8 collection
block is about 75% because database export automation remains. Measurements,
calibration, documents and delivery do not count. No new published number or
README result changed.

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
- E4 production court/cross-family routes, E5 organizer and service wiring, E6
  database-backed diagnosis, E10 LLM proposer, MCP SDK validation, real multimodal
  providers, package integrity and E9 remain. Do not duplicate another agent's
  crisis adapter work. No paid call, migration, held-out run or safety change
  was performed in this task.
- Provider balances, caps, secrets, labels, catalog, zones and recordings still
  require the maintainer. G-GLOBAL remains unauthorized, outside the denominator.

## Done last

- Tests first: both subagents and the runner initially failed with missing modules.
  The review regressions reproduced unmeasured error latency being sampled as zero
  and prompt metadata failing to cover measured roles; both were corrected.
- Full local CI is required by the current pre-push gate. Exact final command
  results, commit and PR are reported in the task chat and PR, not inferred here.
- See docs/E8_RUNNER.md for commands, strict input schema, measurement scope,
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
git status, branches and worktrees, and fetch origin. E8 reporting is isolated in
exp/e8-latency-runner at ../waggle-e8-runner, based on main 8cfb8fb with PR 163
already merged. Inspect its PR and checks; only the maintainer merges. Review
docs/E8_RUNNER.md for commands, metadata schema and explicit extrapolation limits.
Do not treat unmeasured error latency zeros as measurements. E8 production
exports and calibration and E9 remain. Preserve the crisis adapter agent's root
work, dirty asset/global worktrees and binary pack. Project code remains about
83% plus/minus 3 points, bounded E8 reporting task 100%, broader E8 collection
75%, viewer 68%, all judgments. Production E4/E5/E6, MCP SDK validation and
viewer map/overlays/live remain; first check other agents' branches to avoid
duplication. No paid call, held-out run, migration or safety change is authorized
by this handoff. Never merge docs/context-wave3 or delete another agent's work.
