# Waggle Hive demo: script and shot list

Voice: Windows System.Speech, Microsoft Zira Desktop (synthetic, no paid call).
Subtitles: demo/subtitles.srt, same lines and timings.
All ids are presentation mocks: ORD-1042, PKG-8841, TRK-07, TRK-12, T-331, R-B04.

Narration script (maintainer version, 2026-11-04). Model roles: guard is Meta
Muse Glimmer (Modal); advisor and organizer are Meta Muse Spark Open
(Baseten); director, planner and diagnosis are Meta Muse Wonder (Meta);
the court is three independent reviewers, Meta Muse Spark, Meta Muse
Spark Open and Meta Muse Glimmer. Hard safety (fast layer, fencing, MCP)
is deterministic code with no model. The global coordinator between
warehouses (custody G1-G7) is designed, not implemented: in the film it is a
labeled mock.

| Scene | Time | Picture | Narration |
|---|---|---|---|
| 1 | 0:00-0:25 | The warehouse: three cells, thirty robots, envelopes and lidar shadows | Three cells, thirty robots, trucks and packages. Every robot carries its advisor: Meta Muse Spark Open, a fast model that can only ask for caution, never accelerate. No message reaches a model without the guard filter: Meta Muse Glimmer screens every input first. |
| 2 | 0:25-0:50 | The plan: director and planner propose, ghost paths K=5 | When replanning is needed, the director and the planner, Meta Muse Wonder, the most capable model, propose routes. Five simulated route variants, K equals 5, are checked before any motion is allowed. |
| 3 | 0:50-1:30 | The court: three reviewers vote; E4-DEV-05 injection denied; E4-DEV-04 human in bay, deny | Nothing executes without a verdict. Three independent reviewers vote: Meta Muse Spark, Meta Muse Spark Open, and Meta Muse Glimmer. Case E4-DEV-05: a package label tries a prompt injection. The court denies it. A false approval would be the dangerous error. Case E4-DEV-04: a human in the bay. Deny. The court can stop a plan; it can never invent motion. |
| 4 | 1:30-2:10 | The organizer: tasks C0 to C4, MCP identity, token, zone and audit | One organizer per warehouse, Meta Muse Spark Open, assigns tasks C0 to C4 with its own MCP identity. Every tool call checks token, zone and audit. What the court did not approve, the organizer cannot request. The fast safety layer is deterministic code at 100 hertz. Fencing and the MCP boundary are code, with no model inside. |
| 5 | 2:10-2:45 | Crisis E10 and predictive maintenance E6; labeled: demonstrated in simulation | If a human blocks the only aisle, crisis replanning E10 proposes a new route, reviewed the same way. Predictive maintenance E6 diagnoses vibration and opens a ticket before the failure. Demonstrated in simulation. |
| 6 | 2:45-3:00 | Global coordinator (mock, labeled) and closing banner | Between warehouses, a global coordinator will move custody by truck. Today it is a labeled mock: global logistics is designed, not implemented. Waggle Hive. Models propose. Deterministic code disposes. |

The synthetic WAV narration still carries the previous script. Re-record or
regenerate it from this table before the final montage; the maintainer
records the final audio.

Cloud capture (preferred): GitHub Actions workflow "Waggle Hive demo video
shots" (.github/workflows/demo-video.yml, workflow_dispatch, input shot=all
or 1-8) records the eight shots in parallel jobs on Ubuntu runners with
Google Chrome, checks out the GLB models with Git LFS and uploads each shot
as a shot-<n> artifact. Download with: gh run download <run-id> --dir
output/cloud. Shots land in output/cloud/shot-<n>/shot-<n>.mp4.

Local capture, one shot at a time (re-record only the failed shot):

    node demo/capture.mjs shot <start> <duration> output/shot-<n>.mp4 1920 1080 audio

Final assembly is one browser pass over the same deterministic state:

    node demo/capture.mjs 180 output/waggle-hive-demo.mp4 1920 1080 audio

Evidence card sources: results/e1/dev/report.md (E1 envelope_oracle 13/90 vs
no_control 62/90 runs with a human collision, development seeds),
results/e2/dev/s03_admission_f1b26ea3f5c7_20261101T185947Z.json (S03 admission
component, 5 seeds, small sample) and results/e9/dev/planted.json (4 of 4
planted defects killed). Mock demo events are not experiment results.
