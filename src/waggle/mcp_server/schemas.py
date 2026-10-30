"""Strict argument schemas for the MCP tools (ADR-032).

``validate_call`` is pure. It checks the allowlist first, then rejects non-mapping arguments,
unknown and missing fields, wrong types (no coercion) and values outside the bounds. A value
out of bounds is denied, never clamped.
"""

import math
import re
from collections.abc import Mapping
from typing import Literal

from waggle.mcp_server.allowlist import is_allowed
from waggle.mcp_server.bounds import CHASSIS_BOUNDS, MapExtent

ErrorCode = Literal[
    "tool_not_allowed", "bad_type", "unknown_field", "missing_field", "bad_value", "out_of_bounds"
]

_ID = re.compile(r"[A-Za-z0-9_.-]+")
_ID_MAX = 64
_TEXT_MAX = 500
_TOKEN_MAX = 2**63 - 1
_QUANTITY_MAX = 100


class SchemaError(ValueError):
    """A call was denied. ``code`` is the audit reason code. The message has no argument values."""

    def __init__(self, code: ErrorCode, field: str = "") -> None:
        super().__init__(f"{code}: {field}" if field else code)
        self.code: ErrorCode = code
        self.field = field


def _id(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise SchemaError("bad_type", name)
    if not 1 <= len(value) <= _ID_MAX:
        raise SchemaError("out_of_bounds", name)
    if _ID.fullmatch(value) is None:
        raise SchemaError("bad_value", name)
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise SchemaError("bad_type", name)
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise SchemaError("bad_value", name)
    if not 1 <= len(value) <= _TEXT_MAX:
        raise SchemaError("out_of_bounds", name)
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise SchemaError("bad_type", name)
    return float(value)


def _integer(value: object, name: str, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError("bad_type", name)
    if not 1 <= value <= high:
        raise SchemaError("out_of_bounds", name)
    return value


def _check(kind: str, value: object, name: str, chassis: str, extent: MapExtent) -> object:
    if kind == "id":
        return _id(value, name)
    if kind == "text":
        return _text(value, name)
    if kind == "token":
        return _integer(value, name, _TOKEN_MAX)
    if kind == "quantity":
        return _integer(value, name, _QUANTITY_MAX)
    number = _number(value, name)
    if kind == "speed":
        bounds = CHASSIS_BOUNDS.get(chassis)
        if bounds is None or not 0.0 < number <= bounds.max_speed:
            raise SchemaError("out_of_bounds", name)
    else:
        low, high = (extent.x_min, extent.x_max) if kind == "x" else (extent.y_min, extent.y_max)
        if not low <= number <= high:
            raise SchemaError("out_of_bounds", name)
    return value


SCHEMAS: Mapping[str, Mapping[str, str]] = {
    "move_waypoint": {"task_id": "id", "x": "x", "y": "y", "speed": "speed"},
    "pick_package": {"task_id": "id", "package_id": "id"},
    "deliver_package": {"task_id": "id", "package_id": "id", "zone_id": "id"},
    "release_zone": {"zone_id": "id", "token": "token"},
    "get_task": {"task_id": "id"},
    "get_inventory": {"part_number": "id"},
    "reserve_part": {"part_number": "id", "quantity": "quantity", "idempotency_key": "id"},
    "dispatch_tech": {"ticket_id": "id", "zone_id": "id"},
    "open_ticket": {"machine_id": "id", "idempotency_key": "id", "summary": "text"},
    "create_purchase_order": {
        "part_number": "id",
        "quantity": "quantity",
        "idempotency_key": "id",
    },
}


def validate_call(
    tool: str, chassis: str, args: Mapping[str, object], extent: MapExtent
) -> dict[str, object]:
    """Return a validated copy of ``args`` or raise SchemaError.

    ``chassis`` must come from the authenticated identity, never from the request.
    """
    schema = SCHEMAS.get(tool)
    if schema is None or not is_allowed(chassis, tool):
        raise SchemaError("tool_not_allowed")
    if not isinstance(args, Mapping) or not all(isinstance(k, str) for k in args):
        raise SchemaError("bad_type", "arguments")
    unknown = sorted(set(args) - set(schema))
    if unknown:
        raise SchemaError("unknown_field", unknown[0])
    missing = sorted(set(schema) - set(args))
    if missing:
        raise SchemaError("missing_field", missing[0])
    return {name: _check(kind, args[name], name, chassis, extent) for name, kind in schema.items()}
