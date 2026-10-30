# E1 development results

Development seeds only. Held-out seeds were not run. Every control value is an assumption that is not calibrated. Samples are small: 90 runs per configuration. Runs with a human collision are counted per run, and the counts of episodes are not independent samples. A false stop is a stop that starts with every human farther than 3.0 m, so in a scenario without humans every stop is a false stop, whatever stopped the robot. Latency is the code latency of `control_step` on the platform listed below, not a real-time bound.

## Safety

| Configuration | Runs with a human collision (Wilson 95%) | Human collisions | Robot collisions | Separation violations | Near misses | Human collisions without unavoidable cases |
| --- | --- | --- | --- | --- | --- | --- |
| `no_control` | 62/90 (68.9%, 58.7% to 77.5%) | 107 | 1027 | 125 | 218 | 107 |
| `radial_lidar` | 12/90 (13.3%, 7.8% to 21.9%) | 48 | 0 | 65 | 103 | 48 |
| `envelope_oracle` | 13/90 (14.4%, 8.6% to 23.2%) | 49 | 0 | 65 | 101 | 49 |
| `envelope_lidar` | 11/90 (12.2%, 7.0% to 20.6%) | 38 | 0 | 63 | 90 | 38 |
| `envelope_lidar_beacons` | 12/90 (13.3%, 7.8% to 21.9%) | 40 | 0 | 59 | 90 | 40 |
| `envelope_occlusion_lidar` | 12/90 (13.3%, 7.8% to 21.9%) | 46 | 0 | 63 | 99 | 46 |
| `envelope_occlusion_cpa_lidar` | 12/90 (13.3%, 7.8% to 21.9%) | 46 | 0 | 62 | 99 | 46 |
| `envelope_occlusion_cpa_lidar_beacons` | 12/90 (13.3%, 7.8% to 21.9%) | 46 | 0 | 63 | 98 | 46 |

## Cost

| Configuration | Stop episodes | False stops | Tasks | Throughput vs no_control | Distance vs no_control | Mean speed / request | Median latency (us) | Worst run p99 (us) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `no_control` | 0 | 0 | 6198 | 1.00 | 1.00 | n/a | n/a | n/a |
| `radial_lidar` | 32221 | 31613 | 37 | 0.01 | 0.08 | 0.07 | 197 | 5890 |
| `envelope_oracle` | 19326 | 18044 | 2099 | 0.34 | 0.19 | 0.17 | 228 | 6335 |
| `envelope_lidar` | 20736 | 19571 | 651 | 0.11 | 0.18 | 0.16 | 307 | 7697 |
| `envelope_lidar_beacons` | 20924 | 19672 | 783 | 0.13 | 0.18 | 0.17 | 363 | 9744 |
| `envelope_occlusion_lidar` | 19136 | 17946 | 1433 | 0.23 | 0.22 | 0.19 | 1336 | 11033 |
| `envelope_occlusion_cpa_lidar` | 19112 | 17952 | 1433 | 0.23 | 0.22 | 0.19 | 900 | 7200 |
| `envelope_occlusion_cpa_lidar_beacons` | 19488 | 18161 | 1346 | 0.22 | 0.22 | 0.19 | 1542 | 11353 |

## Ablation pairs (change from the first to the second, same seeds)

| Block | From | To | Human collisions | Separation violations | Stop episodes |
| --- | --- | --- | --- | --- | --- |
| any control | `no_control` | `radial_lidar` | -59 | -60 | +32221 |
| swept footprint | `radial_lidar` | `envelope_lidar` | -10 | -2 | -11485 |
| cost of real sensing | `envelope_oracle` | `envelope_lidar` | -11 | -2 | +1410 |
| beacons | `envelope_lidar` | `envelope_lidar_beacons` | +2 | -4 | +188 |
| occlusion cap | `envelope_lidar` | `envelope_occlusion_lidar` | +8 | +0 | -1600 |
| CPA | `envelope_occlusion_lidar` | `envelope_occlusion_cpa_lidar` | +0 | -1 | -24 |

Envelope with CPA but without the occlusion cap is not run.

## Failing seeds

- `no_control` (81): S01/160488194, S01/419688070, S01/619865736, S01/692763450, S02/326935064, S02/376988137, S02/710301817, S02/825337471, S03/130524517, S03/230355215, S03/414186736, S03/830106457, S03/883949663, S04/200467740, S04/383286097, S04/555190957, S04/821336371, S05/44671688, S05/314832476, S05/684495231, S05/842368745, S05/861685585, S06/67332239, S06/165450615, S06/732414731, S06/793028680, S06/807789445, S07/66447779, S07/420555216, S07/451650604, S07/478319539, S07/980757511, S08/102612522, S08/212395693, S08/235622891, S08/382823189, S09/705967957, S09/757652174, S09/856954589, S09/995766752, S10/96712523, S10/290587930, S10/512558154, S10/611369257, S10/741635605, S11/40101521, S11/288785471, S11/304758822, S11/443133586, S11/855115839, S12/202469928, S12/213496709, S12/796499750, S12/848272079, S12/968457897, S13/593303039, S13/633021836, S13/719883213, S14/40238984, S14/52744551, S14/567737527, S14/810184639, S14/820765836, S15/74125674, S15/82473746, S15/229344423, S15/545157448, S15/608804536, S16/8893461, S16/317022959, S16/857583022, S17/217899087, S17/281201543, S17/339866399, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `radial_lidar` (12): S13/313487353, S15/82473746, S16/8893461, S16/317022959, S17/281201543, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `envelope_oracle` (13): S13/633021836, S15/82473746, S16/317022959, S16/857583022, S17/217899087, S17/339866399, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `envelope_lidar` (11): S13/633021836, S15/82473746, S16/317022959, S17/217899087, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `envelope_lidar_beacons` (12): S13/633021836, S15/82473746, S16/317022959, S16/857583022, S17/217899087, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `envelope_occlusion_lidar` (12): S13/633021836, S15/82473746, S16/8893461, S17/217899087, S17/339866399, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `envelope_occlusion_cpa_lidar` (12): S13/633021836, S15/82473746, S16/8893461, S17/217899087, S17/339866399, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012
- `envelope_occlusion_cpa_lidar_beacons` (12): S13/633021836, S15/82473746, S16/8893461, S17/217899087, S17/339866399, S17/601969674, S17/962258108, S18/47264320, S18/141178730, S18/375870558, S18/493284782, S18/730892012

Unavoidable cases (0): none

## Provenance

| Configuration | Commit | Date | Platform |
| --- | --- | --- | --- |
| `no_control` | 94bacc41a4 | 2026-10-30T17:36:38+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `radial_lidar` | 94bacc41a4 | 2026-10-30T17:39:12+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `envelope_oracle` | 94bacc41a4 | 2026-10-30T17:40:05+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `envelope_lidar` | 94bacc41a4 | 2026-10-30T17:40:31+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `envelope_lidar_beacons` | 94bacc41a4 | 2026-10-30T17:41:49+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `envelope_occlusion_lidar` | 94bacc41a4 | 2026-10-30T17:43:40+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `envelope_occlusion_cpa_lidar` | 94bacc41a4 | 2026-10-30T17:42:03+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
| `envelope_occlusion_cpa_lidar_beacons` | 94bacc41a4 | 2026-10-30T17:47:34+00:00 | Linux-7.0.0-1017-azure-x86_64-with-glibc2.39 |
