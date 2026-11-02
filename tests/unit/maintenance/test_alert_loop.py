"""The alert loop turns predictor assessments into one ticket, one stock action and a dispatch.

It runs over a fake tool port: no database, no simulator, no model. Every case below is a rule of
design section 5 (A3 persistence) or section 6 (the loop) of docs/PREDICTIVE_MAINTENANCE_DESIGN.md.
"""

import ast
from pathlib import Path

import pytest

from waggle.maintenance.loop import (
    AlertPolicy,
    MaintenanceLoop,
    PartPlan,
    ToolRefused,
)
from waggle.maintenance.predictor import Assessment

PLAN = PartPlan("BRG-6204", 2, "zone-1")
POLICY = AlertPolicy(persistence=3, lead_target_ticks=100)


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.reserve_ok = True
        self.order_ok = True
        self.refuse: set[str] = set()

    def _do(self, name: str, *args: object) -> None:
        self.calls.append((name, args))
        if name in self.refuse:
            raise ToolRefused(name)

    def open_ticket(self, key: str, machine_id: str, summary: str) -> str:
        self._do("open_ticket", key, machine_id, summary)
        return "tkt-" + key[-8:]

    def reserve_part(self, key: str, part_number: str, quantity: int, ticket_id: str) -> bool:
        self._do("reserve_part", key, part_number, quantity, ticket_id)
        return self.reserve_ok

    def create_purchase_order(
        self, key: str, part_number: str, quantity: int, ticket_id: str
    ) -> bool:
        self._do("create_purchase_order", key, part_number, quantity, ticket_id)
        return self.order_ok

    def dispatch_tech(self, ticket_id: str, zone_id: str) -> bool:
        self._do("dispatch_tech", ticket_id, zone_id)
        return True

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def _a(
    tick: int,
    *,
    flag: bool = True,
    ttl: int | None = 50,
    scorable: bool = True,
    machine: int = 1,
) -> Assessment:
    return Assessment(machine, tick, True, scorable, flag, ("vibration",) if flag else (), ttl)


def _loop(
    tools: FakeTools, policy: AlertPolicy = POLICY, plans: dict[str, PartPlan] | None = None
) -> MaintenanceLoop:
    return MaintenanceLoop(
        policy, tools, {"M-1": PLAN, "M-2": PLAN} if plans is None else plans, lambda i: f"M-{i}"
    )


def _feed(loop: MaintenanceLoop, ticks: range, **kwargs: object) -> None:
    for tick in ticks:
        loop.step(_a(tick, **kwargs))  # type: ignore[arg-type]


def test_nothing_happens_before_the_flag_has_persisted() -> None:
    tools = FakeTools()
    _feed(_loop(tools), range(0, 2))
    assert tools.calls == []


def test_the_nth_consecutive_flag_opens_the_event() -> None:
    tools = FakeTools()
    _feed(_loop(tools), range(0, 3))
    assert tools.names() == ["open_ticket", "reserve_part", "dispatch_tech"]


def test_a_dropped_flag_restarts_the_count() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    for tick, flag in enumerate((True, True, False, True, True)):
        loop.step(_a(tick, flag=flag))
    assert tools.calls == []


def test_a_blind_predictor_never_opens_a_ticket() -> None:
    tools = FakeTools()
    _feed(_loop(tools), range(0, 500), flag=False, ttl=None)
    assert tools.calls == []


def test_the_estimate_must_be_under_the_lead_target_when_it_is_used() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    _feed(loop, range(0, 5), ttl=101)
    _feed(loop, range(5, 10), ttl=None)
    assert tools.calls == []
    _feed(loop, range(10, 13), ttl=100)
    assert tools.names()[0] == "open_ticket"


def test_the_flag_alone_triggers_when_the_estimate_is_not_used() -> None:
    tools = FakeTools()
    loop = _loop(tools, AlertPolicy(persistence=2, lead_target_ticks=100, use_estimate=False))
    _feed(loop, range(0, 2), ttl=None)
    assert tools.names()[0] == "open_ticket"


def test_the_event_key_is_the_machine_and_the_tick_of_the_first_trigger_and_stays() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    _feed(loop, range(0, 3))
    assert loop.event_key(1) == "failure:M-1:2"
    _feed(loop, range(3, 30), ttl=10)
    assert loop.event_key(1) == "failure:M-1:2"
    assert tools.calls[0][1][0] == "failure:M-1:2"


