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
