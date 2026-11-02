"""dispatch_tech with a technician lease, close_ticket and the two settlement tools (ADR-074)."""

import pytest

from waggle.coordination.corridors import ZoneObservation
from waggle.db.corridors import IdempotencyConflict
from waggle.db.settlement import ReservationSettled, SettlementResult, UnknownReservation
from waggle.db.ticket_lease import CloseOutcome, DispatchOutcome
from waggle.db.tickets import UnknownTicket, UnknownZone
from waggle.mcp_server.forwarder import FencedForwarder, ToolDenied, ToolUnavailable
from waggle.mcp_server.identity import Identity

MAINT = Identity("maintenance", "maint-0")
TICKET = "tkt-0000000000000001"
DISPATCH = {"ticket_id": TICKET, "zone_id": "zone-1", "technician": "tech-0"}


class FakeTicks:
    def now_tick(self) -> int:
        return 42


class FakeOccupancy:
    def __init__(self) -> None:
        self.asked: list[tuple[tuple[str, ...], int]] = []

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        self.asked.append((zone_ids, now_tick))
        return tuple(ZoneObservation(z, now_tick, ()) for z in zone_ids)


class FakeLeases:
    def __init__(
        self,
        dispatch: DispatchOutcome | Exception | None = None,
        close: CloseOutcome | Exception | None = None,
        zone: str | None = "zone-1",
    ) -> None:
        self.dispatch_result = dispatch or DispatchOutcome(True, True, "granted", 7)
        self.close_result = close or CloseOutcome(True, True, "released")
        self.zone = zone
        self.dispatched: list[tuple[str, str, str, str, int, tuple[ZoneObservation, ...]]] = []
        self.closed: list[tuple[str, str, int, tuple[ZoneObservation, ...]]] = []

    def dispatch(
        self,
        ticket_id: str,
        zone_id: str,
        dispatcher: str,
        technician: str,
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
    ) -> DispatchOutcome:
        if isinstance(self.dispatch_result, Exception):
            raise self.dispatch_result
        self.dispatched.append((ticket_id, zone_id, dispatcher, technician, now_tick, observations))
        return self.dispatch_result

    def close(
        self, ticket_id: str, closer: str, now_tick: int, observations: tuple[ZoneObservation, ...]
    ) -> CloseOutcome:
        if isinstance(self.close_result, Exception):
            raise self.close_result
        self.closed.append((ticket_id, closer, now_tick, observations))
        return self.close_result

    def zone_of(self, ticket_id: str) -> str | None:
        return self.zone


class FakeTechnicians:
    def __init__(self, known: frozenset[str] = frozenset({"tech-0"})) -> None:
        self.known = known

    def is_technician(self, robot_id: str) -> bool:
        return robot_id in self.known


class FakeSettlement:
    def __init__(self, error: Exception | None = None, changed: bool = True) -> None:
        self.error = error
        self.changed = changed
        self.calls: list[tuple[str, str]] = []

    def consume(self, key: str) -> SettlementResult:
        if self.error:
            raise self.error
        self.calls.append(("consume", key))
        return SettlementResult("consumed", self.changed)

    def release(self, key: str) -> SettlementResult:
        if self.error:
            raise self.error
        self.calls.append(("release", key))
        return SettlementResult("released", self.changed)


def _forwarder(
    leases: FakeLeases | None = None,
    technicians: FakeTechnicians | None = None,
    settlement: FakeSettlement | None = None,
    occupancy: FakeOccupancy | None = None,
) -> FencedForwarder:
    return FencedForwarder(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        FakeTicks(),
        occupancy or FakeOccupancy(),
        leases=leases,
        technicians=technicians,
        settlement=settlement,
    )


def test_dispatch_takes_the_lease_at_the_trusted_tick_with_trusted_occupancy() -> None:
    leases = FakeLeases()
    out = _forwarder(leases, FakeTechnicians()).forward(MAINT, "dispatch_tech", DISPATCH, 5)
    assert out == {
        "dispatched": True,
        "ticket_id": TICKET,
        "zone_id": "zone-1",
        "reason": "granted",
    }
    ticket, zone, dispatcher, technician, tick, observations = leases.dispatched[0]
    assert (ticket, zone, dispatcher, technician, tick) == (
        TICKET,
        "zone-1",
        "maint-0",
        "tech-0",
        42,
    )
    assert observations == (ZoneObservation("zone-1", 42, ()),)


def test_dispatch_never_returns_the_lease_token() -> None:
    out = _forwarder(FakeLeases(), FakeTechnicians()).forward(MAINT, "dispatch_tech", DISPATCH, 5)
    assert "token" not in out
    assert 7 not in out.values()


