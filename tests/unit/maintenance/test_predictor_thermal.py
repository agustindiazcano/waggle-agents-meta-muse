"""waggle.maintenance.predictor.thermal: output-error fit of a one-node model."""

import math

import numpy as np
import pytest

from waggle.maintenance.predictor.thermal import fit_one_node


def _data(seed: int, alpha: float = 0.97, noise: float = 0.35) -> tuple[list[float], list[float]]:
    rng = np.random.default_rng(seed)
    temp, temps, loads = 38.0, [], []
    for k in range(200):
        load = 0.5 + 0.2 * math.sin(k / 20.0)
        temp = alpha * temp + (1 - alpha) * (25.0 + 40.0 * load)
        temps.append(temp + float(rng.normal(0, noise)))
        loads.append(load)
    return temps, loads


def test_alpha_is_recovered_from_noisy_readings() -> None:
    for seed in range(5):
        temps, loads = _data(seed)
        assert fit_one_node(temps, loads, 0.82, 0.995).alpha == pytest.approx(0.97, abs=0.02)


def test_gains_describe_the_equilibrium() -> None:
    temps, loads = _data(1, noise=0.05)
    fit = fit_one_node(temps, loads, 0.82, 0.995)
    gain = fit.gamma / (1 - fit.alpha)
    assert gain == pytest.approx(40.0, rel=0.15)


def test_too_few_samples_are_rejected() -> None:
    with pytest.raises(ValueError, match="three"):
        fit_one_node([1.0, 2.0], [0.1, 0.2], 0.82, 0.995)
    with pytest.raises(ValueError, match="paired"):
        fit_one_node([1.0, 2.0, 3.0, 4.0], [0.1, 0.2], 0.82, 0.995)


def test_non_finite_readings_do_not_produce_a_fit() -> None:
    temps, loads = _data(2)
    temps[10] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        fit_one_node(temps, loads, 0.82, 0.995)
