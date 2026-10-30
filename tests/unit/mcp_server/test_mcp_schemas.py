"""Allowlist, bounds and strict schemas of the MCP boundary (ADR-032, pure, no I/O)."""

import math
from collections.abc import Mapping

import pytest

from waggle.mcp_server.allowlist import ALLOWLIST, TOOLS, is_allowed
from waggle.mcp_server.bounds import CHASSIS_BOUNDS, MapExtent
from waggle.mcp_server.schemas import SchemaError, validate_call
from waggle.sim.params import ROBOT_PARAMS

EXTENT = MapExtent(0.0, 0.0, 40.0, 24.0)
MOTION = ("carrier", "forklift", "parts_runner", "tech_repair")


def ok(tool: str, chassis: str, args: Mapping[str, object]) -> Mapping[str, object]:
    return validate_call(tool, chassis, args, EXTENT)


def reason(tool: str, chassis: str, args: object) -> str:
    with pytest.raises(SchemaError) as err:
        validate_call(tool, chassis, args, EXTENT)  # type: ignore[arg-type]
    return err.value.code


def test_every_chassis_pair_matches_the_table() -> None:
    for chassis in (*MOTION, "maintenance", "unknown"):
        for tool in TOOLS:
            expected = tool in ALLOWLIST.get(chassis, frozenset())
            assert is_allowed(chassis, tool) is expected


def test_unknown_chassis_or_tool_is_denied() -> None:
    assert not is_allowed("ghost", "move_waypoint")
    assert not is_allowed("carrier", "format_disk")
    assert not is_allowed("", "")


def test_motion_chassis_never_get_maintenance_only_tools() -> None:
    for chassis in MOTION:
        for tool in ("reserve_part", "dispatch_tech", "create_purchase_order"):
            assert not is_allowed(chassis, tool)
    for tool in ("move_waypoint", "pick_package", "deliver_package", "release_zone"):
        assert not is_allowed("maintenance", tool)


def test_carrier_cannot_call_a_tool_outside_its_role() -> None:
    assert not is_allowed("carrier", "open_ticket")
    assert not is_allowed("tech_repair", "pick_package")


def test_chassis_bounds_match_the_simulator_parameters() -> None:
    assert set(CHASSIS_BOUNDS) == {kind.value for kind in ROBOT_PARAMS}
    for kind, params in ROBOT_PARAMS.items():
        assert CHASSIS_BOUNDS[kind.value].max_speed == params.max_speed


GOOD_MOVE = {"task_id": "t-1", "x": 10.0, "y": 5.0, "speed": 1.0}


def test_valid_call_is_returned_as_a_copy() -> None:
    args = dict(GOOD_MOVE)
    out = ok("move_waypoint", "carrier", args)
    assert out == GOOD_MOVE
    args["x"] = 99.0
    assert out["x"] == 10.0


def test_extra_and_missing_fields_are_rejected() -> None:
    assert reason("move_waypoint", "carrier", {**GOOD_MOVE, "robot_id": "r9"}) == "unknown_field"
    assert reason("move_waypoint", "carrier", {"task_id": "t", "x": 1.0}) == "missing_field"


def test_identity_fields_are_never_accepted_as_arguments() -> None:
    for key in ("chassis", "robot_id", "role", "token"):
        assert reason("get_task", "carrier", {"task_id": "t-1", key: "x"}) == "unknown_field"


def test_speed_at_the_chassis_limit_passes_and_above_is_denied() -> None:
    limit = CHASSIS_BOUNDS["forklift"].max_speed
    assert ok("move_waypoint", "forklift", {**GOOD_MOVE, "speed": limit})["speed"] == limit
    over = math.nextafter(limit, math.inf)
    assert reason("move_waypoint", "forklift", {**GOOD_MOVE, "speed": over}) == "out_of_bounds"


def test_speed_is_denied_not_clamped() -> None:
    assert reason("move_waypoint", "forklift", {**GOOD_MOVE, "speed": 2.0}) == "out_of_bounds"
    assert ok("move_waypoint", "carrier", {**GOOD_MOVE, "speed": 2.0})["speed"] == 2.0


@pytest.mark.parametrize("speed", [0.0, -1.0])
def test_nonpositive_speed_is_denied(speed: float) -> None:
    assert reason("move_waypoint", "carrier", {**GOOD_MOVE, "speed": speed}) == "out_of_bounds"


