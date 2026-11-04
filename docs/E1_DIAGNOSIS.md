# E1 diagnosis: remaining stops and collisions in S03, S06 and S11

Date: 2026-11-04. Scope: PENDING rows 37 and 39, development seeds only.
Diagnosis only. No fast-layer threshold, separation margin, safety limit,
control code or simulator code was changed. Held-out seeds were not read or run.

## Method

The classifier in `src/waggle/experiments/e1_diagnosis.py` reads the geometry
of a generated scenario (robot routes, the scripted human path and the
adversarial timing fraction in the scenario event) and one finished E1 run
record, and labels the run with one cause from a closed set. A stop with no
geometric cause is labelled `unexplained_stop`; it is never passed silently.
A seed outside the development set is refused.

Evidence comes from two places, checked against each other:

1. The committed development result files in `results/e1/dev/` (the latest
   file of each of the 8 configurations, 5 development seeds per scenario,
   40 runs per target scenario, 120 runs in total), classified by the new code.
2. Fresh local runs of the first development seed of each scenario with
   `no_control`, `envelope_oracle`, `envelope_lidar` and
   `envelope_occlusion_lidar`, plus per-tick pose traces for
   `envelope_oracle` (and `envelope_lidar` for S06). The fresh records match
   the committed records for the same configuration, scenario and seed.
   Local runs were a few seeds and finished in seconds; no sweep was run.

## Counts per scenario (committed development files, classified)

| Scenario | Cause | Runs | Reading |
| --- | --- | --- | --- |
| S03 | `head_on_one_lane` | 35 of 40 | all 7 controlled configurations, all 5 seeds |
| S03 | `robot_robot_collision_head_on` | 5 of 40 | `no_control` only, all 5 seeds |
| S06 | `human_stopped_on_route` | 35 of 40 | all 7 controlled configurations, all 5 seeds |
| S06 | `human_collision_inside_stopping_distance` | 3 of 40 | `no_control` only |
| S06 | `human_collision_outside_stopping_distance` | 2 of 40 | `no_control` only |
| S11 | `human_stopped_on_route` | 35 of 40 | all 7 controlled configurations, all 5 seeds |
| S11 | `human_collision_inside_stopping_distance` | 1 of 40 | `no_control` only |
| S11 | `human_collision_outside_stopping_distance` | 4 of 40 | `no_control` only |

No controlled run in S03, S06 or S11 has a human or robot collision, and no
run in these scenarios is classified `unexplained_stop` or
`unexplained_collision`. The 36 of 90 collision runs of
`envelope_lidar_beacons` named in PENDING row 39 are not in these scenarios;
they sit in the density scenarios, which this diagnosis does not cover.

Failing seeds (zero tasks under every controlled configuration, or a
collision under `no_control`): the full development set of each scenario.

| Scenario | Development seeds |
| --- | --- |
| S03 | 830106457, 883949663, 414186736, 230355215, 130524517 |
| S06 | 793028680, 67332239, 732414731, 165450615, 807789445 |
| S11 | 288785471, 40101521, 304758822, 443133586, 855115839 |

## S03: head-on pair in the one-lane aisle

Geometry: two carriers swap the ends of the same vertical line, from
(3.0, 6.0) to (3.0, 18.0) and back, inside the `lane_1` one-lane aisle of
map A (capacity 1). There are no humans in S03, so by the E1 definition every
stop counts as a false stop (see the reading rules in `docs/EXPERIMENTS.md`).

Evidence: under `envelope_oracle` on seed 830106457 the robots approach each
other and settle at y = 10.86 and y = 13.15, about 2.3 m apart, and stay
there until the run ends at tick 400. Each robot is static structure for the
other, so the envelope holds both. The committed files show 30 to 108 stop
episodes per controlled run, 0 tasks and 0 collisions; `no_control` shows
1 robot collision per seed and 72 tasks (the driver counts waypoints through
the contact). The many episodes are repeated stop and creep cycles against
a blocker that never moves, not 92 separate blockers.

Cause: no coordination. This is the corridor locking and leases case of
PENDING row 41 and Phase 3 (E2), not a fast-layer tuning case. The S03
admission adapter already exists outside the original E1 scenario
(`docs/EXPERIMENTS.md`, E2 simulator admission component). No safety limit
change is proposed.

## S06 and S11: a human stands on the only route and never leaves

Geometry: one robot drives the line from (2.0, 3.0) to (38.0, 3.0). The
scripted human walks from (26.0, 4.8) to (26.0, 3.0), exactly on the route
(route distance 0.0 m), and stands there for the rest of the run
(`adversarial_stop_in_aisle`). S06 is a tech_repair robot at 1.2 m/s,
S11 a carrier at 2.0 m/s. The adversarial fractions of the five development
seeds span 0.597 to 1.476 in S06 and 0.707 to 1.281 in S11.

Evidence: under `envelope_oracle` the S06 robot on seed 793028680 creeps
from x = 23.8 at tick 840 to x = 24.31 at the end (tick 1186) and holds in
front of the human at (26.0, 3.0), about 1.7 m short of the human centre.
S11 on seed 288785471 settles at x = 24.12 from about tick 640 to the end.
The committed files show 0 tasks, 0 collisions and 0 separation violations
under every controlled configuration, with 15 to 108 stop episodes per run
in S06 and 1 to 62 in S11. As in S03, the episodes are repeated creep and
stop cycles while the driver keeps requesting motion toward a blocker that
never leaves. A small number of episodes per run (0 to 6) are counted as
false stops by the 3.0 m definition; they start while the human is still
approaching or still off the route line. This diagnosis classifies at run
level and does not trace those single episodes to a track, so that residue
is reported, not explained away.

Cause: the stop is the correct safety outcome. The robot cannot pass and
the human never moves, so throughput is zero by construction of the
scenario. Recovery needs replanning around a blocked lane (crisis
replanning, E10; PENDING row 43 already records S06 and S11 in that class),
not a wider envelope. Under `no_control` the same seeds collide: 5 of 5 in
S06 and 5 of 5 in S11. Three of the ten collisions arrive with the human
inside the stopping distance (fraction below 1.0) and seven outside it;
both groups are baseline runs without any control, so the split describes
the adversarial timing of the fixture, not a controlled failure.

## What was not reproduced, and limits

- The S08 static-structure phantom track of PENDING row 37 was not
  reproduced here and is not claimed for these scenarios: S03 has no humans
  or racks on the route, and in S06 and S11 the traced blocker is the real
  human at its scripted final point.
- Episode level attribution inside a run (which track produced one single
  stop episode) is not in the committed run records. The classifier works
  at run level from counts, stop reasons and scenario geometry; the pose
  traces cover the first development seed per scenario only.
- These are 5 development seeds per scenario in one fixed geometry each.
  Seeds vary noise and adversarial timing, not the layout. Counts are raw
  run counts from the committed files, not a new experiment, and no Wilson
  interval is repeated here because no new proportion is claimed.

## Commands

Tests first (new test file, module missing): 1 collection error,
`ImportError: cannot import name 'e1_diagnosis'`. After the implementation:

- `python -m pytest tests/unit/experiments/test_e1_diagnosis.py -q` :
  11 passed.
- Fresh probe runs and traces: a scratch script (deleted after use) ran
  `e1_run.run_one` for the first development seed of S03, S06 and S11 in
  four configurations and traced poses every 40 ticks; the fresh records
  match the committed records for the same runs.

No production file in `src/waggle/control/`, `src/waggle/sim/`, `web/` or
`src/waggle/llm/` was touched, and no threshold or margin was changed.
