"""Production assembly for database-backed maintenance orchestration.

The caller still owns alert policy and the durable event key (see
``waggle.maintenance.service``). This module owns the remaining production
wiring: the catalog is read fresh from the ``spare_parts`` table on every
event, the manual sheet is looked up by machine id (a missing sheet is the
conservative default, so the event escalates), and the authenticated tool
port is assembled from the caller's MCP ``call`` callable. Every database
transaction closes before any tool call, because the repositories return
plain values and the diagnosis reads its own snapshot first.
"""

from collections.abc import Mapping, Sequence

from waggle.db.connection import Database
from waggle.db.failure_history import FailureHistory
from waggle.db.inventory import InventoryRepository
from waggle.maintenance.history import DatabaseDiagnosis
from waggle.maintenance.service import MaintenanceEvent, MaintenanceResult, MaintenanceService
from waggle.maintenance.sheet import ManualSheet, default_sheet
from waggle.maintenance.tool_port import CallTool, IsBusy, McpToolPort


class ProductionMaintenance:
    """One confirmed event in, one bounded database-backed action pass out."""

    def __init__(
        self,
        service: MaintenanceService,
        catalog: InventoryRepository,
        sheets: Mapping[str, ManualSheet],
    ) -> None:
        self._service = service
        self._catalog = catalog
        self._sheets = dict(sheets)

    def handle(self, event: MaintenanceEvent) -> MaintenanceResult:
        """Resolve sheet and catalog from production sources, then delegate."""
        sheet = self._sheets.get(event.machine_id)
        if sheet is None:
            sheet = default_sheet(event.machine_id)
        elif sheet.machine_id != event.machine_id:
            raise ValueError("sheet machine does not match event")
        catalog = self._catalog.part_numbers()
        return self._service.handle(event, sheet, catalog)


def build_production_maintenance(
    database: Database,
    call: CallTool,
    technicians: Sequence[str],
    is_busy: IsBusy,
    sheets: Mapping[str, ManualSheet],
) -> ProductionMaintenance:
    """Assemble the production service over a database and an MCP call callable."""
    service = MaintenanceService(
        DatabaseDiagnosis(FailureHistory(database)),
        McpToolPort(call, technicians, is_busy),
    )
    return ProductionMaintenance(service, InventoryRepository(database), sheets)
