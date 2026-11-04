# Waggle Hive: Last context

Updated: 2026-11-04. README task on `docs/readme-project`, based on main
`7b99bbf` (PR 174, Meta Wonder routing merged). Other agents continue in separate
worktrees; preserve their work. The maintainer reviews and merges every PR.

Code progress of the project (estimate by eye, code only): 87% on 2026-11-04,
margin about 3 points. Unchanged: this task updates documentation and its checks,
not product code. Existing per-task estimates remain in PENDING.md.

## Done last

- Rewrote README: warehouse problem, task flow, architecture, implementation versus
  pending integration, configured model roles, E1/E2/E8/E9 evidence, E3 to E10 gaps,
  hackathon requirement/evidence matrix, viewer setup, configuration and disclosure.
- Verified the official Meta event page for Indie Developer, Push the Frontier
  and public judging descriptions. Antigravity web search timed out; direct web
  access worked. The linked rules/waiver returned only a loading page. Full
  eligibility, live Meta use, asset rights, video/live links and submission remain
  explicit checks, not claims of complete compliance.
- Updated two old documentation tests that required implemented layers to remain
  labeled as unimplemented. Targeted documentation/provider/style suite: 181 passed.
  Changed-test Ruff check and formatting pass. No product behavior changed.
- `uv run replay-verify web/public/demo.jsonl` fails at tick 4 against current code;
  `--digest-only` passes. README distinguishes playback/integrity from resimulation;
  the fixture is unchanged. Full local CI was stopped at the maintainer request:
  this is a README task; do not run more tests. The branch was pushed without
  bypass flags; remaining CI belongs in GitHub Actions.

## Current state

- Main at task start contains PRs 163 to 170 and 174, including viewer overlays,
  E8 reporting, crisis proposer, organizer E5 and E9 planted defects. Fetch origin
  before continuing: other agents are merging newer work.
- Remaining integration includes production E4/court, E5 service/call logging,
  database-backed E6 diagnosis, E10 harness/caller, multimodal providers, fleet
  planner and package consistency checks. Inspect newer branches before duplicating.
- README uses historical committed development results, not measurements of HEAD.
  E1 still has human collisions and substantial throughput loss; E2 is a five-seed
  admission comparison, not full chaos; E9 covers four declared planted defects.
- Console balances/caps/prices, reviewed data/labels, asset provenance and final
  delivery checks remain in PENDING.md and SUBMISSION.md. No paid call, migration,
  held-out run, safety change or result-file edit occurred in the README task.
- Preserve dirty asset/global-custody worktrees and the separate viewer asset pack.
  Never merge `docs/context-wave3`; remote branch cleanup belongs to the maintainer.
  Viewer port is 5174; port 5173 belongs to another project.

## Prompt for the next session

Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md and PENDING.md first, inspect
status, branches and worktrees, and fetch origin. Review docs/readme-project and
its PR/CI before the maintainer merges. The README now explains implemented scope,
measured development evidence and hackathon checks with explicit pending items.
Confirm the current branch and cloud results before changing those statuses.
Project code remains about 87% plus/minus 3 points by eye; this documentation task
adds no product code. The example replay passes digest checks but resimulation
against current code differs at tick 4; do not call it a current regression pass.
Inspect other agents' work before starting production court, maintenance, crisis
or viewer tasks. Preserve all unmerged work. No paid call, held-out run, migration,
secret access or safety change is authorized by this handoff. Agents never merge.
