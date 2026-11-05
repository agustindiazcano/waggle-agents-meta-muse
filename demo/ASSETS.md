# Demo assets

| Asset | Source | Status |
|---|---|---|
| three.module.min.js (0.170.0) | Copied from viewer-capture worktree `web/node_modules/three/build/` | Vendored for offline capture; same version as web/package.json |
| Narration WAV lines 00-14 | Windows System.Speech, Microsoft Zira Desktop, generated locally | Synthetic voice; no paid call |
| Meta floor decal | Canvas-drawn loop and wordmark in demo/index.html | Placeholder pending an official Meta logo asset supplied by the maintainer. Not an official asset. Replace before publication. |
| Banner copy | Plan docs/VIDEO_DEMO_PLAN.md: "Powered by Meta Muse" / "Agustin Diaz Cano" / "MS Candidate, Systems Engineering" | Working copy. Final brand wording and "Built with Muse Spark Open" attribution to be verified by the maintainer before publication. Closing card carries that line. |
| GLB robot models | Not used in this cut. Robots are procedural meshes. | The gallery GLB pack (web/models.json) was not integrated; noted as pending visual upgrade. |
| Blue_Delivery_Truck.glb (68.3 MB, 1 mesh, no animations, sha256 79d530308b868b77e624e7027dd4fbe5729d8f314af6cf1fd13dfb45ad2cce1d) | Supplied by the maintainer in assets/ on 2026-11-04 | Integrated as exterior decoration: loaded with vendored GLTFLoader, normalized to 10 m, used for the TRK-12 truck on the front road. Other trucks stay procedural for capture performance. Stored in the repository with Git LFS on branch feat/video-demo. |
| Shipping_Container.glb (15.2 MB, 1 mesh, no animations, sha256 c505aec026bf1bf4ff9f86aa28653d13227df7484fb57f6c54e2072646654ff6) | Supplied by the maintainer in assets/ on 2026-11-04 | Integrated: one container beside each warehouse dock, outside the roads. Stored with Git LFS. |
| worker-1.glb (10.0 MB, clips Running/Walking/Idle_11/walking_2_inplace, sha256 3556ed28a371a90ab15e1c05ea23d5444b79f27fa67b119bc1489825546a52e4) | Supplied by the maintainer in assets/ on 2026-11-04 | WH-A dock worker, Idle_11. Stored with Git LFS. |
| worker-2.glb (10.5 MB, same clips, sha256 c5ff97fa7901846be57a985afb7afd94f325cfec8359fc56edd54735de5a91b2) | Supplied by the maintainer in assets/ on 2026-11-04 | Aisle-crossing human in WH-B, Walking clip, replaces the red box figure. Stored with Git LFS. |
| worker-3.glb (10.2 MB, clips Running/Walking/Idle_11/walking_2, sha256 2293fa7647e23576f65878fd02d9f6b7fe56124331e9ada9bd62bbbe3eb49c63) | Supplied by the maintainer in assets/ on 2026-11-04 | WH-B dock worker, Idle_11. Stored with Git LFS. |
| worker-4.glb (9.9 MB, clips Running/Walking/Idle_11/walking_2_inplace, sha256 7b9f09153740fcfbc66dca785fd6e5906a4bb16afc20fcea8507fde4c325f078) | Supplied by the maintainer in assets/ on 2026-11-04 as the "(1)" file | WH-B worker beside machine M-B2, Idle_11. Fourth distinct worker: its sha256 differs from worker-1, so it is kept, not a duplicate. Stored with Git LFS. |

Demo events (ORD-1042, PKG-8841, TRK-07, TRK-12, T-331) are presentation mocks.
They are not simulator ground truth, audit records, experiment results or model logs.
The engineering card cites only committed files: results/e1/dev/report.md,
results/e2/dev/s03_admission_f1b26ea3f5c7_20261101T185947Z.json and
results/e9/dev/planted.json, all development seeds.
