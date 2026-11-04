"""Static chassis to tool allowlist (ADR-032). Code only: no prompt, document or database
value can widen it."""

from collections.abc import Mapping

_MOTION = frozenset(
    {"move_waypoint", "pick_package", "deliver_package", "release_zone", "get_task"}
)

ALLOWLIST: Mapping[str, frozenset[str]] = {
    "carrier": _MOTION,
    "forklift": _MOTION,
    "parts_runner": frozenset({"move_waypoint", "release_zone", "get_task", "get_inventory"}),
    "tech_repair": frozenset({"move_waypoint", "release_zone", "get_task", "open_ticket"}),
    "maintenance": frozenset(
        {
            "reserve_part",
            "dispatch_tech",
            "create_purchase_order",
            "open_ticket",
            "get_inventory",
            "close_ticket",
            "consume_reservation",
            "release_reservation",
        }
    ),
}

TOOLS: frozenset[str] = frozenset().union(*ALLOWLIST.values())


def allowed_tools(chassis: str) -> frozenset[str]:
    """The tools a chassis may call. Unknown means empty. The only reader of ``ALLOWLIST``
    for both the call path and the tool listing, so the two cannot drift."""
    return ALLOWLIST.get(chassis, frozenset())


def is_allowed(chassis: str, tool: str) -> bool:
    """True only when the chassis is known and lists the tool. Unknown means denied."""
    return tool in allowed_tools(chassis)
