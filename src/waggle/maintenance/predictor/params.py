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
    "baseline": ("warmup_samples", "sigma_floor", "alpha_min", "alpha_max"),
    "cusum": ("slack", "threshold"),
    "estimate": ("intercept_memory", "level_memory", "temperature_limit_c"),
}
MIN_WARMUP = 30


@dataclass(frozen=True)
class PredictorParams:
    """Every predictor parameter, flat."""

    warmup_samples: int
    sigma_floor: float
    alpha_min: float
    alpha_max: float
    slack: float
    threshold: float
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
    if not 0.0 < p.alpha_min < p.alpha_max < 1.0:
        raise PredictorError("alpha_min and alpha_max must satisfy 0 < alpha_min < alpha_max < 1")
    if p.sigma_floor <= 0.0 or p.threshold <= 0.0 or p.slack < 0.0:
        raise PredictorError("sigma_floor and threshold must be positive, slack not negative")
    for name in ("intercept_memory", "level_memory"):
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
    flat["warmup_samples"] = int(flat["warmup_samples"])
    params = PredictorParams(**flat)  # type: ignore[arg-type]  # warmup_samples was cast to int
    validate(params)
    return params
