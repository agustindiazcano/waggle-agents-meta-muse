# Waggle Hive demo: script and shot list

Voice: Windows System.Speech, Microsoft Zira Desktop (synthetic, no paid call).
Subtitles: demo/subtitles.srt, same lines and timings.
All ids are presentation mocks: ORD-1042, PKG-8841, TRK-07, TRK-12, T-331, R-B04.

| Shot | Time | Duration | Picture | Narration |
|---|---|---|---|---|
| 1 | 0:00-0:15 | 15 s | Global network, three warehouses, urgent order arrives | Three warehouses. Thirty robots. One urgent order. / ORD-1042: transfer PKG-8841 from WH-A to WH-C. Priority: urgent. |
| 2 | 0:15-0:35 | 20 s | Coordinator to organizer to advisor zoom | One global coordinator assigns the transfer to three cell organizers. / Each organizer directs ten robots. Thirty advisors add caution; deterministic code decides. |
| 3 | 0:35-1:05 | 30 s | Pickup, human crossing, fast-layer stop, resume | WH-B organizer assigns pickup. PKG-8841 attaches to carrier R-B04. / A human crosses the aisle. The fast layer commands a stop. No model is in this loop. / Clear. Motion resumes inside the allowed envelope. |
| 4 | 1:05-1:30 | 25 s | Package label override attempt rejected | A package label tries to add an override instruction. / Screening, strict schema and tool permissions reject it. The order is unchanged. |
| 5 | 1:30-2:00 | 30 s | Overheating alert, ticket, ghost routes, court review | Machine M-B2 reports overheating. Ticket, diagnosis and part reservation open. / Simulated route variants are reviewed. One safe alternative is selected. |
| 6 | 2:00-2:35 | 35 s | Truck delay, global reassignment, delivery | Truck TRK-07 is delayed. The coordinator reassigns the transfer to TRK-12. / PKG-8841 is loaded, moved and delivered. ORD-1042 is complete. |
| 7 | 2:35-2:45 | 10 s | Engineering evidence card | Measured evidence, from committed result files. Development seeds only. |
| 8 | 2:45-3:00 | 15 s | Fleet return, closing card, attribution | Waggle Hive. Models propose. Deterministic code disposes. |

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
