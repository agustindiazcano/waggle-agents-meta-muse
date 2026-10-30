# Waggle Hive: Last context

Updated: 2026-10-30 (night: B0 to B17, ADR-030, E1 metrics, the A+C decision and the pure Phase 3 model (ADR-031) are on main).

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
- ADR-032 (MCP boundary and guard design, docs only) is on branch `docs/mcp-boundary-adr`. E1 dev results are in PR 39. PR 35 and 37 are merged. No code, migration or `.env` change for the MCP yet.
- Pending maintainer: merge PR 35, PENDING 25 (gates), 34, 40 (task metric: approved, done by PR 35).
- Not done: S14, S15, S18 diagnosis; Phase 3 beyond the first branch; MCP, guard, court, advisors, crisis loop, viewer.
- Traps: the Bash heredoc breaks on triple quotes, write scripts to the scratchpad; `step.py` imports `limit_command` by name, patch `waggle.control.step.limit_command`; `uv run ci` takes 3 to 6 minutes; a watch on a cloud run can return before the jobs finish, check the status.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/DECISIONS.md (ADR-024, ADR-026, ADR-028 with its addendum, ADR-030), docs/EXPERIMENTS.md (E1), docs/GOTCHAS.md. Run git fetch, git status, git branch -r, git worktree list, gh pr list.

State: main has B0 to B17, the map filter (ADR-030, active only with the occlusion cap), the E1 distance and speed columns, and the A+C decision (ADR-028 addendum): the fast layer keeps other robots as static structure, the dense scene cost is reported by scenario, traffic is for Phase 3. E1 dev runs exist only as cloud artifacts (run 41100237070 has the latest files), not in results/e1/dev/. Held-out seeds were not run.
The Phase 3 pure model is on main (PR 37, ADR-031): waggle.coordination.leases and corridors, deterministic, no clock, no database. It is implemented, not evaluated: no persistence, no integration with the simulator, no E2. The worktree ../waggle-feat-leases may be removed after the merge (git worktree remove, the maintainer decides).

Never merge, never push to main, no force push. Do not commit `index (1).html`. Tests first with the failing run shown, Conventional Commits, uv run ci green before each push (3 to 6 minutes, or push and let the CI run decide).

Tasks, ask the maintainer which first if unsure:
1. Phase 3 next step: integrate the pure corridor model with the simulator so that S03 is resolved by admission before entry, then measure E2 on development seeds in the cloud. The database layer and any migration need the maintainer first (AGENTS section 15).
2. Commit the E1 development results from the cloud artifacts into results/e1/dev/ (gh run download 41100237070), in a branch docs/e1-dev-results. Check there is no secret or large file. Held-out files are never committed by an agent.
3. MCP boundary and guard: the design is ADR-032. After the maintainer confirms the allowlist and the first branch (PENDING 47, 48), implement it tests first, starting with the pure schemas and allowlist. Do not write the database layer or a migration, and ask before touching the fencing check, the audit logic or .env.
4. The LLM smoke test branch needs PENDING 4, 5, 9 and 12 first (balances, caps, HTTP client, Meta credits by Nov 4 9 PM ET). Do not start it until the maintainer confirms them. No paid API call before that.
Gates: G2 is tonight (fast layer and E1 on development seeds), G3 Nov 1 night (leases, MCP, E2, E3). Report progress against AGENTS section 18 in a table when asked.
Constraints: numpy and the standard library only, waggle.control reads only waggle.sim.observations and waggle.sim.params, fail closed, held-out seeds not run, ask before touching the fencing check, the MCP boundary, the audit logic or .env.
```
