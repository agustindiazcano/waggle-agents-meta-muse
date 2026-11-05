# Validation and reproduction notes

The README presents the implementation and recorded outcomes. This document keeps
protocol boundaries and reproduction details alongside that evidence.

## Measurement scope

These boundaries describe what the published evidence measures.

- Simulation only: 2D physics on the floor plane with 3D rendering. Height is not modeled.
  Telemetry, manuals and failure history are synthetic; humans are scripted/adversarial.
  The lidar is simulated. Vision is not in the control loop. No physical robot validation.
- Deterministic reproduction requires the same platform and numpy version.
  The published E1 cloud run used Linux; result files identify their platform and commit.
- Simulation validation and unanimous model review are not formal verification or safety proofs.
  The stopping/separation approach does not imply standards compliance or certification.
- Control timings are code latencies inside a simulator, not hardware real-time guarantees.
- Live Meta text API connectivity and PostgreSQL integration are tested as listed above.
  E5/E6 benefit, E7 accuracy and live E10 outcomes are implemented, not evaluated.
  Voice/vision operator UI and physical deployment are outside the recorded evaluations.
- [Multi-warehouse logistics](MULTI_WAREHOUSE_PLAN.md) is a planned extension,
  not implemented or evaluated as part of the local system described here.


## Evaluation coverage

E1 disables the watchdog, geofence and e-stop reflex limits to isolate the compared
configurations. The controls reduced collisions versus the baseline, with remaining
human collisions and lower throughput. Occlusion plus CPA did not improve the
human-collision count over the LiDAR envelope in the published run.
E2 admission evaluates fixed S03 geometry with sensor/odometry noise; it is separate
from the PostgreSQL killed-worker chaos protocol. Five runs per arm is a small sample.
E8 rollout optimization reached about 3.1x; the 2 s and 5x targets were not met.

The live Meta tests exercise API requests, responses, token accounting and cost
checks. E4's four recorded campaigns use scripted reviewers. E5/E6 benefit,
E7 accuracy and live E10 outcomes are implemented, not evaluated.
E4's development set contains eight provisional agent-drafted reviewed cases;
cross-family configuration D is excluded by ADR-097. E9 planted-defect results
are published; the separate mutation workflow 41942126363 failed.
Result files identify their commits and platforms; they are not measurements of
all subsequent HEADs. No held-out experiment results are published in the README.

## Viewer reproduction

The recorded demo is S01 development seed 7, labeled fixture0. It is a replay
example and does not contain every safety overlay. Digest-only verification checks
file integrity. Resimulation against the audited code differs at tick 4, so this
fixture is not a current simulator regression reference.
Model-pack setup and hash checking are documented in [web/README.md](../web/README.md).
The standalone Vite command needs an explicit proxy to the Python API for /ws/live.
That API is read-only, unauthenticated and bound to localhost by default.
The interactive presentation and global video scenes use scripted presentation events.

## Repository safeguards and publication

Hooks and CODEOWNERS are a weak control: they depend on repository settings.
Required review and branch protection remain maintainer responsibilities.
The pre-push gate requires a green full-CI stamp on HEAD. At this audit, publication
is blocked by the missing stamp; project policy also forbids full local suites.
The e57d41c CI snapshot has four failures: E9 fork context, Markdown links,
result-directory layout and text style. This documentation branch repairs the links.
See [PENDING.md](../PENDING.md) for the remaining fixes.

## Source-size snapshot

Measured at commit 8cdf754 on November 4, 2026, as physical lines including blank
lines and comments, excluding dependencies, generated assets and demo/vendor:

| Tree | Files | Lines |
|---|---|---|
| src/waggle, Python | 228 | 31,507 |
| web/src, TypeScript | 21 | 2,312 |
| tests, Python | 325 | 36,478 |
| web/test, TypeScript and MJS | 19 | 911 |
| Source total | 249 | 33,819 |
| Test total | 344 | 37,389 |

Count method: sum len(path.read_text(encoding="utf-8").splitlines()) across the
listed trees and extensions. These are size measurements, not coverage percentages.
