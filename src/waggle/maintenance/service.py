"""Production maintenance actions for a caller-confirmed durable alert event.

The caller owns alert policy, persistence, event identity and recovery. It must retain the
same event key across attempts and replicas. This service has no lock, deduplication cache or
retry loop. Existing authenticated tools enforce durable idempotency and compatibility.
Diagnosis remains advisory: the manual sheet and catalog must agree before any action.
"""

import hashlib
import json
import re
from collections.abc import Set
from dataclasses import dataclass
from typing import Literal

from waggle.db.failure_history import MACHINE_CLASSES
from waggle.maintenance.diagnosis import DiagnosisEscalation, DiagnosisProposal
from waggle.maintenance.history import DatabaseDiagnosis
from waggle.maintenance.loop import Action, ToolPort, ToolRefused
from waggle.maintenance.predictor import Reading
from waggle.maintenance.sheet import ManualSheet

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def _tool_key(event: "MaintenanceEvent", stage: str) -> str:
    payload = json.dumps([event.machine_id, event.event_key, stage], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaintenanceEvent:
    """A confirmed alert, with its first triggering tick frozen in a durable caller key."""

    event_key: str
    machine_id: str
    machine_class: str
    reading: Reading

    def __post_init__(self) -> None:
        """Reject malformed identifiers and an event key belonging to another machine."""
        if type(self.reading.tick) is not int or self.reading.tick < 0:
            raise ValueError("invalid event tick")
        if not isinstance(self.machine_id, str) or _ID.fullmatch(self.machine_id) is None:
            raise ValueError("invalid machine id")
        prefix = f"failure:{self.machine_id}:"
        if (
            not isinstance(self.event_key, str)
            or not self.event_key.startswith(prefix)
            or not re.fullmatch(r"0|[1-9][0-9]*", self.event_key[len(prefix) :])
            or len(self.event_key) > 120
            or int(self.event_key[len(prefix) :]) > self.reading.tick
        ):
            raise ValueError("invalid event key")
        if self.machine_class not in MACHINE_CLASSES:
            raise ValueError("invalid machine class")


@dataclass(frozen=True)
class MaintenanceResult:
    """Explicit outcome and database provenance; no claim of a model diagnosis or repair."""

    event_key: str
    status: Literal["dispatched", "escalated"]
    reason: str
    diagnosis: DiagnosisProposal | DiagnosisEscalation
    ticket_id: str | None = None
    actions: tuple[Action, ...] = ()
    source: Literal["database_history"] = "database_history"


class MaintenanceService:
    """Resolve a database diagnosis and run one bounded pass through existing tools."""

    def __init__(self, history: DatabaseDiagnosis, tools: ToolPort) -> None:
        self._history = history
        self._tools = tools

    def handle(
        self, event: MaintenanceEvent, sheet: ManualSheet, catalog: Set[str]
    ) -> MaintenanceResult:
        """Act on a durable confirmed alert; database errors propagate before tool calls."""
        if sheet.machine_id != event.machine_id:
            raise ValueError("sheet machine does not match event")
        diagnosis = self._history.diagnose(event.machine_class, event.reading, catalog)
        if isinstance(diagnosis, DiagnosisEscalation):
            return MaintenanceResult(event.event_key, "escalated", diagnosis.reason, diagnosis)
        plan = sheet.plan_for(diagnosis.mode, catalog)
        if plan is None or plan.part_number != diagnosis.part_number:
            return MaintenanceResult(event.event_key, "escalated", "sheet_disagreement", diagnosis)
        actions: list[Action] = []
        ticket: str | None = None
        stage = "open_ticket"
        try:
            ticket = self._tools.open_ticket(
                _tool_key(event, stage),
                event.machine_id,
                f"predicted failure of {event.machine_id}",
            )
            actions.append(Action(stage, True))
            stage = "reserve_part"
            reserved = self._tools.reserve_part(
                _tool_key(event, stage), plan.part_number, plan.quantity, ticket
            )
            actions.append(Action(stage, reserved))
            if not reserved:
                stage = "create_purchase_order"
                ordered = self._tools.create_purchase_order(
                    _tool_key(event, stage), plan.part_number, plan.quantity, ticket
                )
                actions.append(Action(stage, ordered))
                if not ordered:
                    return MaintenanceResult(
                        event.event_key,
                        "escalated",
                        "order_rejected",
                        diagnosis,
                        ticket,
                        tuple(actions),
                    )
            stage = "dispatch_tech"
            dispatched = self._tools.dispatch_tech(ticket, plan.zone_id)
            actions.append(Action(stage, dispatched))
            return MaintenanceResult(
                event.event_key,
                "dispatched" if dispatched else "escalated",
                "dispatched" if dispatched else "dispatch_rejected",
                diagnosis,
                ticket,
                tuple(actions),
            )
        except ToolRefused:
            actions.append(Action(stage, False))
            return MaintenanceResult(
                event.event_key, "escalated", f"{stage}_refused", diagnosis, ticket, tuple(actions)
            )
