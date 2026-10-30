"""Proportions and latency summaries for E1."""

import math
from collections.abc import Sequence

import numpy as np

_Z95 = 1.959963984540054


def wilson(successes: int, total: int, z: float = _Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion. With no trials it is (0, 1)."""
    if total <= 0:
        return 0.0, 1.0
    if not 0 <= successes <= total:
        raise ValueError("successes must be between 0 and total")
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    low = 0.0 if successes == 0 else max(centre - half, 0.0)
    high = 1.0 if successes == total else min(centre + half, 1.0)
    return low, high


def latency_summary(samples_us: Sequence[float]) -> dict[str, float]:
    """Median, 99th percentile and maximum of latency samples in microseconds."""
    if len(samples_us) == 0:
        return {"n": 0, "median_us": 0.0, "p99_us": 0.0, "max_us": 0.0}
    values = np.asarray(samples_us, dtype=np.float64)
    return {
        "n": int(values.size),
        "median_us": float(np.median(values)),
        "p99_us": float(np.percentile(values, 99)),
        "max_us": float(values.max()),
    }
