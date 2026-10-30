"""Rollouts with the fast lidar, serial and in worker processes."""

import pytest

from waggle.sim import rollout

SPECS = [rollout.RolloutSpec("S14", seed, 60) for seed in (1, 2, 3)]


def test_a_rollout_is_a_pure_function_of_its_spec() -> None:
    assert rollout.run_rollout(SPECS[0]) == rollout.run_rollout(SPECS[0])
    assert rollout.run_rollout(SPECS[0]).final_hash != rollout.run_rollout(SPECS[1]).final_hash


def test_scans_are_counted_on_lidar_ticks() -> None:
    result = rollout.run_rollout(rollout.RolloutSpec("S14", 1, 9))
    assert result.scans == 3 * 10  # ticks 0, 4 and 8 for ten robots
    assert rollout.run_rollout(rollout.RolloutSpec("S14", 1, 9, lidar=False)).scans == 0


def test_the_lidar_does_not_change_the_trajectory() -> None:
    """Scans read ground truth and draw from their own streams, so they never move a robot."""
    with_lidar = rollout.run_rollout(rollout.RolloutSpec("S14", 2, 80))
    without = rollout.run_rollout(rollout.RolloutSpec("S14", 2, 80, lidar=False))
    assert with_lidar.counts == without.counts
    assert with_lidar.final_hash != without.final_hash, "the lidar streams are part of the hash"


def test_parallel_variants_equal_serial_variants_in_the_same_order() -> None:
    serial = rollout.run_variants(SPECS, workers=1)
    parallel = rollout.run_variants(SPECS, workers=2)
    assert parallel == serial
    assert [r.final_hash for r in parallel] == [rollout.run_rollout(s).final_hash for s in SPECS]


def test_invalid_arguments_are_rejected() -> None:
    with pytest.raises(ValueError):
        rollout.run_variants(SPECS, workers=0)
    with pytest.raises(ValueError):
        rollout.run_rollout(rollout.RolloutSpec("S14", 1, -1))


def test_worker_count_never_exceeds_the_jobs() -> None:
    assert rollout.worker_count(None, 5) == 5
    assert rollout.worker_count(8, 5) == 5
    assert rollout.worker_count(2, 5) == 2
    assert rollout.worker_count(3, 0) == 1
