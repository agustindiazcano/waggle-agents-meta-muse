"""Tests for finite-burst fleet extrapolation, not measured fleet performance."""

import math
import random

import pytest

from waggle.experiments.e8_extrapolation import extrapolate


def test_constant_latency_has_known_burst_makespan() -> None:
    result = extrapolate(
        [2.0], failure_rate=0.0, fleet_size=5, calls_per_robot=2, concurrency=3, seed=7
    )
    assert result["label"] == "extrapolation"
    assert result["total_calls"] == 10
    assert result["successful_calls"] == 10
    assert result["failed_calls"] == 0
    assert result["elapsed_s"] == 8.0
    assert result["throughput_calls_per_s"] == 1.25
    assert result["successful_throughput_calls_per_s"] == 1.25
    assert result["inputs"] == {
        "latencies_s": [2.0],
        "failure_rate": 0.0,
        "fleet_size": 5,
        "calls_per_robot": 2,
        "concurrency": 3,
        "seed": 7,
    }
    assumptions = result["assumptions"]
    assert isinstance(assumptions, list)
    assert "All calls arrive at time zero as one finite burst." in assumptions
    assert result["unvalidated_effects"] == [
        "provider rate limits",
        "queue arrival process",
        "inter-call correlation",
        "network and database contention",
        "hardware performance",
    ]


def test_failures_consume_latency_without_retries() -> None:
    result = extrapolate(
        [2.0], failure_rate=1.0, fleet_size=5, calls_per_robot=2, concurrency=3, seed=7
    )
    assert result["total_calls"] == 10
    assert result["successful_calls"] == 0
    assert result["failed_calls"] == 10
    assert result["elapsed_s"] == 8.0
    assert result["throughput_calls_per_s"] == 1.25
    assert result["successful_throughput_calls_per_s"] == 0.0


def test_sampling_is_repeatable_without_changing_global_random_state() -> None:
    initial_state = random.getstate()
    first = extrapolate(
        [0.0, 1.0, 4.0],
        failure_rate=0.35,
        fleet_size=10,
        calls_per_robot=3,
        concurrency=4,
        seed=12,
    )
    second = extrapolate(
        [0.0, 1.0, 4.0],
        failure_rate=0.35,
        fleet_size=10,
        calls_per_robot=3,
        concurrency=4,
        seed=12,
    )
    assert first == second
    assert random.getstate() == initial_state
    assert first["successful_calls"] in range(1, 30)
    assert first["failed_calls"] in range(1, 30)


def test_idle_workers_do_not_add_time() -> None:
    result = extrapolate(
        [2.0],
        failure_rate=0.0,
        fleet_size=1,
        calls_per_robot=1,
        concurrency=1_000_000,
        seed=-1,
    )
    assert result["elapsed_s"] == 2.0
    assert result["throughput_calls_per_s"] == 0.5


@pytest.mark.parametrize("latencies", [[], [-1.0], [0.0, 0.0], [math.nan], [math.inf]])
def test_reject_invalid_latency_samples(latencies: list[float]) -> None:
    with pytest.raises(ValueError, match="latencies_s"):
        extrapolate(
            latencies,
            failure_rate=0.0,
            fleet_size=1,
            calls_per_robot=1,
            concurrency=1,
            seed=0,
        )


@pytest.mark.parametrize("failure_rate", [-0.01, 1.01, math.nan, math.inf, True])
def test_reject_invalid_failure_rate(failure_rate: float) -> None:
    with pytest.raises(ValueError, match="failure_rate"):
        extrapolate(
            [1.0],
            failure_rate=failure_rate,
            fleet_size=1,
            calls_per_robot=1,
            concurrency=1,
            seed=0,
        )


@pytest.mark.parametrize("field", ["fleet_size", "calls_per_robot", "concurrency", "seed"])
@pytest.mark.parametrize("value", [True, 1.5])
def test_reject_noninteger_parameters(field: str, value: object) -> None:
    inputs = {"fleet_size": 1, "calls_per_robot": 1, "concurrency": 1, "seed": 0}
    inputs[field] = value  # type: ignore[assignment]
    with pytest.raises(ValueError, match=field):
        extrapolate([1.0], failure_rate=0.0, **inputs)


@pytest.mark.parametrize("field", ["fleet_size", "calls_per_robot", "concurrency"])
@pytest.mark.parametrize("value", [0, -1])
def test_reject_nonpositive_parameters(field: str, value: int) -> None:
    inputs = {"fleet_size": 1, "calls_per_robot": 1, "concurrency": 1, "seed": 0}
    inputs[field] = value
    with pytest.raises(ValueError, match=field):
        extrapolate([1.0], failure_rate=0.0, **inputs)


def test_reject_excessive_burst_before_allocating_workers() -> None:
    with pytest.raises(ValueError, match="1,000,000"):
        extrapolate(
            [1.0],
            failure_rate=0.0,
            fleet_size=1_000_001,
            calls_per_robot=1,
            concurrency=1_000_001,
            seed=0,
        )


def test_reject_overflowing_elapsed_time() -> None:
    with pytest.raises(ValueError, match="elapsed"):
        extrapolate(
            [1e308],
            failure_rate=0.0,
            fleet_size=2,
            calls_per_robot=1,
            concurrency=1,
            seed=0,
        )


def test_zero_sampled_burst_has_undefined_throughput() -> None:
    result = extrapolate(
        [0.0, 1.0],
        failure_rate=0.0,
        fleet_size=1,
        calls_per_robot=1,
        concurrency=1,
        seed=1,
    )
    assert result["elapsed_s"] == 0.0
    assert result["throughput_calls_per_s"] is None
    assert result["successful_throughput_calls_per_s"] is None


def test_reject_overflowing_throughput() -> None:
    with pytest.raises(ValueError, match="throughput"):
        extrapolate(
            [1e-320],
            failure_rate=0.0,
            fleet_size=1,
            calls_per_robot=1,
            concurrency=1,
            seed=0,
        )
