"""waggle.control.params: declared assumptions of the fast layer and their validation."""

import dataclasses
import math

import pytest

from waggle.control.params import DEFAULT_CONTROL_PARAMS, ControlParams, ControlParamsError


def test_defaults_are_the_adr_values() -> None:
    cp = DEFAULT_CONTROL_PARAMS
    assert cp.human_speed_bound == 1.6
    assert cp.interp_k == 1.5
    assert cp.human_margin > 0
    assert cp.structure_margin > 0
    assert cp.lateral_margin > 0


def test_params_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_CONTROL_PARAMS.interp_k = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    ["human_speed_bound", "human_margin", "structure_margin", "lateral_margin"],
)
@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
def test_a_non_positive_or_non_finite_value_is_rejected(field: str, bad: float) -> None:
    with pytest.raises(ControlParamsError, match=field):
        dataclasses.replace(DEFAULT_CONTROL_PARAMS, **{field: bad})


@pytest.mark.parametrize("bad", [0.99, 0.0, math.nan, math.inf])
def test_interp_k_must_be_at_least_one_and_finite(bad: float) -> None:
    with pytest.raises(ControlParamsError, match="interp_k"):
        ControlParams(interp_k=bad)


def test_perception_defaults_are_the_adr_026_values() -> None:
    from waggle.control.params import DEFAULT_PERCEPTION_PARAMS as pp

    assert pp.max_scan_age_ticks == 8
    assert pp.max_nan_fraction == 0.2
    assert pp.human_max_extent == 1.0
    assert pp.human_speed_bound == DEFAULT_CONTROL_PARAMS.human_speed_bound


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("max_scan_age_ticks", 0),
        ("nan_window", 0),
        ("max_coast_ticks", 0),
        ("ring_points", 3),
        ("gap_base", 0.0),
        ("gap_per_meter", math.nan),
        ("human_max_extent", -1.0),
        ("assoc_gate_base", math.inf),
        ("beacon_sigma", 0.0),
        ("max_nan_fraction", 1.0),
        ("max_nan_fraction", -0.1),
        ("velocity_alpha", 0.0),
        ("velocity_alpha", 1.5),
    ],
)
def test_a_bad_perception_value_is_rejected(field: str, bad: float) -> None:
    from waggle.control.params import PerceptionParams

    with pytest.raises(ControlParamsError, match=field):
        PerceptionParams(**{field: bad})  # type: ignore[arg-type]
