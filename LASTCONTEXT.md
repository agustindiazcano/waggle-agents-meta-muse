# Waggle Hive: Last context

Updated: 2026-10-30 (late: ADR-032 branches a, b, c and the S03 admission adapter are on main; nothing is cut).

## Done last
- `main` has B0 to B17 and PR 34 (ADR-030): a cluster whose points all lie within `map_margin` 0.25 m of a mapped segment is structure, active only when the occlusion cap is on (maintainer option C).
- PR 35 (`exp/e1-speed-metrics`, open): E1 now also records `distance_m` and `speed_sums` per run, and the report shows "Distance vs no_control" and "Mean speed / request" next to tasks. Reason: tasks fall to 0 when a slowed robot misses its first waypoint in a short scene. No limit or stored result changed. `uv run ci` 1363 passed.
- E1 dev run 4 (cloud run 41100237070, PR 35 branch) is in the table below. Correction of an earlier reading: the cliff explains single scenes (S01 to S08), but over all 90 runs the speed cost is real. Mean speed over request is 0.16 to 0.19 and distance over no_control is 0.18 to 0.22, in line with the task ratio. Dense scenes with many robots (S13 to S18) weigh most in these sums.
- Phase 3 pure model (PR 37, ADR-031) is on main: leases, fencing tokens and atomic corridor admission, tests with Hypothesis, import contract for `waggle.coordination`. Implemented, not evaluated.

### E1 development runs (runs with a human collision out of 90 | tasks as ratio to no_control)

| Configuration | Run 1 | Run 2 (filter always on) | Run 3 (option C) |
|---|---|---|---|
| no_control | 62 \| 1.00 | 62 \| 1.00 | 62 \| 1.00 |
| radial_lidar | 12 \| 0.01 | 10 \| 0.01 | 12 \| 0.01 |
| envelope_oracle | 13 \| 0.34 | 24 \| 0.65 | 13 \| 0.34 |
| envelope_lidar | 11 \| 0.11 | 21 \| 0.65 | 11 \| 0.11 |
| envelope_lidar_beacons | 12 \| 0.13 | 36 \| 0.65 | 12 \| 0.13 |
| envelope_occlusion_lidar | 12 \| 0.05 | 12 \| 0.23 | 12 \| 0.23 |
| envelope_occlusion_cpa_lidar | 12 \| 0.05 | 12 \| 0.23 | 12 \| 0.23 |
| envelope_occlusion_cpa_lidar_beacons | 13 \| 0.05 | 12 \| 0.22 | 12 \| 0.22 |

Run 2 showed that without the occlusion cap the filter doubles human collisions, so it is only on with the cap. Run 3 confirmed: configurations without the cap return to run 1, those with it keep 12 collisions and gain throughput. Stop episodes stay near 19000 per configuration and most count as false by definition.

### E1 dev run 4: cost columns (same code as run 3, new columns)

| Configuration | Tasks vs no_control | Distance vs no_control | Mean speed / request |
|---|---|---|---|
| radial_lidar | 0.01 | 0.08 | 0.07 |
| envelope_oracle | 0.34 | 0.19 | 0.17 |
| envelope_lidar | 0.11 | 0.18 | 0.16 |
| envelope_lidar_beacons | 0.13 | 0.18 | 0.17 |
| envelope_occlusion_lidar | 0.23 | 0.22 | 0.19 |
| envelope_occlusion_cpa_lidar | 0.23 | 0.22 | 0.19 |
| envelope_occlusion_cpa_lidar_beacons | 0.22 | 0.22 | 0.19 |

Reading: the controlled fleet moves at about a fifth of the requested speed in aggregate. The next step is to split these sums by scenario to see which scenes (the dense ones) hold the cost.

### Why the controlled runs complete few tasks (diagnosed with traces)

| Scenes | Cause | Where it is handled |
|---|---|---|
| S01, S05, S07, S08 with the occlusion cap | The cap slows to about 1 m/s with no stops (S01 seed 160488194: mean speed 0.66 of request, same as the envelope alone, 0.63). A slowed robot misses the first waypoint of a long route in a short scene: a cliff in the task metric. | PR 35 metrics |
| S08 early stalls | Wall faces read as humans | ADR-030 |
| S06, S11, S12, S08 tail | A human stops in the only lane, the robot holds at 1.7 to 1.9 m. Correct behavior without replanning. | Phase 5C, E10 |
| S03 | Two robots head on in a one-lane corridor, both stop forever | Phase 3 corridor locking, E2 |
| S14, S15, S17, S18 (10 and 30 robots) | Robot-robot queues: in 77 to 95 percent of robot-ticks the robot is under 25 percent of its request, and the nearest other robot is 2.0 to 2.5 m away (centre to centre, about nose to tail). Other robots are structure points to the envelope, so a follower treats a moving leader as a wall and waits for a full stopping gap. Speed ratio of these scenes is 0.04 to 0.3 and they hold most of the distance, so they set the aggregate 0.19. | Decided A and C (PENDING 45, ADR-028 addendum): the fast layer is not changed, the cost is reported by scenario, Phase 3 traffic control addresses it |