def test_waypoint_must_lie_inside_the_map() -> None:
    assert ok("move_waypoint", "carrier", {**GOOD_MOVE, "x": 40.0, "y": 24.0})
    assert ok("move_waypoint", "carrier", {**GOOD_MOVE, "x": 0.0, "y": 0.0})
    for key, value in (("x", 40.001), ("x", -0.001), ("y", 24.001), ("y", -0.001)):
        assert reason("move_waypoint", "carrier", {**GOOD_MOVE, key: value}) == "out_of_bounds"


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_denied(bad: float) -> None:
    assert reason("move_waypoint", "carrier", {**GOOD_MOVE, "x": bad}) == "bad_type"


def test_types_are_not_coerced() -> None:
    assert reason("move_waypoint", "carrier", {**GOOD_MOVE, "x": "10"}) == "bad_type"
    assert reason("move_waypoint", "carrier", {**GOOD_MOVE, "x": True}) == "bad_type"
    assert reason("move_waypoint", "carrier", {**GOOD_MOVE, "task_id": 7}) == "bad_type"
    assert reason("release_zone", "carrier", {"zone_id": "z1", "token": 1.0}) == "bad_type"
    assert reason("release_zone", "carrier", {"zone_id": "z1", "token": True}) == "bad_type"


def test_int_arguments_are_accepted_as_numbers_for_float_fields() -> None:
    assert ok("move_waypoint", "carrier", {**GOOD_MOVE, "x": 3})["x"] == 3


@pytest.mark.parametrize("bad", ["", "a b", "a;b", "../x", "x" * 65, "t\n1", "é"])
def test_ids_must_match_the_safe_pattern(bad: str) -> None:
    assert reason("get_task", "carrier", {"task_id": bad}) in {"bad_value", "out_of_bounds"}


def test_id_length_boundary() -> None:
    assert ok("get_task", "carrier", {"task_id": "a" * 64})
    assert reason("get_task", "carrier", {"task_id": "a" * 65}) == "out_of_bounds"


def test_fencing_token_is_a_positive_integer_claim() -> None:
    assert ok("release_zone", "carrier", {"zone_id": "z1", "token": 1})
    assert reason("release_zone", "carrier", {"zone_id": "z1", "token": 0}) == "out_of_bounds"
    assert reason("release_zone", "carrier", {"zone_id": "z1", "token": -3}) == "out_of_bounds"


def test_quantity_bounds() -> None:
    base = {"part_number": "P-100", "idempotency_key": "k1"}
    assert ok("reserve_part", "maintenance", {**base, "quantity": 1})
    assert ok("reserve_part", "maintenance", {**base, "quantity": 100})
    assert reason("reserve_part", "maintenance", {**base, "quantity": 0}) == "out_of_bounds"
    assert reason("reserve_part", "maintenance", {**base, "quantity": 101}) == "out_of_bounds"


def test_free_text_is_bounded_and_free_of_control_characters() -> None:
    base = {"machine_id": "m1", "idempotency_key": "k1"}
    assert ok("open_ticket", "tech_repair", {**base, "summary": "x" * 500})
    assert reason("open_ticket", "tech_repair", {**base, "summary": "x" * 501}) == "out_of_bounds"
    assert reason("open_ticket", "tech_repair", {**base, "summary": "a\x00b"}) == "bad_value"
    assert reason("open_ticket", "tech_repair", {**base, "summary": ""}) == "out_of_bounds"


def test_tool_not_allowed_for_the_chassis_is_denied_before_schema() -> None:
    assert reason("reserve_part", "carrier", {}) == "tool_not_allowed"
    assert reason("format_disk", "carrier", {}) == "tool_not_allowed"
    assert reason("move_waypoint", "ghost", GOOD_MOVE) == "tool_not_allowed"


def test_non_mapping_arguments_are_denied() -> None:
    bad_values: tuple[object, ...] = (None, [], "x", 3)
    for bad in bad_values:
        assert reason("get_task", "carrier", bad) == "bad_type"


def test_non_string_keys_are_denied() -> None:
    assert reason("get_task", "carrier", {1: "x"}) == "bad_type"


def test_degenerate_map_extent_is_rejected() -> None:
    with pytest.raises(ValueError):
        MapExtent(5.0, 0.0, 5.0, 10.0)
    with pytest.raises(ValueError):
        MapExtent(0.0, 0.0, math.nan, 1.0)


def test_summary_must_be_a_string() -> None:
    args = {"machine_id": "m1", "idempotency_key": "k1", "summary": 5}
    assert reason("open_ticket", "tech_repair", args) == "bad_type"
