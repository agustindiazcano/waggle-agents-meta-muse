"""waggle.maintenance.predictor: telemetry in, flag and time-to-limit estimate out.

Imports nothing from ``waggle.sim`` (AGENTS.md 9.8). The input type has no fault-state field.
"""

from waggle.maintenance.predictor.core import Predictor
from waggle.maintenance.predictor.params import PredictorParams, default_params_path, load_params
from waggle.maintenance.predictor.types import Assessment, PredictorError, Reading

__all__ = [
    "Assessment",
    "Predictor",
    "PredictorError",
    "PredictorParams",
    "Reading",
    "default_params_path",
    "load_params",
]
