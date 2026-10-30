# Waggle Hive: Last context

Updated: 2026-10-30 (B14 to B17 on main, E1 dev run twice, map filter PR 34 open).

## Done last
- PRs 29 to 33 are on `main` (B14 occlusion, B15 CPA, B16 reflex, B17 E1 harness; PR 33 carried B15 to B17 because 30 to 32 were merged into stacked bases, the GOTCHAS trap).
- E1 development run 1 (cloud run 41086309588, commit ce8f92d, 90 runs per configuration, dev seeds only): control cuts human collisions but throughput collapses.
- Diagnosis (S08 seed 102612522, oracle scan): wall and rack faces seen at an angle split into clusters under `human_max_extent`, became human tracks, coasted up to 80 ticks with a ring growing at the human speed bound, and triggered ESTOP. The real human was 10 m away.
- Fix on branch `exp/e1-diagnose-stops`, PR 34 (ADR-030): `ControlInputs.map_segments`; a cluster whose points are all within `map_margin` 0.25 m of a mapped segment is structure. Maintainer decision C: the filter is active only when `use_occlusion` is on (second commit on the branch, local CI to be rerun before the push).
- E1 development run 2 (cloud run 41095424297, with the filter on in every configuration): throughput recovered, safety worse without the occlusion cap.

### E1 dev run 1 versus run 2 (runs with a human collision out of 90, tasks as ratio to no_control)

| Configuration | Collisions run 1 | Collisions run 2 | Throughput run 1 | Throughput run 2 |
|---|---|---|---|---|
| no_control | 62 | 62 | 1.00 | 1.00 |
| radial_lidar | 12 | 10 | 0.01 | 0.01 |
| envelope_oracle | 13 | 24 | 0.34 | 0.65 |
| envelope_lidar | 11 | 21 | 0.11 | 0.65 |
| envelope_lidar_beacons | 12 | 36 | 0.13 | 0.65 |
| envelope_occlusion_lidar | 12 | 12 | 0.05 | 0.23 |
| envelope_occlusion_cpa_lidar | 12 | 12 | 0.05 | 0.23 |
| envelope_occlusion_cpa_lidar_beacons | 13 | 12 | 0.05 | 0.22 |

Stop episodes stay near 19000 per configuration and most are false stops by definition. They come mostly from S14, S15, S18 (dense scenes) and S03.

## Current state
- `main` has B0 to B17. Branch `exp/e1-diagnose-stops` (PR 34) has the PENDING note, ADR-030, the map filter and the option C change.
- Open problems, not fixed: (1) S03 two robots head on in a one-lane corridor never complete a task: a deadlock for corridor locking (Phase 3, E2), not for perception. (2) `envelope_lidar_beacons` has 36 of 90 collision runs without the occlusion cap, cause unknown (check whether a beacon no longer merges with a cluster, giving a wrong or duplicate track). (3) S08 completes 0 tasks because the route is about 38 m and the scene lasts 1013 ticks, so any slowdown misses the first waypoint: the task metric is a cliff, consider normalizing by scene length (maintainer and agent). (4) S06 and S11 are undiagnosed. (5) The occlusion cap gives 0.22 to 0.23 throughput: safe but slow.
- Pending maintainer: merge PR 34 (touches `src/waggle/control/` and `docs/DECISIONS.md`), PENDING 25 (gates), 34.
- Probe scripts used for the diagnosis were in the session scratchpad and are not in the repo. The idea: wrap `control_step` in `waggle.experiments.e1_rig` and print tracks, reasons and gaps at the first ESTOP.
- Traps: the Bash tool heredoc breaks on triple quotes, write scripts to the scratchpad; `step.py` imports `limit_command` by name, so a probe must patch `waggle.control.step.limit_command`; `uv run ci` takes about 4 min now.

## Prompt for the next session
```
Continue Waggle Hive. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/DECISIONS.md (ADR-024, ADR-026, ADR-030), docs/GOTCHAS.md. Run git fetch, git status, git branch -r, git worktree list, gh pr list.

State: B0 to B17 are on main. PR 34 (exp/e1-diagnose-stops) holds the map filter (ADR-030, active only with the occlusion cap). If it is merged, branch from main; otherwise from exp/e1-diagnose-stops. Never merge, never push to main, no force push. Do not commit `index (1).html`.

Task, tests first with the failing run shown, uv run ci green before each push:
1. Explain the 36 of 90 collision runs of envelope_lidar_beacons in E1 run 2 (cloud run 41095424297): pick 2 or 3 failing seeds from its report, trace tracks and reasons at the collision, find the cause. Any fix is a new branch, never loosens a limit, and the filter and beacons interplay goes into ADR-030 or a new ADR.
2. Diagnose S06, S11 and the remaining stops of S08 the same way. Report causes in a table.
3. Propose, do not apply, a task metric normalized by scene length (S08 is a cliff). Ask the maintainer.
4. Rerun E1 in the cloud (gh workflow run e1.yml --ref <branch>) after any control change and report the table versus run 2.
Then stop and report. Phase 3 (leases, corridor locking for S03, E2) starts only when the maintainer says so.
Constraints: numpy and the stdlib only, waggle.control reads only waggle.sim.observations and waggle.sim.params, fail closed, no paid API call, held-out seeds not run, ask before touching the fencing check, the MCP boundary, the audit logic or .env.
```
