"""The tool port over MCP-style callables: technician choice, error mapping, no authority."""

import pytest

from waggle.maintenance.loop import ToolPort, ToolRefused
from waggle.maintenance.tool_port import McpToolPort, ToolCallDenied

_DEFAULTS: dict[str, object] = {
    "open_ticket": {"ticket_id": "tkt-1", "created": True},
    "reserve_part": {"reserved": True, "reason": "ok"},
    "create_purchase_order": {"ordered": True, "reason": "ok"},
    "dispatch_tech": {"dispatched": True},
}


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.results: dict[str, object] = {}

    def __call__(self, tool: str, arguments: dict[str, object]) -> object:
        self.calls.append((tool, dict(arguments)))
        outcome = self.results.get(tool, _DEFAULTS[tool])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _port(
    rec: Recorder, techs: tuple[str, ...] = ("tech-1", "tech-2"), busy: set[str] | None = None
) -> McpToolPort:
    taken = busy or set()
    return McpToolPort(rec, techs, lambda t: t in taken)


def test_the_port_satisfies_the_loop_protocol() -> None:
    port: ToolPort = _port(Recorder())
    assert port is not None


def test_open_ticket_uses_the_schema_argument_names() -> None:
    rec = Recorder()
    assert _port(rec).open_ticket("failure:m:9", "m", "predicted failure of m") == "tkt-1"
    assert rec.calls == [
        (
            "open_ticket",
            {
                "machine_id": "m",
                "idempotency_key": "failure:m:9",
                "summary": "predicted failure of m",
            },
        )
    ]


def test_reserve_and_order_use_the_schema_argument_names() -> None:
    rec = Recorder()
    port = _port(rec)
    assert port.reserve_part("k:reserve", "P-1", 2, "tkt-1") is True
    assert port.create_purchase_order("k:order", "P-1", 2, "tkt-1") is True
    assert rec.calls[0] == (
        "reserve_part",
        {
            "part_number": "P-1",
            "quantity": 2,
            "idempotency_key": "k:reserve",
            "ticket_id": "tkt-1",
        },
    )
    assert rec.calls[1][0] == "create_purchase_order"


def test_a_shortage_is_false_not_an_error() -> None:
    rec = Recorder()
    rec.results["reserve_part"] = {"reserved": False, "reason": "insufficient"}
    assert _port(rec).reserve_part("k", "P-1", 1, "tkt-1") is False


def test_a_denied_open_ticket_is_a_refusal() -> None:
    rec = Recorder()
    rec.results["open_ticket"] = ToolCallDenied("ticket not available")
    with pytest.raises(ToolRefused):
        _port(rec).open_ticket("k", "m", "s")


def test_a_denied_reservation_is_a_refusal() -> None:
    rec = Recorder()
    rec.results["reserve_part"] = ToolCallDenied("reservation not available")
    with pytest.raises(ToolRefused):
        _port(rec).reserve_part("k", "P-1", 1, "tkt-1")


@pytest.mark.parametrize("bad", [{}, {"ticket_id": 5}, {"ticket_id": "bad id"}, "text"])
def test_an_open_ticket_result_without_a_valid_id_is_a_refusal(bad: object) -> None:
    rec = Recorder()
    rec.results["open_ticket"] = bad
    with pytest.raises(ToolRefused):
        _port(rec).open_ticket("k", "m", "s")


@pytest.mark.parametrize("bad", [{}, {"reserved": "yes"}, {"error": "denied"}])
def test_a_reservation_result_that_is_not_a_bool_fails_closed(bad: object) -> None:
    rec = Recorder()
    rec.results["reserve_part"] = bad
    with pytest.raises(ToolRefused):
        _port(rec).reserve_part("k", "P-1", 1, "tkt-1")


def test_dispatch_picks_the_first_technician_that_is_not_busy() -> None:
    rec = Recorder()
    assert _port(rec, busy={"tech-1"}).dispatch_tech("tkt-1", "zone-3") is True
    assert rec.calls == [
        ("dispatch_tech", {"ticket_id": "tkt-1", "zone_id": "zone-3", "technician": "tech-2"})
    ]


def test_dispatch_with_every_technician_busy_returns_false_and_calls_nothing() -> None:
    rec = Recorder()
    assert _port(rec, busy={"tech-1", "tech-2"}).dispatch_tech("tkt-1", "z") is False
    assert rec.calls == []


def test_dispatch_with_no_technicians_returns_false() -> None:
    rec = Recorder()
    assert _port(rec, techs=()).dispatch_tech("tkt-1", "z") is False


def test_a_denied_dispatch_tries_the_next_technician() -> None:
    calls: list[dict[str, object]] = []
    outcomes: list[object] = [ToolCallDenied("dispatch not available"), {"dispatched": True}]

    def call(tool: str, arguments: dict[str, object]) -> object:
        calls.append(dict(arguments))
        out = outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    port = McpToolPort(call, ("tech-1", "tech-2"), lambda t: False)
    assert port.dispatch_tech("tkt-1", "z") is True
    assert [c["technician"] for c in calls] == ["tech-1", "tech-2"]


def test_every_dispatch_denied_returns_false() -> None:
    rec = Recorder()
    rec.results["dispatch_tech"] = ToolCallDenied("dispatch not available")
    assert _port(rec).dispatch_tech("tkt-1", "z") is False


def test_a_dispatch_result_that_does_not_confirm_is_false() -> None:
    rec = Recorder()
    rec.results["dispatch_tech"] = {"dispatched": "maybe"}
    assert _port(rec).dispatch_tech("tkt-1", "z") is False


def test_the_technician_choice_is_deterministic() -> None:
    a, b = Recorder(), Recorder()
    _port(a).dispatch_tech("t", "z")
    _port(b).dispatch_tech("t", "z")
    assert a.calls == b.calls


def test_technician_ids_are_validated() -> None:
    with pytest.raises(ValueError):
        McpToolPort(Recorder(), ("bad id",), lambda t: False)
    with pytest.raises(ValueError):
        McpToolPort(Recorder(), ("tech-1", "tech-1"), lambda t: False)


def test_an_unexpected_error_is_not_swallowed() -> None:
    rec = Recorder()
    rec.results["open_ticket"] = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _port(rec).open_ticket("k", "m", "s")
