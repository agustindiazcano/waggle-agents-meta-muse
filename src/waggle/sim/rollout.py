"""Rollouts of a scenario with the rollout lidar, run in parallel across variants (ADR-025).

A rollout is one scenario run from its seed with the fast lidar of every robot. ``run_variants``
runs several of them in worker processes (standard library only) and returns the results in
the order of the specs. Each result depends only on its own spec, so a parallel run equals a
serial run. A worker keeps one static scan cache per map for all the rollouts it runs. The
cache holds no run state, so this does not change any result.
"""

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from waggle.sim import fastlidar, params, scenarios, sensors
from waggle.sim.observations import LidarScan

_CACHES: dict[str, fastlidar.StaticScanCache] = {}


@dataclass(frozen=True)
class RolloutSpec:
    """One rollout: a scenario and seed, how many ticks, and whether the lidar runs."""

    scenario_id: str
    seed: int
    ticks: int
    lidar: bool = True


@dataclass(frozen=True)
class RolloutResult:
    """What a rollout reports: detector counts, final state hash and number of lidar scans."""

    counts: dict[str, int]
    final_hash: str
    scans: int


def _cache_for(map_name: str) -> fastlidar.StaticScanCache:
    cache = _CACHES.get(map_name)
    if cache is None:
        static = sensors.static_segments(scenarios.load_map(map_name))
        cache = fastlidar.StaticScanCache(static, sensors.LidarConfig())
        _CACHES[map_name] = cache
    return cache


def run_rollout(spec: RolloutSpec) -> RolloutResult:
    """Run one rollout from its spec. A pure function of the spec."""
    if spec.ticks < 0:
        raise ValueError("ticks must not be negative")
    scenario = scenarios.generate(spec.scenario_id, spec.seed)
    sim, det = scenarios.build_engine(scenario, {"lidar": len(scenario.robots)})
    scans: list[int] = [0]

    def count(batch: Sequence[LidarScan]) -> None:
        scans[0] += len(batch)

    if spec.lidar:
        robot_params = [params.ROBOT_PARAMS[r.kind] for r in scenario.robots]
        sim.systems.append(
            fastlidar.rollout_system(_cache_for(scenario.map_name), robot_params, count)
        )
    sim.run(spec.ticks)
    return RolloutResult(det.counts(sim.state), sim.state_hash(), scans[0])


def run_variants(specs: Sequence[RolloutSpec], workers: int = 1) -> list[RolloutResult]:
    """Run the specs and return the results in the same order, serially or in processes."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1 or len(specs) <= 1:
        return [run_rollout(spec) for spec in specs]
    with ProcessPoolExecutor(max_workers=min(workers, len(specs))) as pool:
        return list(pool.map(run_rollout, specs))


def worker_count(requested: int | None, jobs: int) -> int:
    """Workers to use: the request or one per job, never more than the jobs."""
    return max(1, min(jobs, requested if requested is not None else jobs))
