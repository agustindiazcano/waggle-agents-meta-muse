# Waggle Hive: Last context

Updated: 2026-10-30 (B0 to B17 and the map filter on main, E1 dev run 3 done, PR 35 open with the speed metrics, Phase 3 started in parallel by another agent).

## Done last
- `main` has B0 to B17 and PR 34 (ADR-030): a cluster whose points all lie within `map_margin` 0.25 m of a mapped segment is structure, active only when the occlusion cap is on (maintainer option C).
- PR 35 (`exp/e1-speed-metrics`, open): E1 now also records `distance_m` and `speed_sums` per run, and the report shows "Distance vs no_control" and "Mean speed / request" next to tasks. Reason: tasks fall to 0 when a slowed robot misses its first waypoint in a short scene. No limit or stored result changed. `uv run ci` 1363 passed.
- E1 dev run 4 (cloud run 41100237070, PR 35 branch) is in the table below. Correction of an earlier reading: the cliff explains single scenes (S01 to S08), but over all 90 runs the speed cost is real. Mean speed over request is 0.16 to 0.19 and distance over no_control is 0.18 to 0.22, in line with the task ratio. Dense scenes with many robots (S13 to S18) weigh most in these sums.
- Another agent works in parallel on Phase 3 in its own worktree, branch `feat/coordination-leases`: leases, fencing tokens and corridor locking as pure functions in `src/waggle/coordination/`, plus an ADR-031 or higher. It does not touch `waggle.control`, `waggle.experiments`, `waggle.sim` or these context files. When it reports, add its PENDING rows and ADR number here.

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
- Pending maintainer: merge PR 35, PENDING 25 (gates), 34, 40 (task metric: approved, done by PR 35).
- Not done: S14, S15, S18 diagnosis; Phase 3 beyond the first branch; MCP, guard, court, advisors, crisis loop, viewer.
- Traps: the Bash heredoc breaks on triple quotes, write scripts to the scratchpad; `step.py` imports `limit_command` by name, patch `waggle.control.step.limit_command`; `uv run ci` takes 3 to 6 minutes; a watch on a cloud run can return before the jobs finish, check the status.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/DECISIONS.md (ADR-024, ADR-026, ADR-030), docs/GOTCHAS.md. Run git fetch, git status, git branch -r, git worktree list, gh pr list.

State: B0 to B17 and ADR-030 are on main. PR 35 (exp/e1-speed-metrics) adds distance and speed ratio to the E1 report; if it is not merged, branch from it. A parallel agent builds Phase 3 in feat/coordination-leases; do not touch src/waggle/coordination/. Never merge, never push to main, no force push. Do not commit `index (1).html`.

Task, tests first with the failing run shown, uv run ci green before each push:
1. Split speed ratio and distance by scenario from the run 4 result files (gh run download 41100237070) to see which scenes hold the cost.
2. S14, S15, S17, S18 are robot-robot queues and the maintainer decided to leave the fast layer as it is (ADR-028 addendum). Do not change how the envelope treats other robots. Add a per-scenario cost table to the README only from result files.
3. If a control change is made, rerun E1 in the cloud (gh workflow run e1.yml --ref <branch>) and report the table versus run 3.
Then stop and report. Phase 3 integration, MCP, guard and court only when the maintainer says so.
Constraints: numpy and the standard library only, waggle.control reads only waggle.sim.observations and waggle.sim.params, fail closed, no paid API call, held-out seeds not run, ask before touching the fencing check, the MCP boundary, the audit logic or .env.
```
