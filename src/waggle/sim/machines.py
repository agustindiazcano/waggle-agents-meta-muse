"""Machine degradation: a two-node thermal model with power-law wear (design section 2).

Ground truth for predictive maintenance lives here and nowhere else (AGENTS.md 5.4). A machine
has a hidden failure mode, an onset tick and a wear state. The predictor never sees any of it.

Model family (the predictor uses a different one, AGENTS.md 9.8):

- Two thermal nodes, housing and bearing, joined by a conductance. Heat enters the bearing node
  from a base term, a load term and a friction term that grows with the hidden damage.
- Bearing wear w in [0, 1] after onset: dw/dt = k * load^a * (w + seed)^b * (1 + noise).
  With b = 1 this accelerates, which a first-order model does not capture.
- Lubrication loss l falls from 1 to 0 after onset at a rate k * load^a_l * (1 + noise).
- Misalignment is a step in an offset at onset; damage accumulates as offset * load.

All parameters live in ``data/sim/degradation.json``. They are assumptions to calibrate, not
measurements of any real machine. Machine state is opt-in: with no machines there are no
arrays and no streams, so existing scenario hashes do not change.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from waggle.sim import engine, state, streams
from waggle.sim.params import DT

BEARING = 0
LUBE = 1
OFFSET = 2
MODES = (BEARING, LUBE, OFFSET)
STRIDE_TICKS = 40
"""Machines advance once per second (40 ticks at DT = 0.025 s)."""
STEP_SECONDS = STRIDE_TICKS * DT

Floats = NDArray[np.float64]
Ints = NDArray[np.int64]


class DegradationError(ValueError):
    """A parameter file is malformed or a parameter is not finite or out of range."""


@dataclass(frozen=True)
class ThermalParams:
    """Two-node thermal model constants (assumptions)."""

    ambient_c: float
    housing_capacity: float
    bearing_capacity: float
    bearing_housing_conductance: float
    housing_ambient_conductance: float
    heat_base_w: float
    heat_per_load_w: float


@dataclass(frozen=True)
class WearParams:
    """Onset, wear rates and failure budgets (assumptions)."""

    healthy_probability: float
    onset_min_s: float
    onset_max_s: float
    bearing_rate_min: float
    bearing_rate_max: float
    bearing_seed: float
    bearing_load_exponent: float
    bearing_state_exponent: float
    lube_rate_min: float
    lube_rate_max: float
    lube_load_exponent: float
    offset_step_min: float
    offset_step_max: float
    damage_budget: float
    rate_noise_sigma: float


@dataclass(frozen=True)
class LoadParams:
    """Load profile ranges: a bounded wave plus a term from tasks served (assumptions)."""

    base_min: float
    base_max: float
    amp_min: float
    amp_max: float
    period_min_s: float
    period_max_s: float
    task_gain: float
    task_cap: float


@dataclass(frozen=True)
class EffectsParams:
    """How hidden damage shows up in friction heat, vibration and current (assumptions)."""

    friction_heat_wear_w: float
    friction_heat_lube_w: float
    friction_heat_offset_w: float
    vibration_base: float
    vibration_per_load: float
    vibration_wear_gain: float
    vibration_lube_gain: float
    vibration_lube_knee: float
    vibration_offset_gain: float
    current_base_a: float
    current_per_load_a: float
    current_offset_gain_a: float


@dataclass(frozen=True)
class DegradationParams:
    """Every simulator-side parameter of the degradation model."""

    thermal: ThermalParams
    wear: WearParams
    load: LoadParams
    effects: EffectsParams


@dataclass(frozen=True)
class Observables:
    """Noise-free readings of the true state, per machine."""

    temperature: Floats
    vibration: Floats
    current: Floats
    load: Floats


def _f(arrays: Mapping[str, state.Array], name: str) -> Floats:
    """A float64 view of a state array (the same memory when it already is float64)."""
    return np.asarray(arrays[name], dtype=np.float64)


def _i(arrays: Mapping[str, state.Array], name: str) -> Ints:
    """An int64 view of a state array (the same memory when it already is int64)."""
    return np.asarray(arrays[name], dtype=np.int64)


def default_params_path() -> Path:
    """Path of ``data/sim/degradation.json`` in the repository."""
    return Path(__file__).resolve().parents[3] / "data" / "sim" / "degradation.json"


def load_section[S](raw: Mapping[str, Any], name: str, cls: type[S]) -> S:
    """Build one frozen parameter section from a parsed file; strict keys, finite floats."""
    section = raw.get(name)
    if not isinstance(section, dict):
        raise DegradationError(f"section {name!r} is missing")
    expected = {f.name for f in fields(cls)}  # type: ignore[arg-type]  # cls is a dataclass
    if set(section) != expected:
        missing, extra = expected - set(section), set(section) - expected
        raise DegradationError(
            f"section {name!r}: missing {sorted(missing)}, extra {sorted(extra)}"
        )
    for key, value in section.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise DegradationError(f"{name}.{key} must be a finite number")
    return cls(**{key: float(value) for key, value in section.items()})


def validate(params: DegradationParams) -> None:
    """Reject ranges that are inverted or physically meaningless. Fails closed."""
    wear, load, thermal = params.wear, params.load, params.thermal
    pairs = {
        "onset": (wear.onset_min_s, wear.onset_max_s),
        "bearing_rate": (wear.bearing_rate_min, wear.bearing_rate_max),
        "lube_rate": (wear.lube_rate_min, wear.lube_rate_max),
        "offset_step": (wear.offset_step_min, wear.offset_step_max),
        "load base": (load.base_min, load.base_max),
        "load amp": (load.amp_min, load.amp_max),
        "load period": (load.period_min_s, load.period_max_s),
    }
    for name, (low, high) in pairs.items():
        if low < 0.0 or low > high:
            raise DegradationError(f"{name} range is inverted or negative")
    if not 0.0 <= wear.healthy_probability <= 1.0:
        raise DegradationError("healthy_probability must be in [0, 1]")
    if load.base_max + load.amp_max > 1.0 or load.period_min_s <= 0.0 or load.task_cap <= 0.0:
        raise DegradationError("load profile must stay within [0, 1] and have a positive period")
    positive = (
        thermal.housing_capacity,
        thermal.bearing_capacity,
        thermal.bearing_housing_conductance,
        thermal.housing_ambient_conductance,
        wear.bearing_seed,
        wear.damage_budget,
    )
    if min(positive) <= 0.0:
        raise DegradationError("capacities, conductances, seed and budget must be positive")


def load_params(path: Path | None = None) -> DegradationParams:
    """Read and validate the degradation parameter file."""
    source = path if path is not None else default_params_path()
    raw = json.loads(source.read_text(encoding="utf-8"))
    params = DegradationParams(
        load_section(raw, "thermal", ThermalParams),
        load_section(raw, "wear", WearParams),
        load_section(raw, "load", LoadParams),
        load_section(raw, "effects", EffectsParams),
    )
    validate(params)
    return params


def _load_at(arrays: Mapping[str, state.Array], t_s: float, params: DegradationParams) -> Floats:
    """The bounded load profile at time ``t_s`` seconds."""
    p = params.load
    angle = 2.0 * math.pi * t_s / _f(arrays, "machine_load_period_s")
    wave = _f(arrays, "machine_load_base") + _f(arrays, "machine_load_amp") * np.sin(
        angle + _f(arrays, "machine_load_phase")
    )
    tasks = _f(arrays, "machine_tasks")
    load = wave + p.task_gain * np.minimum(tasks / p.task_cap, 1.0)
    return np.clip(load, 0.0, 1.0)


def _draw_machine(
    rng: np.random.Generator, params: DegradationParams
) -> tuple[int, int, float, float, float, float, float]:
    """Draw one machine's static values in a fixed order (same count whatever the values)."""
    w, ld = params.wear, params.load
    healthy = rng.random() < w.healthy_probability
    onset_s = rng.uniform(w.onset_min_s, w.onset_max_s)
    mode = int(rng.integers(0, len(MODES)))
    unit = rng.random()
    base = rng.uniform(ld.base_min, ld.base_max)
    amp = rng.uniform(ld.amp_min, ld.amp_max)
    period = rng.uniform(ld.period_min_s, ld.period_max_s)
    phase = rng.uniform(0.0, 2.0 * math.pi)
    onset_tick = -1 if healthy else round(onset_s / DT)
    return onset_tick, mode, unit, base, amp, period, phase


