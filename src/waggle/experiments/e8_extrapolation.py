"""Deterministic empirical burst extrapolation, not real fleet validation."""

import heapq
import math
import random
from collections.abc import Sequence

_MAX_CALLS = 1_000_000


def extrapolate(
    latencies_s: Sequence[float],
    *,
    failure_rate: float,
    fleet_size: int,
    calls_per_robot: int,
    concurrency: int,
    seed: int,
) -> dict[str, object]:
    """Sample independent calls in a finite burst using a local seeded generator."""
    samples = tuple(latencies_s)
    if (
        not samples
        or any(
            isinstance(value, bool) or not math.isfinite(value) or value < 0 for value in samples
        )
        or not any(value > 0 for value in samples)
    ):
        raise ValueError("latencies_s must be finite, nonnegative and include a positive sample")
    if (
        isinstance(failure_rate, bool)
        or not math.isfinite(failure_rate)
        or not 0 <= failure_rate <= 1
    ):
        raise ValueError("failure_rate must be finite and within [0, 1]")
    for name, value in (
        ("fleet_size", fleet_size),
        ("calls_per_robot", calls_per_robot),
        ("concurrency", concurrency),
        ("seed", seed),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if name != "seed" and value <= 0:
            raise ValueError(f"{name} must be positive")
    total_calls = fleet_size * calls_per_robot
    if total_calls > _MAX_CALLS:
        raise ValueError("finite burst must not exceed 1,000,000 calls")

    generator = random.Random(seed)
    workers = [0.0] * min(concurrency, total_calls)
    failures = 0
    for _ in range(total_calls):
        latency = generator.choice(samples)
        failures += generator.random() < failure_rate
        available_at = workers[0] + latency
        if not math.isfinite(available_at):
            raise ValueError("elapsed time overflowed the finite numerical range")
        heapq.heapreplace(workers, available_at)
    elapsed = max(workers)
    successful_calls = total_calls - failures
    throughput = total_calls / elapsed if elapsed > 0 else None
    successful_throughput = successful_calls / elapsed if elapsed > 0 else None
    if throughput is not None and not math.isfinite(throughput):
        raise ValueError("elapsed time is too small for finite throughput")
    return {
        "label": "extrapolation",
        "inputs": {
            "latencies_s": list(samples),
            "failure_rate": failure_rate,
            "fleet_size": fleet_size,
            "calls_per_robot": calls_per_robot,
            "concurrency": concurrency,
            "seed": seed,
        },
        "total_calls": total_calls,
        "successful_calls": successful_calls,
        "failed_calls": failures,
        "elapsed_s": elapsed,
        "throughput_calls_per_s": throughput,
        "successful_throughput_calls_per_s": successful_throughput,
        "assumptions": [
            "All calls arrive at time zero as one finite burst.",
            "Each free worker immediately takes the next call at fixed concurrency.",
            "Latencies are independent uniform draws with replacement from the supplied samples.",
            "Failures are independent Bernoulli draws, independent of latency.",
            "Failed calls consume sampled latency; no call is retried.",
            "Calls have no per-robot ordering or dependency constraints.",
            "Throughput is null when the sampled burst has zero elapsed time.",
            "This is an extrapolation and does not validate real fleet performance.",
        ],
        "unvalidated_effects": [
            "provider rate limits",
            "queue arrival process",
            "inter-call correlation",
            "network and database contention",
            "hardware performance",
        ],
    }
