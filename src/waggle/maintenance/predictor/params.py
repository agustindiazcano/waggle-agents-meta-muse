"""Predictor parameters, read from ``data/maintenance/predictor.json``.

Predictor side only. No key or value here is shared with ``data/sim/degradation.json``, and a
test checks that. All values are assumptions to calibrate on development seeds or on the
synthetic failure log, never on the simulator's own parameters. They are not measurements.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from waggle.maintenance.predictor.types import PredictorError

_SECTIONS = {
    "baseline": (
        "temperature_margin_c",
        "warmup_samples",
        "max_warmup_samples",
        "min_load_span",
        "sigma_floor",
        "alpha_min",
        "alpha_max",
    ),
    "cusum": ("slack", "threshold", "observer_gain"),
    "estimate": ("intercept_memory", "level_memory", "temperature_limit_c"),
}
MIN_WARMUP = 30


@dataclass(frozen=True)
class PredictorParams:
    """Every predictor parameter, flat."""

    warmup_samples: int
    max_warmup_samples: int
    temperature_margin_c: float
    min_load_span: float
    sigma_floor: float
    alpha_min: float
    alpha_max: float
    slack: float
    threshold: float
    observer_gain: float
    intercept_memory: float
    level_memory: float
    temperature_limit_c: float


def default_params_path() -> Path:
    """Path of ``data/maintenance/predictor.json`` in the repository."""
    return Path(__file__).resolve().parents[4] / "data" / "maintenance" / "predictor.json"


def validate(p: PredictorParams) -> None:
    """Reject values that make the model meaningless. Fails closed."""
    if p.warmup_samples < MIN_WARMUP:
        raise PredictorError(f"warmup_samples must be at least {MIN_WARMUP}")
    if p.max_warmup_samples < p.warmup_samples:
        raise PredictorError("max_warmup_samples must not be below warmup_samples")
    if not 0.0 < p.min_load_span < 1.0:
        raise PredictorError("min_load_span must be strictly between 0 and 1")
    if not 0.0 < p.alpha_min < p.alpha_max < 1.0:
        raise PredictorError("alpha_min and alpha_max must satisfy 0 < alpha_min < alpha_max < 1")
    if p.temperature_margin_c < 0.0:
        raise PredictorError("temperature_margin_c must not be negative")
    if p.sigma_floor <= 0.0 or p.threshold <= 0.0 or p.slack < 0.0:
        raise PredictorError("sigma_floor and threshold must be positive, slack not negative")
    for name in ("intercept_memory", "level_memory", "observer_gain"):
        if not 0.0 < getattr(p, name) < 1.0:
            raise PredictorError(f"{name} must be strictly between 0 and 1")


def load_params(path: Path | None = None) -> PredictorParams:
    """Read and validate the predictor parameter file."""
    raw = json.loads((path or default_params_path()).read_text(encoding="utf-8"))
    flat: dict[str, float] = {}
    for section, keys in _SECTIONS.items():
        body = raw.get(section)
        if not isinstance(body, dict) or set(body) != set(keys):
            got = sorted(body) if isinstance(body, dict) else body
            raise PredictorError(f"section {section!r} must hold exactly {list(keys)}, got {got}")
        for key, value in body.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise PredictorError(f"{section}.{key} must be a number")
            if not math.isfinite(value):
                raise PredictorError(f"{section}.{key} must be finite")
            flat[key] = float(value)
    for name in ("warmup_samples", "max_warmup_samples"):
        flat[name] = int(flat[name])
    params = PredictorParams(**flat)  # type: ignore[arg-type]  # warmup_samples was cast to int
    validate(params)
    return params
