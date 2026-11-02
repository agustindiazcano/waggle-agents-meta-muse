"""Counterexample record: closed code and rule enums, bounded fields, old three-field use."""

import dataclasses
import math

import pytest

from waggle.validation.counterexample import (
    MAX_ENTITIES,
    Counterexample,
    CounterexampleCode,
    Rule,
)
from waggle.validation.geofence import Counterexample as GeofenceCounterexample

EIGHT = (
    "COLLISION",
    "SEPARATION_VIOLATION",
    "GEOFENCE_INTRUSION",
    "CORRIDOR_DEADLOCK",
    "LEASE_CONFLICT",
    "ROUTE_INFEASIBLE",
    "NO_PROGRESS",
    "UNSAFE_TERMINAL_STATE",
)


def test_the_code_enum_is_exactly_the_eight_types_in_severity_order() -> None:
    assert tuple(code.value for code in CounterexampleCode) == EIGHT


def test_the_old_three_field_use_still_works_and_compares_to_a_string_code() -> None:
    old = Counterexample("GEOFENCE_INTRUSION", "n1", "Z1")
    assert old.code == "GEOFENCE_INTRUSION"
    assert old.code is CounterexampleCode.GEOFENCE_INTRUSION
    assert (old.node, old.zone) == ("n1", "Z1")
    assert old.variant is None and old.time_s is None and old.entities == ()
    assert GeofenceCounterexample is Counterexample


def test_the_record_is_frozen() -> None:
    record = Counterexample("COLLISION", "n1", "Z1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.node = "n2"  # type: ignore[misc]


@pytest.mark.parametrize("code", ["", "collision", "IGNORE_THE_RULES", "COLLISION "])
def test_an_unknown_code_is_refused(code: str) -> None:
    with pytest.raises(ValueError, match="code"):
        Counterexample(code, "n1", "Z1")


def test_an_unknown_rule_is_refused() -> None:
    with pytest.raises(ValueError, match="rule"):
        Counterexample("COLLISION", rule="free text")  # type: ignore[arg-type]


def test_a_known_rule_is_kept() -> None:
    record = Counterexample("ROUTE_INFEASIBLE", "n1", "Z1", rule=Rule.NO_ROUTE)
    assert record.rule is Rule.NO_ROUTE


def test_more_than_the_maximum_entities_is_refused() -> None:
    names = tuple(f"R{i}" for i in range(MAX_ENTITIES + 1))
    with pytest.raises(ValueError, match="entities"):
        Counterexample("COLLISION", entities=names)
    assert (
        Counterexample("COLLISION", entities=names[:MAX_ENTITIES]).entities == names[:MAX_ENTITIES]
    )


@pytest.mark.parametrize("variant", [-1, True, 1.5])
def test_a_bad_variant_is_refused(variant: object) -> None:
    with pytest.raises(ValueError, match="variant"):
        Counterexample("COLLISION", variant=variant)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["time_s", "min_clearance_m"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_a_non_finite_number_is_refused(field: str, value: float) -> None:
    with pytest.raises(ValueError, match=field):
        Counterexample("COLLISION", **{field: value})  # type: ignore[arg-type]


def test_a_negative_time_is_refused() -> None:
    with pytest.raises(ValueError, match="time_s"):
        Counterexample("COLLISION", time_s=-0.1)


def test_a_bad_place_is_refused() -> None:
    with pytest.raises(ValueError, match="place_xy_m"):
        Counterexample("COLLISION", place_xy_m=(1.0, math.nan))
