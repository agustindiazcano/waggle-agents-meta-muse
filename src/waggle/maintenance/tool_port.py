"""A ``ToolPort`` backed by MCP-style callables (design section 6, ADR-076, ADR-081).

The port holds no authority and no connection. The caller supplies ``call(tool, arguments)``,
which goes through the authenticated MCP boundary under the ``maintenance`` identity, and raises
``ToolCallDenied`` for a denied or failed call. Argument names follow the tool schemas in
``waggle.mcp_server.schemas`` (this module does not import that package).

Mapping to the loop's protocol: a denial or a result that cannot be read raises ``ToolRefused``
for the ticket, reservation and order calls (the loop retries with the same keys, then
escalates). A shortage is ``False``. ``dispatch_tech`` needs a technician (the ADR-081 gap): the
port takes the first technician of a caller-supplied ordered list that is not busy, and tries
the next one when a call is denied; with none left it returns ``False``.
"""

import re
from collections.abc import Callable, Mapping, Sequence

from waggle.maintenance.loop import ToolRefused

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")

CallTool = Callable[[str, dict[str, object]], object]
IsBusy = Callable[[str], bool]


class ToolCallDenied(Exception):
    """The boundary denied the call or the tool failed. Raised by the caller's ``call``."""


class McpToolPort:
    """Implements ``waggle.maintenance.loop.ToolPort`` over a ``call`` callable."""

    def __init__(self, call: CallTool, technicians: Sequence[str], is_busy: IsBusy) -> None:
        if len(set(technicians)) != len(technicians) or any(
            not isinstance(t, str) or _ID.fullmatch(t) is None for t in technicians
        ):
            raise ValueError("technicians must be unique valid ids")
        self._call = call
        self._technicians = tuple(technicians)
        self._is_busy = is_busy

    def _result(self, tool: str, arguments: dict[str, object]) -> Mapping[str, object]:
        try:
            result = self._call(tool, arguments)
        except ToolCallDenied:
            raise ToolRefused(tool) from None
        if not isinstance(result, Mapping):
            raise ToolRefused(tool)
        return result

    def _flag(self, tool: str, arguments: dict[str, object], name: str) -> bool:
        value = self._result(tool, arguments).get(name)
        if not isinstance(value, bool):
            raise ToolRefused(tool)
        return value

    def open_ticket(self, key: str, machine_id: str, summary: str) -> str:
        """Open the ticket and return its id; an unreadable id is a refusal."""
        result = self._result(
            "open_ticket",
            {"machine_id": machine_id, "idempotency_key": key, "summary": summary},
        )
        ticket_id = result.get("ticket_id")
        if not isinstance(ticket_id, str) or _ID.fullmatch(ticket_id) is None:
            raise ToolRefused("open_ticket")
        return ticket_id

    def reserve_part(self, key: str, part_number: str, quantity: int, ticket_id: str) -> bool:
        """True when reserved, False on a shortage."""
        arguments: dict[str, object] = {
            "part_number": part_number,
            "quantity": quantity,
            "idempotency_key": key,
            "ticket_id": ticket_id,
        }
        return self._flag("reserve_part", arguments, "reserved")

    def create_purchase_order(
        self, key: str, part_number: str, quantity: int, ticket_id: str
    ) -> bool:
        """True when the order was placed."""
        arguments: dict[str, object] = {
            "part_number": part_number,
            "quantity": quantity,
            "idempotency_key": key,
            "ticket_id": ticket_id,
        }
        return self._flag("create_purchase_order", arguments, "ordered")

    def dispatch_tech(self, ticket_id: str, zone_id: str) -> bool:
        """Dispatch the first technician that is not busy; False when none can go."""
        for technician in self._technicians:
            if self._is_busy(technician):
                continue
            arguments: dict[str, object] = {
                "ticket_id": ticket_id,
                "zone_id": zone_id,
                "technician": technician,
            }
            try:
                result = self._call("dispatch_tech", arguments)
            except ToolCallDenied:
                continue
            if isinstance(result, Mapping) and result.get("dispatched") is True:
                return True
        return False