def test_a_busy_zone_is_a_result_not_an_error() -> None:
    leases = FakeLeases(dispatch=DispatchOutcome(False, False, "held_elsewhere", None))
    out = _forwarder(leases, FakeTechnicians()).forward(MAINT, "dispatch_tech", DISPATCH, 5)
    assert out["dispatched"] is False
    assert out["reason"] == "held_elsewhere"


@pytest.mark.parametrize("known", [frozenset(), frozenset({"someone-else"})])
def test_dispatch_denies_a_technician_that_is_not_a_registered_tech_repair_robot(
    known: frozenset[str],
) -> None:
    leases = FakeLeases()
    with pytest.raises(ToolDenied, match="dispatch not available"):
        _forwarder(leases, FakeTechnicians(known)).forward(MAINT, "dispatch_tech", DISPATCH, 5)
    assert leases.dispatched == []


@pytest.mark.parametrize(
    "error", [UnknownTicket("t"), UnknownZone("z"), IdempotencyConflict("other technician")]
)
def test_dispatch_denies_unknown_references_and_a_second_technician(error: Exception) -> None:
    with pytest.raises(ToolDenied, match="dispatch not available"):
        _forwarder(FakeLeases(dispatch=error), FakeTechnicians()).forward(
            MAINT, "dispatch_tech", DISPATCH, 5
        )


@pytest.mark.parametrize(
    ("leases", "technicians"),
    [(None, FakeTechnicians()), (FakeLeases(), None)],
)
def test_dispatch_is_unavailable_without_the_lease_or_the_technician_port(
    leases: FakeLeases | None, technicians: FakeTechnicians | None
) -> None:
    """No silent fallback to a dispatch without a lease."""
    with pytest.raises(ToolUnavailable):
        _forwarder(leases, technicians).forward(MAINT, "dispatch_tech", DISPATCH, 5)


def test_close_releases_with_the_zone_of_the_ticket_observed() -> None:
    leases = FakeLeases(zone="zone-9")
    occupancy = FakeOccupancy()
    out = _forwarder(leases, occupancy=occupancy).forward(
        MAINT, "close_ticket", {"ticket_id": TICKET}, 5
    )
    assert out == {"closed": True, "reason": "released"}
    assert occupancy.asked == [(("zone-9",), 42)]
    assert leases.closed == [(TICKET, "maint-0", 42, (ZoneObservation("zone-9", 42, ()),))]


def test_close_denied_by_the_lease_is_a_result_with_its_reason() -> None:
    leases = FakeLeases(close=CloseOutcome(False, False, "occupied"))
    out = _forwarder(leases).forward(MAINT, "close_ticket", {"ticket_id": TICKET}, 5)
    assert out == {"closed": False, "reason": "occupied"}


@pytest.mark.parametrize("zone", [None])
def test_close_of_a_ticket_without_a_zone_denies_and_closes_nothing(zone: str | None) -> None:
    leases = FakeLeases(zone=zone)
    with pytest.raises(ToolDenied, match="close not available"):
        _forwarder(leases).forward(MAINT, "close_ticket", {"ticket_id": TICKET}, 5)
    assert leases.closed == []


def test_close_denies_an_unknown_ticket() -> None:
    with pytest.raises(ToolDenied, match="close not available"):
        _forwarder(FakeLeases(close=UnknownTicket("t"))).forward(
            MAINT, "close_ticket", {"ticket_id": TICKET}, 5
        )


def test_close_is_unavailable_without_the_lease_port() -> None:
    with pytest.raises(ToolUnavailable):
        _forwarder().forward(MAINT, "close_ticket", {"ticket_id": TICKET}, 5)


@pytest.mark.parametrize(
    ("tool", "status"), [("consume_reservation", "consumed"), ("release_reservation", "released")]
)
def test_settlement_tools_settle_the_reservation_by_key(tool: str, status: str) -> None:
    settlement = FakeSettlement()
    out = _forwarder(settlement=settlement).forward(MAINT, tool, {"idempotency_key": "evt-1"}, 5)
    assert out == {"status": status, "changed": True}
    assert settlement.calls == [(tool.split("_")[0], "evt-1")]


@pytest.mark.parametrize("tool", ["consume_reservation", "release_reservation"])
@pytest.mark.parametrize("error", [UnknownReservation("k"), ReservationSettled("k")])
def test_settlement_tools_deny_with_one_text_for_every_failed_check(
    tool: str, error: Exception
) -> None:
    with pytest.raises(ToolDenied, match=r"^settlement not available$"):
        _forwarder(settlement=FakeSettlement(error)).forward(
            MAINT, tool, {"idempotency_key": "evt-1"}, 5
        )


@pytest.mark.parametrize("tool", ["consume_reservation", "release_reservation"])
def test_settlement_tools_are_unavailable_without_the_port(tool: str) -> None:
    with pytest.raises(ToolUnavailable):
        _forwarder().forward(MAINT, tool, {"idempotency_key": "evt-1"}, 5)
