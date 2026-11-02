"""The alert loop: predictor assessments in, one ticket, one stock action and a dispatch out.

Design sections 5 and 6 of docs/PREDICTIVE_MAINTENANCE_DESIGN.md. Deterministic code, no model
and no authority of its own: every action goes through a ``ToolPort`` that the caller backs with
the authenticated MCP tools. The alert rule is A3: the flag, and optionally an estimated time to
limit under the lead target, must hold for ``persistence`` consecutive scorable readings. A
reading that cannot be scored holds the count and is reported, never counted as a pass.

The event key is frozen at the tick that first satisfied the rule, so a re-estimated onset cannot
open a second ticket. The reservation and the order derive their keys from it. A technician is
dispatched only after a reservation or an order succeeded. This module imports nothing from the
simulator, the database or the LLM layer.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from waggle.maintenance.predictor import Assessment

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_QUANTITY_MAX = 1000
Phase = Literal["idle", "open", "done", "escalated"]


class ToolRefused(Exception):
    """A tool denied or failed the call. The loop retries with the same keys, up to a cap."""


class ToolPort(Protocol):
    """The loop's view of the maintenance tools. Each call must be idempotent by its key."""

    def open_ticket(self, key: str, machine_id: str, summary: str) -> str:
        """Open the ticket for the event and return its id."""
        ...

    def reserve_part(self, key: str, part_number: str, quantity: int, ticket_id: str) -> bool:
        """True when the stock was reserved, False on a shortage."""
        ...

    def create_purchase_order(
        self, key: str, part_number: str, quantity: int, ticket_id: str
    ) -> bool:
        """True when the order was placed."""
        ...

    def dispatch_tech(self, ticket_id: str, zone_id: str) -> bool:
        """True when the technician was dispatched."""
        ...


@dataclass(frozen=True)
class AlertPolicy:
    """The A3 parameters. ``persistence`` and ``lead_target_ticks`` are tuned on development
    seeds only and have no default here, so no number is invented."""

    persistence: int
    lead_target_ticks: int
    use_estimate: bool = True
    max_attempts: int = 3

    def __post_init__(self) -> None:
        """Reject a value that would make the rule meaningless."""
        for name in ("persistence", "lead_target_ticks", "max_attempts"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class PartPlan:
    """What to reserve and where to send the technician for one machine (from the sheet)."""

    part_number: str
    quantity: int
    zone_id: str

    def __post_init__(self) -> None:
        """Validate every field, as a sheet is data and not a trusted source."""
        for name in ("part_number", "zone_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or _ID.fullmatch(value) is None:
                raise ValueError(f"invalid {name}")
        if type(self.quantity) is not int or not 1 <= self.quantity <= _QUANTITY_MAX:
            raise ValueError("invalid quantity")


@dataclass(frozen=True)
class Action:
    """One tool call the loop made, and whether it counted as done."""

    kind: str
    ok: bool


@dataclass(frozen=True)
class LoopStep:
    """The result of one assessment. ``held`` means the reading could not be scored."""

    machine_id: int
    tick: int
    held: bool
    actions: tuple[Action, ...]


@dataclass
class _Machine:
    count: int = 0
    key: str | None = None
    ticket_id: str | None = None
    stocked: bool = False
    attempts: int = 0
    phase: Phase = "idle"
    log: list[Action] = field(default_factory=list)


class MaintenanceLoop:
    """Per machine state machine over the tool port. Holds no clock and no randomness."""

    def __init__(
        self,
        policy: AlertPolicy,
        tools: ToolPort,
        plans: Mapping[str, PartPlan],
        name_of: Callable[[int], str],
    ) -> None:
        self._policy = policy
        self._tools = tools
        self._plans = plans
        self._name_of = name_of
        self._machines: dict[int, _Machine] = {}

    def event_key(self, machine_id: int) -> str | None:
        """The frozen event key, or None before the rule first held."""
        return self._machines[machine_id].key if machine_id in self._machines else None

    def phase(self, machine_id: int) -> Phase:
        """``idle``, ``open``, ``done`` or ``escalated`` (needs a person)."""
        return self._machines[machine_id].phase if machine_id in self._machines else "idle"

    def reset(self, machine_id: int) -> None:
        """Forget a machine after a repair, so a later failure is a new event."""
        self._machines.pop(machine_id, None)

    def step(self, assessment: Assessment) -> LoopStep:
        """Feed one assessment. Raises ValueError for a machine name that cannot be a key."""
        machine_id, tick = assessment.machine_id, assessment.tick
        if not assessment.scorable:
            return LoopStep(machine_id, tick, True, ())
        machine = self._machines.setdefault(machine_id, _Machine())
        if machine.phase in ("done", "escalated"):
            return LoopStep(machine_id, tick, False, ())
        name = self._name_of(machine_id)
        if _ID.fullmatch(name) is None:
            raise ValueError("invalid machine name")
        if machine.key is None:
            machine.count = machine.count + 1 if self._triggers(assessment) else 0
            if machine.count < self._policy.persistence:
                return LoopStep(machine_id, tick, False, ())
            machine.key = f"failure:{name}:{tick}"
            machine.phase = "open"
        return LoopStep(machine_id, tick, False, self._advance(machine, name))

    def _triggers(self, a: Assessment) -> bool:
        if not a.flag:
            return False
        if not self._policy.use_estimate:
            return True
        ttl = a.time_to_limit_ticks
        return ttl is not None and ttl <= self._policy.lead_target_ticks

    def _advance(self, m: _Machine, name: str) -> tuple[Action, ...]:
        actions: list[Action] = []
        try:
            self._run_stages(m, name, actions)
        except ToolRefused:
            actions.append(Action("refused", False))
            self._fail(m)
        return tuple(actions)

    def _fail(self, m: _Machine) -> None:
        m.attempts += 1
        if m.attempts >= self._policy.max_attempts:
            m.phase = "escalated"

    def _run_stages(self, m: _Machine, name: str, actions: list[Action]) -> None:
        key = m.key
        assert key is not None
        if m.ticket_id is None:
            m.ticket_id = self._tools.open_ticket(key, name, f"predicted failure of {name}")
            actions.append(Action("open_ticket", True))
        plan = self._plans.get(name)
        if plan is None:
            actions.append(Action("no_part_plan", False))
            m.phase = "escalated"
            return
        if not m.stocked:
            m.stocked = self._stock(m, key, plan, actions)
            if not m.stocked:
                self._fail(m)
                return
        if self._tools.dispatch_tech(m.ticket_id, plan.zone_id):
            actions.append(Action("dispatch_tech", True))
            m.phase = "done"
        else:
            actions.append(Action("dispatch_tech", False))
            self._fail(m)

    def _stock(self, m: _Machine, key: str, plan: PartPlan, actions: list[Action]) -> bool:
        assert m.ticket_id is not None
        reserved = self._tools.reserve_part(
            f"{key}:reserve", plan.part_number, plan.quantity, m.ticket_id
        )
        actions.append(Action("reserve_part", reserved))
        if reserved:
            return True
        ordered = self._tools.create_purchase_order(
            f"{key}:order", plan.part_number, plan.quantity, m.ticket_id
        )
        actions.append(Action("create_purchase_order", ordered))
        return ordered
