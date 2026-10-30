# Waggle Hive: Last context

Updated: 2026-10-30 (B14 to B17 done and in review, the E1 development run is waiting for the cloud).

## Done last
- B17 `feat/e1-harness` (PR 32): `waggle.sim.sensors.oracle_scan`, package `waggle.experiments` (`e1_config`, `e1_rig`, `e1_run`, `e1_stats`, `e1_report`), `uv run experiments-dev` (development seeds only, no held-out option), `uv run report` (writes `results/e1/dev/report.md`), `.github/workflows/e1.yml` (manual, one job per configuration). No E1 result is committed. 1351 tests.
- B16 `feat/control-reflex` (PR 31): watchdog, e-stop, hazard geofences and telemetry thresholds as arbiter limits (`waggle.control.reflex`, `frames`). Off in E1.
- B15 `feat/control-cpa` (PR 30): constant velocity CPA (`waggle.control.cpa`), track trails and a least squares velocity over at least 10 ticks.
- B14 `feat/control-occlusion` (PR 29, base `main`): occlusion boundaries from range jumps of 0.6 m or more, phantom human cap with the footprint widened by the distance a person walks while the robot reacts and brakes, `extra_limits` in `limit_command`.
- ADR-018, ADR-024, ADR-027 and ADR-028 carry the choices of B14 to B17. PRs 29 to 32 are stacked: 32 on 31 on 30 on 29 on `main`.
- A correction: PR 29, 30 and 31 first said "Protected paths touched: none" although `src/waggle/control/` is protected. The three bodies were edited.

## Current state
- `waggle.control` is complete for E1: envelope, arbiter, limiter, perception, tracking, occlusion, CPA, reflex, `control_step`. About 260 control tests.
- Smoke runs on this machine (a few seeds, not results): the oracle scan harness reproduces the Phase 1 baseline for `no_control` (same counts and final hash) and the baseline human collision of S07 seed 66447779 disappears under the envelope. Control also costs throughput: in the short samples some controlled runs complete 0 waypoints (S03 seed 7 has two robots head-on in a one lane aisle and no humans; S07 seed 66447779, cause not investigated). That is data for E1, not a tuned result.
- The full E1 development run (8 configurations, 90 runs each) was NOT run. It needs `.github/workflows/e1.yml` on `main` first, then a manual dispatch. Held-out seeds were not run.
- Traps met: (1) `waggle.sim.streams` allows only the subsystems robots, humans, lidar, beacons, scenario, so odometry noise uses the `robots` stream; (2) a false stop is defined against humans only, so in scenarios without humans every stop is false; (3) the Bash heredoc breaks on triple quotes, write scripts with the Write tool; (4) a lone return at a wall end is a human candidate (extent zero), so the envelope already slows there; (5) CRLF warnings from git are harmless.
- Open maintainer decisions: PENDING 25 (gates), 34 (stale rows 1 and 3), 35 (merge order and protected paths of PRs 29 to 32), 36 (run the E1 development workflow), 37 (what to do with the stuck and slow runs once the table exists), and the ADR-026 beacon deviation.

## Prompt for the next session
```
Continue Waggle Hive, session brief 2, after B17. Read AGENTS.md, LASTCONTEXT.md, PENDING.md, docs/EXPERIMENTS.md (E1), docs/DECISIONS.md (ADR-026 to ADR-028 and their addenda). Run git fetch, git status, git branch -r, git worktree list, gh pr list.

State: B0 to B13 are on main. B14 to B17 are PRs 29, 30, 31, 32, stacked in that order. Do not merge anything, never push to main, no force push. Do not commit `index (1).html` and do not work on the viewer (PENDING 33).

Do not start B18. Wait for the maintainer to say what comes next. Possible tasks, only on request: (a) read the E1 development result files the maintainer committed under results/e1/dev/ and write the analysis (false approvals first is for the court, here: human collisions first, then separation violations, then the cost in stops and throughput, with the Wilson intervals and every failing seed); (b) if the maintainer asks, investigate why some controlled runs finish with 0 waypoints, with a test first, without loosening any limit; (c) PENDING 36 follow-ups.

Constraints: numpy and the standard library only. waggle.control reads only waggle.sim.observations and waggle.sim.params. Never loosen a safety check. Ask before touching the fencing check, the MCP boundary, the audit logic or the .env. No paid API call. Held-out seeds are not run.
```
