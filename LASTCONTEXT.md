# Waggle Hive: Last context

Code progress of the project (estimate by eye, code only): 83% on 2026-11-04.
Unchanged at this precision; a judgment, not a result.

## Done last

Updated: 2026-11-04. Branch `feat/viewer-assets-complete`, based on
`chore/merge-wave-5` (PR 159), preserves and completes the uncommitted GLB viewer
from `feat/viewer-glb`. The original viewer and Meshy worktrees are unchanged.

The gallery has 20 entries: 17 generated GLBs and three procedural previews.
Revised worker, Black worker, Asian woman worker and flat carrier are integrated;
the replay uses the revised worker. Added tank, press, truck, extinguisher and
tree; conveyor and dock are original modular previews. Rack supports bays and
levels. Pickup has a hand-following visual prop in the gallery only. The replay
has no human action or package pose, so no pickup state was invented there.

## Current state

Camera orbit, pan, zoom, entity focus and fit are implemented. All 91 viewer unit
tests, build, Ruff and mypy passed. Three browser contract tests passed using installed
Chrome, including a camera pan that leaves the recorded hash unchanged. The
separate model browser check loaded all 17 GLBs and checked their clip names
(45.3 seconds for the test). Final CI details are recorded in the task PR.
Visual review belongs to the
maintainer. No experiment was run and no result or control behavior changed.

GLBs are excluded from Git. `web/models.json` pins hashes, sizes, clips and
provenance; `npm run models:sync -- --source DIRECTORY` imports an extracted model
pack offline without replacing a different existing asset. Preserve the pack and
the ignored local models. See `web/README.md`. `viewer.yml` runs unit, build and
browser checks without the generated pack. Playwright 1.64.1 is development only.

The model pack is `C:/Users/agusd/.codex/artifacts/waggle-viewer-models-20261104.zip`.
The viewer runs locally on port 5174; open `?gallery=1`. The five new equipment
models consumed 150 monthly Meshy credits, recorded in the generation checkpoint.

Code progress by eye on 2026-11-04: this gallery/model task 100%; overall viewer
about 68% (was about 63%, higher because asset import, modular equipment, pickup
preview and browser checks now exist); whole project about 83%, unchanged at this
precision. These are judgments about code, not evaluation results. Map geometry,
overlays, live mode and role/action fields in replay are still separate work.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and
PENDING.md. Inspect the current remote, PRs and worktrees. Review the PR for
feat/viewer-assets-complete, stacked on chore/merge-wave-5 (PR 159). Preserve the
original viewer and Meshy worktrees and the separate binary model pack. Import
models using web/models.json and the offline models:sync command. The maintainer
does the visual review; fix their observations with tests. Check the task PR's
CI and browser/model results before merging. Do not invent human pickup or role
state in replay; those fields need a simulator-owned contract. Do not change
safety, fencing, audit, retries, caps, secrets or held-out results.
