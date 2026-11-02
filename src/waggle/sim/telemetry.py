"""Machine telemetry with Gaussian noise per channel and a per-machine bias (design T2).

Channels: bearing temperature, vibration RMS, motor current and the commanded load. A sample
is numbers and a tick only: it carries no fault state, no onset and no wear value. Drift,
dropouts and stuck-at faults (T3) are a later branch. Noise sigmas and bias sigmas are
assumptions to calibrate, in ``data/sim/degradation.json`` (simulator side).
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from waggle.sim import engine, machines, state, streams


@dataclass(frozen=True)
class NoiseParams:
    """Per-channel noise and per-machine bias scales (assumptions)."""

    temperature_sigma_c: float
    vibration_sigma: float
    current_sigma_a: float
    load_sigma: float
    temperature_bias_sigma_c: float
    vibration_bias_sigma: float
    current_bias_sigma_a: float


@dataclass(frozen=True)
class TelemetrySample:
    """One machine's reading at one tick. Numbers only, by design."""

    machine_id: int
    tick: int
    temperature: float
    vibration: float
    current: float
    load: float


@dataclass
class TelemetryEngine:
    """An engine that holds machines, with the parameters needed to read their telemetry."""

    engine: engine.Engine
    params: machines.DegradationParams
    noise: NoiseParams


def load_noise(path: Path | None = None) -> NoiseParams:
    """Read the telemetry section of the parameter file; every scale must be finite and >= 0."""
    source = path if path is not None else machines.default_params_path()
    raw = json.loads(source.read_text(encoding="utf-8"))
    noise = machines.load_section(raw, "telemetry", NoiseParams)
    for key, value in vars(noise).items():
        if value < 0.0:
            raise machines.DegradationError(f"telemetry.{key} must not be negative")
    return noise


def bias_array(seed: int, count: int, noise: NoiseParams) -> machines.Floats:
    """Per-machine constant bias for (temperature, vibration, current), drawn once."""
    scales = np.array(
        [noise.temperature_bias_sigma_c, noise.vibration_bias_sigma, noise.current_bias_sigma_a]
    )
    rngs = streams.make_streams(seed, "sensorbias", count)
    rows = [rng.normal(0.0, 1.0, size=3) * scales for rng in rngs]
    return np.array(rows, dtype=np.float64).reshape(count, 3)


def build_engine(
    seed: int,
    count: int,
    params: machines.DegradationParams,
    noise: NoiseParams,
    modes: list[int] | None = None,
) -> TelemetryEngine:
    """Machines plus the streams and the bias that telemetry needs. 0 machines: no state."""
    arrays = machines.initial_arrays(seed, count, params, modes)
    counts = machines.stream_counts(count)
    systems = []
    if count > 0:
        arrays["machine_bias"] = bias_array(seed, count, noise)
        counts["telemetry"] = count
        systems.append(machines.make_system(params))
    return TelemetryEngine(engine.Engine(seed, arrays, systems, counts), params, noise)


def read(sim: TelemetryEngine) -> list[TelemetrySample]:
    """Noisy samples for every machine at the current tick. Raises if the truth is not finite.

    Each call draws from the per-machine telemetry streams, so the stream state (and the
    engine hash) moves, and a fork reads exactly what the original would.
    """
    arrays: dict[str, state.Array] = sim.engine.state.arrays
    if "machine_mode" not in arrays:
        return []
    truth = machines.observables(arrays, sim.params)
    bias = np.asarray(arrays["machine_bias"], dtype=np.float64)
    n, noise = len(truth.temperature), sim.noise
    sigmas = np.array(
        [noise.temperature_sigma_c, noise.vibration_sigma, noise.current_sigma_a, noise.load_sigma]
    )
    samples: list[TelemetrySample] = []
    for i in range(n):
        draw = sim.engine.rngs[f"telemetry/{i}"].normal(0.0, 1.0, size=4) * sigmas
        values = (
            float(truth.temperature[i] + bias[i, 0] + draw[0]),
            float(truth.vibration[i] + bias[i, 1] + draw[1]),
            float(truth.current[i] + bias[i, 2] + draw[2]),
            float(truth.load[i] + draw[3]),
        )
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"machine {i}: telemetry must be finite, the truth is not")
        samples.append(TelemetrySample(i, sim.engine.state.tick, *values))
    return samples
