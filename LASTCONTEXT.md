# Waggle Hive: Last context

Updated: 2026-11-04. PR 163 (chore/merge-wave-5 to main) contains the viewer
gallery and offline asset import. This task merges origin/main at 9cfb142 into
its head 10010cc and resolves LASTCONTEXT.md and PENDING.md by retaining current
main tasks plus the viewer handoff. The maintainer merges the PR, not the agent.
Main remains clean at 9cfb142 with green cloud CI (run 41777534335). PR 156 was
already merged before this task. The user supplied an older 75% analysis; it is
superseded by this code/PR audit and PENDING.md active priorities.

Code progress of the project (estimate by eye, code only): 83% on 2026-11-04, margin about 3 points.
This replaces the stale November 2 estimate of 80%: main now includes technician
MCP wiring, schema revision 14, E5 wiring, E6 mock runner and validator stage D.
Viewer code is about 68% including the pending gallery, whose task code is 100%.
The pending gallery adds less than one project point at this precision. Runs,
results, documentation and delivery do not count. These are judgments, not results.

## Current state

- Main contains ADRs 081 to 088: MCP technician lease/settlement tools, validator
  stage D, E5 runner, failure_history revision 14, E6 mock chain, unified rollout,
  belief builder and crisis loop, E5 caller/persistence/client wiring and history loader.
- E5 C0/C1/replay and the E6 mock runner are implemented, not evaluated by this task.
  E5 C2/C3/C4 are refused because the organizer is absent; its production role remains.
  E4 is scripted-only; E3 includes court_unanimity but live evaluation remains.
  E8 extension and the E9 mutation campaign remain pending. E6 diagnosis
  still reads synthetic in-memory cases; production database-backed retrieval and
  orchestration remain. Crisis planning still needs its LLM proposer adapter.
- LLM provider/logging code is about 93%; court/E4 50%; voice/vision 75%; package
  model 75%; catalog/technician lease 90%; advisors/E5 85%; maintenance/E6 80%;
  rollout/crisis 80%; E2 harness 97%; replay generator 100%. Estimates by eye only.
- Vertex, real transcription, production integration, the real MCP SDK client
  check, maintainer labels/data and reviewed fixtures remain. MCP is not claimed
  conformant. No paid calls, experiments, migrations or held-out runs occurred here.
- Meta Standard prices remain verified at 1.25 input / 4.25 output USD per million
  tokens. PR 156 preserved all five intended price/documentation/test files.

## Viewer handoff

- The gallery has 20 entries: 17 GLBs and three procedural previews. It includes
  revised workers, five robots, industrial equipment, modular rack/conveyor/dock
  and a gallery-only pickup prop. Replay does not invent human action or role state.
- Camera orbit, pan, zoom, focus and fit are implemented. ADR-089 describes the
  asset importer and gallery. Map geometry, overlays, live mode and simulator-owned
  role/action fields remain separate viewer work. Visual review is the maintainer's.
- GLBs are excluded from Git. web/models.json pins hashes, sizes, clips and
  provenance. Import extracted files with npm run models:sync -- --source DIRECTORY
  from web/. Preserve the ignored local assets and the separate binary pack:
  C:/Users/agusd/.codex/artifacts/waggle-viewer-models-20261104.zip.
- Viewer development server is on port 5174; port 5173 belongs to another project.
  Open ?gallery=1. Do not replace dirty Meshy or original GLB worktrees.

## Done last

- The first local resolution CI found two document-format defects: required
  headings and the exact percentage prefix were missing. They were corrected
  in the documents without changing tests. Final validation is reported in the PR.
- Before resolving conflicts, PR 163 remote checks and viewer jobs were green,
  but GitHub reported CONFLICTING in the two context files. The three-dot diff
  also includes .gitignore, docs/DECISIONS.md and docs/GOTCHAS.md; no backend code.
- Earlier local validation on 10010cc: 91 viewer unit tests and build passed.
  Browser tests failed at launch because Playwright Chromium headless shell 1248
  was absent. No browser installation or retry was attempted after that red check;
  earlier CI was interrupted. This context resolution does not claim that local
  browser validation passed. The updated PR checks report the merged head's state.
- PR 156 local minimum validation passed: 85 targeted LLM tests, Ruff, format and
  mypy. Its remote checks passed; it is already merged, not awaiting another merge.
- Main repair was explicitly authorized: mixed files matched origin/main, then
  git reset --hard origin/main restored it. Eight clean merged worktrees were
  removed. Dirty global-custody, meshy-assets, viewer-glb, unmerged old E3/session
  worktrees and the pending viewer worktree were preserved. Another owner's sandbox
  worktree was preserved after Git refused ownership; no trust exception was added.
- docs/context-wave3 must never be merged. Its endpoint diff against main shows
  72 files, 253 insertions and 6325 deletions. Remote deletion is the maintainer's.
- Ticket race fix d11c7c5 is present as identical patch 8ae51e3 on main. Bare
  ON CONFLICT DO NOTHING remains. feat/maintenance-tickets needs no PR.
- Earlier uncommitted validation notes remain in chore/validation-156-163 in
  C:/projects/projects-github-agustindiazcano/waggle-validation-156-163.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md, fetch the
remote, inspect PR 163 and worktrees. The conflict-resolution task merges main
9cfb142 into chore/merge-wave-5 without rewriting history. Review its latest CI
and mergeability before the maintainer merges; agents never merge. Project code
is about 83% plus/minus 3 points, viewer 68% and gallery task 100%, judgments only.
Preserve dirty global, Meshy, GLB and all unmerged worktrees and the binary model
pack. Review all gallery entries visually. Local browser validation previously
failed because Chromium 1248 was absent; do not call it passed. Production E5/E6
integration, the LLM crisis proposer, MCP SDK validation, viewer overlays/map/live
mode and maintainer labels/data remain. Never merge docs/context-wave3; its remote
deletion belongs to the maintainer. Ticket race patch is already in main. No paid
call, held-out run, migration or safety change is authorized by this handoff.