def test_a_repeated_alert_after_the_event_is_done_changes_nothing() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    _feed(loop, range(0, 3))
    count = len(tools.calls)
    _feed(loop, range(3, 40))
    assert len(tools.calls) == count


def test_no_stock_falls_back_to_a_purchase_order_before_dispatch() -> None:
    tools = FakeTools()
    tools.reserve_ok = False
    _feed(_loop(tools), range(0, 3))
    assert tools.names() == [
        "open_ticket",
        "reserve_part",
        "create_purchase_order",
        "dispatch_tech",
    ]


def test_a_technician_is_never_dispatched_without_a_reservation_or_an_order() -> None:
    tools = FakeTools()
    tools.reserve_ok = tools.order_ok = False
    _feed(_loop(tools), range(0, 3))
    assert "dispatch_tech" not in tools.names()


def test_a_machine_without_a_part_plan_gets_a_ticket_and_is_escalated() -> None:
    tools = FakeTools()
    loop = _loop(tools, plans={})
    _feed(loop, range(0, 3))
    assert tools.names() == ["open_ticket"]
    _feed(loop, range(3, 10))
    assert tools.names() == ["open_ticket"]
    assert loop.phase(1) == "escalated"


def test_a_refused_tool_is_retried_with_the_same_keys_then_escalated() -> None:
    tools = FakeTools()
    tools.refuse = {"reserve_part"}
    loop = _loop(tools)
    _feed(loop, range(0, 20))
    assert loop.phase(1) == "escalated"
    assert tools.names().count("reserve_part") == POLICY.max_attempts
    assert tools.names().count("open_ticket") == 1
    assert "dispatch_tech" not in tools.names()
    keys = {args[0] for name, args in tools.calls if name == "reserve_part"}
    assert keys == {"failure:M-1:2:reserve"}


def test_a_reading_that_cannot_be_scored_holds_and_is_reported() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    _feed(loop, range(0, 2))
    step = loop.step(_a(2, scorable=False))
    assert step.held and tools.calls == []
    assert not loop.step(_a(3, flag=True)).held
    assert tools.names()[0] == "open_ticket"


def test_machines_are_independent() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    for tick in range(0, 3):
        loop.step(_a(tick, machine=1))
        loop.step(_a(tick, machine=2, flag=False))
    assert {args[1] for name, args in tools.calls if name == "open_ticket"} == {"M-1"}


def test_the_same_assessments_give_the_same_calls() -> None:
    runs = []
    for _ in range(2):
        tools = FakeTools()
        _feed(_loop(tools), range(0, 6))
        runs.append(tools.calls)
    assert runs[0] == runs[1]


def test_reset_allows_a_new_event_after_a_repair() -> None:
    tools = FakeTools()
    loop = _loop(tools)
    _feed(loop, range(0, 3))
    loop.reset(1)
    _feed(loop, range(100, 103))
    assert tools.names().count("open_ticket") == 2
    assert loop.event_key(1) == "failure:M-1:102"


@pytest.mark.parametrize(
    "make",
    [
        lambda: AlertPolicy(persistence=0, lead_target_ticks=10),
        lambda: AlertPolicy(persistence=1, lead_target_ticks=0),
        lambda: AlertPolicy(persistence=1, lead_target_ticks=10, max_attempts=0),
        lambda: PartPlan("bad part", 1, "zone-1"),
        lambda: PartPlan("BRG-1", 0, "zone-1"),
        lambda: PartPlan("BRG-1", 1001, "zone-1"),
        lambda: PartPlan("BRG-1", 1, ""),
    ],
)
def test_invalid_policy_or_plan_is_refused(make: object) -> None:
    with pytest.raises(ValueError):
        make()  # type: ignore[operator]


def test_a_machine_name_that_cannot_be_a_key_is_refused_before_any_call() -> None:
    tools = FakeTools()
    loop = MaintenanceLoop(POLICY, tools, {"bad name": PLAN}, lambda i: "bad name")
    with pytest.raises(ValueError):
        _feed(loop, range(0, 3))
    assert tools.calls == []


def test_the_loop_imports_neither_the_simulator_nor_the_database() -> None:
    source = Path(__file__).parents[3] / "src" / "waggle" / "maintenance" / "loop.py"
    imported = {
        node.module or ""
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert not [m for m in imported if m.startswith(("waggle.sim", "waggle.db", "waggle.llm"))]