def initial_arrays(
    seed: int, count: int, params: DegradationParams, modes: Sequence[int] | None = None
) -> dict[str, state.Array]:
    """Machine state arrays for ``count`` machines; empty when ``count`` is 0.

    ``modes`` forces the failure mode per machine (tests and planted failures). The draw
    consumes the same random numbers either way, so forcing a mode changes nothing else.
    """
    if count < 0:
        raise ValueError("count must not be negative")
    if count == 0:
        return {}
    if modes is not None:
        if len(modes) != count:
            raise ValueError("modes must hold one entry per machine")
        if any(m not in MODES for m in modes):
            raise ValueError(f"unknown mode, expected one of {MODES}")
    rngs = streams.make_streams(seed, "degradation", count)
    drawn = [_draw_machine(rng, params) for rng in rngs]
    w = params.wear
    mode = np.array([d[1] for d in drawn] if modes is None else list(modes), dtype=np.int64)
    unit = np.array([d[2] for d in drawn])
    rate = np.where(
        mode == BEARING,
        w.bearing_rate_min + unit * (w.bearing_rate_max - w.bearing_rate_min),
        np.where(
            mode == LUBE,
            w.lube_rate_min + unit * (w.lube_rate_max - w.lube_rate_min),
            w.offset_step_min + unit * (w.offset_step_max - w.offset_step_min),
        ),
    )
    arrays: dict[str, state.Array] = {
        "machine_mode": mode,
        "machine_onset_tick": np.array([d[0] for d in drawn], dtype=np.int64),
        "machine_rate": rate.astype(np.float64),
        "machine_load_base": np.array([d[3] for d in drawn]),
        "machine_load_amp": np.array([d[4] for d in drawn]),
        "machine_load_period_s": np.array([d[5] for d in drawn]),
        "machine_load_phase": np.array([d[6] for d in drawn]),
        "machine_tasks": np.zeros(count, dtype=np.int64),
        "machine_wear": np.zeros(count),
        "machine_lube": np.ones(count),
        "machine_offset": np.zeros(count),
        "machine_damage": np.zeros(count),
        "machine_fail_tick": np.full(count, -1, dtype=np.int64),
    }
    load = _load_at(arrays, 0.0, params)
    t = params.thermal
    heat = t.heat_base_w + t.heat_per_load_w * load
    housing = t.ambient_c + heat / t.housing_ambient_conductance
    arrays["machine_load"] = load
    arrays["machine_t_housing"] = housing
    arrays["machine_t_bearing"] = housing + heat / t.bearing_housing_conductance
    return arrays


