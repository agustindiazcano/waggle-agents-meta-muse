"""waggle.control.types: the closed reason set and the frozen request, limit and output types."""

import dataclasses

import pytest

from waggle.control.types import ControlOutput, ControlRequest, Limit, Reason


def test_reason_is_the_closed_set_of_adr_027() -> None:
    assert {reason.name for reason in Reason} == {
        "REQUEST",
        "CLASS_MAX",
        "ENVELOPE",
        "OCCLUSION",
        "CPA",
        "GEOFENCE",
        "WATCHDOG",
        "SCAN_INVALID",
        "INPUT_MISSING",
        "ESTOP",
    }


def test_reason_values_are_stable_strings_for_the_run_log() -> None:
    assert Reason.ENVELOPE.value == "envelope"
    assert Reason.SCAN_INVALID.value == "scan_invalid"


@pytest.mark.parametrize(
    "instance",
    [
        ControlRequest(speed=1.0, turn=0.1),
        Limit(speed_cap=1.0, reason=Reason.ENVELOPE),
        ControlOutput(speed=1.0, turn=0.1, reason=Reason.REQUEST, limits_hit=()),
    ],
)
def test_types_are_frozen(instance: object) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.speed = 2.0  # type: ignore[attr-defined]
