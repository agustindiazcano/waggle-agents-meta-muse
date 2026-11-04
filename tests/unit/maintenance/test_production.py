"""Production orchestration loads the catalog from the database and assembles the service."""

from typing import cast

import psycopg
import pytest

from waggle.db.connection import Database
from waggle.db.inventory import InventoryRepository
from waggle.maintenance.predictor import Reading
from waggle.maintenance.production import build_production_maintenance
from waggle.maintenance.service import MaintenanceEvent
from waggle.maintenance.sheet import ManualSheet, load_sheet
from waggle.maintenance.tool_port import CallTool


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)


class _Connection:
    def __init__(self, database: "FakeDatabase") -> None:
        self._database = database

    def execute(self, sql: str, params: object = None) -> _Cursor:
        if "failure_history" in sql:
            if self._database.fail:
                raise psycopg.OperationalError("unavailable")
            return _Cursor(list(self._database.history))
        if "spare_parts" in sql:
            return _Cursor([(part,) for part in self._database.parts])
        raise AssertionError(sql)


class _Transaction:
    def __init__(self, database: "FakeDatabase") -> None:
        self._database = database

    def __enter__(self) -> _Connection:
        self._database.open_transactions += 1
        return _Connection(self._database)

    def __exit__(self, *args: object) -> None:
        self._database.open_transactions -= 1
        self._database.closed_transactions += 1


class FakeDatabase:
    """Minimal Database stand-in dispatching on the queried table."""

    def __init__(self) -> None:
        self.history: list[tuple[object, ...]] = [
            ("fl-1", "pump", "BEARING_WEAR", 100, 60.0, 3.0, 4.0, "P-1")
        ]
        self.parts: list[str] = ["P-1"]
        self.fail = False
        self.open_transactions = 0
        self.closed_transactions = 0

    def transaction(self) -> _Transaction:
        return _Transaction(self)


def _event() -> MaintenanceEvent:
    return MaintenanceEvent(
        "failure:pump-1:10", "pump-1", "pump", Reading(1, 10, 60.0, 3.0, 4.0, 0.5)
    )


def _sheet(machine: str = "pump-1") -> ManualSheet:
    return load_sheet(
        {
            "machine_id": machine,
            "zone_id": "zone-1",
            "parts": {"BEARING_WEAR": {"part_number": "P-1", "quantity": 1}},
        }
    )


def _tools(database: FakeDatabase, calls: list[str]) -> CallTool:
    def call(tool: str, arguments: dict[str, object]) -> dict[str, object]:
        assert database.open_transactions == 0
        calls.append(tool)
        results: dict[str, dict[str, object]] = {
            "open_ticket": {"ticket_id": "ticket-1"},
            "reserve_part": {"reserved": True},
            "create_purchase_order": {"ordered": True},
            "dispatch_tech": {"dispatched": True},
        }
        return results[tool]

    return call


def test_part_numbers_come_from_the_catalog_table() -> None:
    database = FakeDatabase()
    database.parts = ["P-2", "P-1"]
    repo = InventoryRepository(cast(Database, database))
    assert repo.part_numbers() == frozenset({"P-1", "P-2"})
    assert database.open_transactions == 0


def test_production_handle_dispatches_with_database_catalog() -> None:
    database = FakeDatabase()
    calls: list[str] = []
    service = build_production_maintenance(
        cast(Database, database),
        _tools(database, calls),
        ["tech-1"],
        lambda _: False,
        {"pump-1": _sheet()},
    )
    result = service.handle(_event())
    assert result.status == "dispatched"
    assert result.ticket_id == "ticket-1"
    assert calls == ["open_ticket", "reserve_part", "dispatch_tech"]
    assert database.closed_transactions >= 2


def test_missing_sheet_escalates_without_tools() -> None:
    database = FakeDatabase()
    calls: list[str] = []
    service = build_production_maintenance(
        cast(Database, database),
        _tools(database, calls),
        ["tech-1"],
        lambda _: False,
        {},
    )
    result = service.handle(_event())
    assert result.status == "escalated"
    assert result.reason == "sheet_disagreement"
    assert calls == []


def test_part_missing_from_database_catalog_escalates_without_tools() -> None:
    database = FakeDatabase()
    database.parts = ["P-9"]
    calls: list[str] = []
    service = build_production_maintenance(
        cast(Database, database),
        _tools(database, calls),
        ["tech-1"],
        lambda _: False,
        {"pump-1": _sheet()},
    )
    result = service.handle(_event())
    assert result.status == "escalated"
    assert calls == []


def test_database_failure_propagates_without_tools() -> None:
    database = FakeDatabase()
    database.fail = True
    calls: list[str] = []
    service = build_production_maintenance(
        cast(Database, database),
        _tools(database, calls),
        ["tech-1"],
        lambda _: False,
        {"pump-1": _sheet()},
    )
    with pytest.raises(psycopg.OperationalError):
        service.handle(_event())
    assert calls == []