def _advance(
    arrays: dict[str, state.Array],
    tick: int,
    rngs: dict[str, np.random.Generator],
    params: DegradationParams,
) -> None:
    """One machine step of ``STEP_SECONDS``: load, wear, heat, failure check."""
    w, e, t = params.wear, params.effects, params.thermal
    count = len(arrays["machine_mode"])
    load = _load_at(arrays, tick * DT, params)
    _f(arrays, "machine_load")[:] = load
    noise = np.array([rngs[f"wear/{i}"].normal() for i in range(count)])
    factor = np.maximum(0.0, 1.0 + w.rate_noise_sigma * noise)
    mode, rate = _i(arrays, "machine_mode"), _f(arrays, "machine_rate")
    onset = _i(arrays, "machine_onset_tick")
    active = (onset >= 0) & (tick >= onset)
    wear, lube = _f(arrays, "machine_wear"), _f(arrays, "machine_lube")
    grow = (
        rate
        * factor
        * load**w.bearing_load_exponent
        * (wear + w.bearing_seed) ** (w.bearing_state_exponent)
    )
    wear[:] = np.clip(wear + np.where(active & (mode == BEARING), grow * STEP_SECONDS, 0.0), 0, 1)
    drain = rate * factor * load**w.lube_load_exponent
    lube[:] = np.clip(lube - np.where(active & (mode == LUBE), drain * STEP_SECONDS, 0.0), 0, 1)
    offset = np.where(active & (mode == OFFSET), rate, 0.0)
    _f(arrays, "machine_offset")[:] = offset
    damage = _f(arrays, "machine_damage")
    damage += offset * load * STEP_SECONDS
    heat = (
        t.heat_base_w
        + t.heat_per_load_w * load
        + e.friction_heat_wear_w * wear
        + e.friction_heat_lube_w * (1.0 - lube)
        + e.friction_heat_offset_w * offset * load
    )
    housing, bearing = _f(arrays, "machine_t_housing"), _f(arrays, "machine_t_bearing")
    flow = t.bearing_housing_conductance * (bearing - housing)
    outflow = t.housing_ambient_conductance * (housing - t.ambient_c)
    bearing[:] = bearing + STEP_SECONDS * (heat - flow) / t.bearing_capacity
    housing[:] = housing + STEP_SECONDS * (flow - outflow) / t.housing_capacity
    failed = ((mode == BEARING) & (wear >= 1.0)) | ((mode == LUBE) & (lube <= 0.0))
    failed |= (mode == OFFSET) & (damage >= w.damage_budget)
    fail_tick = _i(arrays, "machine_fail_tick")
    fail_tick[failed & (fail_tick < 0)] = tick


