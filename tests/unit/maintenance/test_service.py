"""Confirmed durable maintenance events use database diagnosis before bounded tool calls."""

from unittest.mock import MagicMock

import psycopg
import pytest

from waggle.db.connection import Database
from waggle.db.failure_history import FailureHistory
from waggle.maintenance.history import DatabaseDiagnosis
from waggle.maintenance.predictor import Reading
from waggle.maintenance.service import MaintenanceEvent, MaintenanceService
from waggle.maintenance.sheet import ManualSheet, default_sheet, load_sheet
from waggle.maintenance.tool_port import McpToolPort, ToolCallDenied
from waggle.mcp_server.bounds import MapExtent
from waggle.mcp_server.schemas import validate_call


def _event(key: str = "failure:pump-1:10") -> MaintenanceEvent:
    return MaintenanceEvent(key, "pump-1", "pump", Reading(1, 10, 60.0, 3.0, 4.0, 0.5))


@pytest.mark.parametrize("shortage", [False, True])
def test_success_closes_database_before_tools_and_reuses_durable_keys(shortage: bool) -> None:
    database, call, service = _setup()
    if shortage:
        call.results["reserve_part"] = {"reserved": False}
    result = service.handle(_event(), _sheet(), {"P-1"})
    assert result.status == "dispatched"
    assert result.diagnosis is not None
    assert result.source == "database_history"
    assert result.ticket_id == "ticket-1"
    assert [name for name, _ in call.calls] == (
        ["open_ticket", "reserve_part", "create_purchase_order", "dispatch_tech"]
        if shortage
        else ["open_ticket", "reserve_part", "dispatch_tech"]
    )
    first = tuple(call.calls)
    service.handle(_event(), _sheet(), {"P-1"})
    assert tuple(call.calls[len(first) :]) == first
    assert database.transaction.call_count == 2


class Calls:
    def __init__(self, database: MagicMock) -> None:
        self.database = database
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.results: dict[str, object] = {
            "open_ticket": {"ticket_id": "ticket-1"},
            "reserve_part": {"reserved": True},
            "create_purchase_order": {"ordered": True},
            "dispatch_tech": {"dispatched": True},
        }

    def __call__(self, tool: str, arguments: dict[str, object]) -> object:
        assert (
            self.database.transaction.return_value.__exit__.call_count
            == self.database.transaction.call_count
        )
        validate_call(tool, "maintenance", arguments, MapExtent(0, 0, 100, 100))
        self.calls.append((tool, arguments))
        result = self.results[tool]
        if isinstance(result, Exception):
            raise result
        return result


def _setup() -> tuple[MagicMock, Calls, MaintenanceService]:
    database = MagicMock(spec=Database)
    connection = database.transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = [
        ("fl-1", "pump", "BEARING_WEAR", 100, 60.0, 3.0, 4.0, "P-1")
    ]
    calls = Calls(database)
    service = MaintenanceService(
        DatabaseDiagnosis(FailureHistory(database)), McpToolPort(calls, ["tech-1"], lambda _: False)
    )
    return database, calls, service


def _sheet(part: str = "P-1", machine: str = "pump-1") -> ManualSheet:
    return load_sheet(
        {
            "machine_id": machine,
            "zone_id": "zone-1",
            "parts": {"BEARING_WEAR": {"part_number": part, "quantity": 1}},
        }
    )


@pytest.mark.parametrize(
    "tool", ["open_ticket", "reserve_part", "create_purchase_order", "dispatch_tech"]
)
def test_tool_failure_stops_downstream_calls(tool: str) -> None:
    _, call, service = _setup()
    if tool == "create_purchase_order":
        call.results["reserve_part"] = {"reserved": False}
    call.results[tool] = ToolCallDenied("denied")
    result = service.handle(_event(), _sheet(), {"P-1"})
    assert result.status == "escalated"
    assert call.calls[-1][0] == tool


def test_rejected_order_never_dispatches() -> None:
    _, call, service = _setup()
    call.results["reserve_part"] = {"reserved": False}
    call.results["create_purchase_order"] = {"ordered": False}
    assert service.handle(_event(), _sheet(), {"P-1"}).status == "escalated"
    assert call.calls[-1][0] == "create_purchase_order"


@pytest.mark.parametrize("part,catalog", [("P-2", {"P-1", "P-2"}), ("P-1", set())])
def test_diagnosis_cannot_override_sheet_or_catalog(part: str, catalog: set[str]) -> None:
    _, call, service = _setup()
    assert service.handle(_event(), _sheet(part), catalog).status == "escalated"
    assert call.calls == []


def test_missing_history_has_no_tool_side_effect() -> None:
    database, call, service = _setup()
    connection = database.transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = []
    assert service.handle(_event(), _sheet(), {"P-1"}).status == "escalated"
    assert call.calls == []


def test_missing_sheet_escalates_without_tools() -> None:
    _, call, service = _setup()
    result = service.handle(_event(), default_sheet("pump-1"), {"P-1"})
    assert result.reason == "sheet_disagreement"
    assert call.calls == []


def test_distinct_events_get_distinct_tool_keys() -> None:
    _, call, service = _setup()
    service.handle(_event("failure:pump-1:9"), _sheet(), {"P-1"})
    first_key = call.calls[0][1]["idempotency_key"]
    call.calls.clear()
    service.handle(_event(), _sheet(), {"P-1"})
    assert call.calls[0][1]["idempotency_key"] != first_key


def test_database_failure_has_no_tool_side_effect() -> None:
    database, call, service = _setup()
    database.transaction.side_effect = psycopg.OperationalError("unavailable")
    with pytest.raises(psycopg.OperationalError):
        service.handle(_event(), _sheet(), {"P-1"})
    assert call.calls == []


def test_sheet_for_other_machine_is_rejected_before_effects() -> None:
    database, call, service = _setup()
    with pytest.raises(ValueError, match="sheet"):
        service.handle(_event(), _sheet(machine="pump-2"), {"P-1"})
    database.transaction.assert_not_called()
    assert call.calls == []


@pytest.mark.parametrize("key", ["", "bad key", "failure:other:10", "a" * 129, "key\n"])
def test_event_key_is_validated(key: str) -> None:
    with pytest.raises(ValueError, match="event key"):
        _event(key)


@pytest.mark.parametrize("tick", [True, 10.5])
def test_event_tick_requires_a_nonnegative_integer(tick: object) -> None:
    reading = Reading(1, tick, 60.0, 3.0, 4.0, 0.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="event tick"):
        MaintenanceEvent("failure:pump-1:0", "pump-1", "pump", reading)