## Current state
- All PRs through 47 are merged. On main: ADR-032 (MCP boundary and guard design) with the pure allowlist, bounds and strict schemas (PR 43), token authentication against a store protocol (PR 45) and the deterministic sanitizers (PR 42); E1 dev results (PR 39); the pure lease and corridor model (PR 37) and the S03 simulator admission adapter `waggle.experiments.corridor_admission` (PR 47, by another agent, ADR-031 addendum). All implemented, not evaluated. No database, migration, audit, rate limit, server, classifier or `.env` change.
- Maintainer decision 2026-10-30: nothing is cut. Never suggest cutting or deferring scope. AGENTS section 18 is the build order and the gates are progress checks.
- Pending maintainer: PENDING 47 (confirm the allowlist table, say whether branches d and e may start, including the migration), 48 (bounds are copied with a consistency test, not imported from the simulator), 49, 4, 5, 9 and 12 before any paid call.
- Rough progress (agent estimate, not a measure): block 1 ~85 percent (no end-to-end slice, held-out seeds not run), block 2 ~35 percent (pure model and S03 adapter, no E2, no database), block 3 ~15 percent (no audit, rate limit, server, classifier, E3, court, E4), blocks 4 to 7 near 0. E1 dev: controlled runs still have 12 of 90 runs with a human collision and about 0.22 of the tasks of no_control.
- Not done: E2, the Phase 3 database layer, the MCP audit and server, the guard classifier, E3, court E4, crisis loop, advisors, maintenance, viewer.
- Traps: write Python files with the Write tool, the Bash heredoc breaks on triple quotes; run `git branch --show-current` before every commit (a session once stood on main by mistake; the harness denied the commit); `step.py` imports `limit_command` by name, patch `waggle.control.step.limit_command`; `uv run ci` takes 3 to 6 minutes; a PR merged into a branch whose own PR already merged never reaches main, check `git merge-base --is-ancestor`; the README test reads the latest `no_control_*.json` by name; the original S03 stays for E1, use `build_s03_admission` for admission.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/DECISIONS.md (ADR-028 addendum, ADR-030, ADR-031 with its addendum, ADR-032), docs/EXPERIMENTS.md (E1, E2, E3), docs/GOTCHAS.md. Run git fetch, git status, git branch --show-current, git branch -r, git worktree list, gh pr list --state all --limit 12.

Rule from the maintainer: nothing is cut. Never suggest cutting, deferring or dropping scope. Report gaps against the build order in AGENTS section 18 and say what work closes them.

State: main has B0 to B17, E1 dev results (results/e1/dev, commit 94bacc4), the pure lease and corridor model, the S03 admission adapter, ADR-032 with schemas, identity and sanitizers. Held-out seeds were not run. Check that no merged branch missed main (git merge-base --is-ancestor).

Never merge, never push to main, never commit on main (check git branch --show-current before each commit), no force push. Do not commit `index (1).html`. Tests first with the failing run shown, Conventional Commits with the Co-Authored-By trailer, one branch per task, uv run ruff, mypy and the touched tests before each push, then let the CI decide. Write Python files with the Write tool, not Bash heredocs.

Tasks, ask the maintainer which first if unsure:
1. Guard classifier interface in waggle.governance: protocol, label policy through the existing screen(), fail closed on parse failure, timeout and uncertain, a mock classifier for tests, no network, no paid call, stdlib only.
2. E2 on development seeds: add a workflow_dispatch workflow (same pattern as .github/workflows/e1.yml) that runs the S03 admission scenario with admission on and off over the development seeds and writes JSON to results/e2/dev/ with commit, seed set and raw counts (double occupants, deadlocks, completed routes, Wilson 95 percent intervals). Run it in the cloud, download the artifact, commit results in a docs branch. No database layer.
3. E3 case corpus: write the injection cases for T1 to T6, T11 and T18 with the target layer declared before any run (AGENTS section 9). Labels are decided by the maintainer; new cases stay pending until reviewed.
4. ADR-032 branches (d) audit table and rate-limit repository with a migration, and (e) server wiring: ask the maintainer first (migration, audit logic, MCP boundary). Propose the schema in the PR, do not run a migration.
5. The LLM smoke test branch needs PENDING 4, 5, 9 and 12 first. Do not start it, and make no paid API call, until the maintainer confirms them.
Gates: G2 tonight (fast layer and E1 on development seeds), G3 Nov 1 night (leases, MCP, E2, E3), G4 Nov 2 night. Report progress in a table when asked.
Constraints: numpy and the standard library only, waggle.control reads only waggle.sim.observations and waggle.sim.params, fail closed, held-out seeds not run, ask before touching the fencing check, the audit logic, a migration or .env.
```
