"""Output-error fit of a one-node first-order thermal model.

Model: T[k+1] = alpha T[k] + beta + gamma load[k]. Fitting by regressing T[k+1] on the noisy
T[k] biases alpha toward zero when the readings are noisy and the temperature moves slowly,
so alpha is found by a grid search instead. For each alpha the free-run response of the model
is linear in a start level and two gains, which least squares solves; the alpha with the
smallest squared output error wins. The coefficients and the grid are the predictor's own.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

GRID_POINTS = 40


@dataclass(frozen=True)
class OneNode:
    """A fitted one-node model: coefficients, the modeled level at the last sample, and sigma."""

    alpha: float
    beta: float
    gamma: float
    level: float
    sigma: float


def _filtered(alpha: float, drive: np.ndarray) -> np.ndarray:
    """y[0] = 0, y[k+1] = alpha y[k] + (1 - alpha) drive[k]."""
    out = np.zeros_like(drive)
    for k in range(1, len(drive)):
        out[k] = alpha * out[k - 1] + (1.0 - alpha) * drive[k - 1]
    return out


def fit_one_node(
    temps: Sequence[float], loads: Sequence[float], alpha_min: float, alpha_max: float
) -> OneNode:
    """Fit the model to a contiguous run of readings. Raises ValueError if nothing finite fits."""
    t, load = np.asarray(temps, dtype=np.float64), np.asarray(loads, dtype=np.float64)
    if len(t) != len(load) or len(t) < 3:
        raise ValueError("need at least three paired temperature and load samples")
    steps = np.arange(len(t))
    best: tuple[float, float, np.ndarray, np.ndarray] | None = None
    for alpha_value in np.linspace(alpha_min, alpha_max, GRID_POINTS):
        alpha = float(alpha_value)
        design = np.column_stack(
            [alpha**steps, _filtered(alpha, np.ones_like(t)), _filtered(alpha, load)]
        )
        coef, *_ = np.linalg.lstsq(design, t, rcond=None)
        fit = design @ coef
        sse = float(np.sum((t - fit) ** 2))
        if np.isfinite(sse) and (best is None or sse < best[0]):
            best = (sse, alpha, coef, fit)
    if best is None:
        raise ValueError("no finite one-node fit")
    _, alpha, coef, fit = best
    return OneNode(
        alpha,
        float((1.0 - alpha) * coef[1]),
        float((1.0 - alpha) * coef[2]),
        float(fit[-1]),
        float(np.std(t - fit)),
    )