def make_system(params: DegradationParams) -> engine.System:
    """The engine system that advances every machine once per ``STRIDE_TICKS``."""

    def system(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        if "machine_mode" in sim.arrays and sim.tick % STRIDE_TICKS == 0:
            _advance(sim.arrays, sim.tick, rngs, params)

    return system


def stream_counts(count: int) -> dict[str, int]:
    """Streams the machine systems need; empty when there are no machines."""
    return {"wear": count} if count > 0 else {}


def observables(arrays: Mapping[str, state.Array], params: DegradationParams) -> Observables:
    """Noise-free readings from the true state. Telemetry adds noise on top of this."""
    e = params.effects
    load = np.asarray(arrays["machine_load"], dtype=np.float64)
    wear = np.asarray(arrays["machine_wear"], dtype=np.float64)
    lost = 1.0 - np.asarray(arrays["machine_lube"], dtype=np.float64)
    offset = np.asarray(arrays["machine_offset"], dtype=np.float64)
    vibration = (
        e.vibration_base
        + e.vibration_per_load * load
        + e.vibration_wear_gain * wear**2
        + e.vibration_lube_gain * np.maximum(0.0, lost - e.vibration_lube_knee)
        + e.vibration_offset_gain * offset
    )
    current = e.current_base_a + e.current_per_load_a * load + e.current_offset_gain_a * offset
    temperature = np.asarray(arrays["machine_t_bearing"], dtype=np.float64).copy()
    return Observables(temperature, vibration, current, load.copy())


def build_engine(
    seed: int, count: int, params: DegradationParams, modes: Sequence[int] | None = None
) -> engine.Engine:
    """An engine that holds only ``count`` machines. With 0 machines it has no state."""
    arrays = initial_arrays(seed, count, params, modes)
    systems = [make_system(params)] if count > 0 else []
    return engine.Engine(seed, arrays, systems, stream_counts(count))
