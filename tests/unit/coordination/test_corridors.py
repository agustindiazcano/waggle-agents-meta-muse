"""Atomic corridor admission, expiry recovery and S03-like opposite traffic."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.coordination.corridors import (
    CorridorReason,
    CorridorRequest,
    CorridorState,
    CorridorZone,
    Direction,
    ZoneObservation,
    ZoneToken,
    expire_corridors,
    release_corridor,
    request_corridor,
)
from waggle.coordination.leases import LeaseState, check_token


def empty_state() -> CorridorState:
    return CorridorState((CorridorZone(LeaseState("east")), CorridorZone(LeaseState("west"))))


def observations(
    tick: int, east: tuple[str, ...] | None = (), west: tuple[str, ...] | None = ()
) -> tuple[ZoneObservation, ...]:
    return (ZoneObservation("east", tick, east), ZoneObservation("west", tick, west))


def request(
    holder: str = "a",
    resources: tuple[str, ...] = ("east", "west"),
    direction: Direction = Direction.FORWARD,
) -> CorridorRequest:
    return CorridorRequest(holder, resources, direction)


def test_s03_like_opposite_robots_make_progress_in_turn() -> None:
    state = empty_state()
    forward = request_corridor(state, request(), 0, observations(0), 10)
    assert forward.granted and forward.reason == CorridorReason.GRANTED
    assert forward.tokens == (ZoneToken("east", 1), ZoneToken("west", 1))
    reverse = request("b", direction=Direction.REVERSE)
    waiting = request_corridor(forward.state, reverse, 1, observations(1, ("a",)), 10)
    assert not waiting.granted and waiting.reason == CorridorReason.HELD
    assert all(zone.lease.holder == "a" for zone in waiting.state.zones)
    released = release_corridor(waiting.state, "a", forward.tokens, 5, observations(5))
    assert released.granted and released.reason == CorridorReason.RELEASED
    admitted = request_corridor(released.state, reverse, 5, observations(5), 10)
    assert admitted.granted
    assert all(zone.lease.holder == "b" for zone in admitted.state.zones)
    assert all(zone.direction == Direction.REVERSE for zone in admitted.state.zones)
    assert all(token.token == 2 for token in admitted.tokens)
    assert state == empty_state()


def test_robot_that_never_releases_loses_empty_corridor_at_expiry() -> None:
    first = request_corridor(empty_state(), request(), 0, observations(0), 10)
    waiting = request_corridor(first.state, request("b"), 9, observations(9), 10)
    assert not waiting.granted
    second = request_corridor(waiting.state, request("b"), 10, observations(10), 10)
    assert second.granted and all(token.token == 2 for token in second.tokens)
    for zone in second.state.zones:
        assert not check_token(zone.lease, "a", 1, 10)
    assert not release_corridor(second.state, "a", first.tokens, 10, observations(10)).granted


@pytest.mark.parametrize("occupants", [("a",), None])
def test_expired_occupied_or_unknown_zone_is_not_reassigned(
    occupants: tuple[str, ...] | None,
) -> None:
    first = request_corridor(empty_state(), request(), 0, observations(0), 10)
    swept = expire_corridors(first.state, 10, observations(10, occupants))
    assert swept.zones[0].fault_occupied
    assert swept.zones[0].lease.holder == "a"
    blocked = request_corridor(swept, request("b"), 10, observations(10, occupants), 10)
    assert not blocked.granted and blocked.reason == CorridorReason.FAULT_OCCUPIED
    assert all(zone.lease.holder != "b" for zone in blocked.state.zones)
    recovered = request_corridor(blocked.state, request("b"), 11, observations(11), 10)
    assert recovered.granted and not any(z.fault_occupied for z in recovered.state.zones)


def test_unknown_stale_or_occupied_observation_denies_admission() -> None:
    for seen, reason in [
        ((), CorridorReason.OCCUPANCY_UNKNOWN),
        (observations(0), CorridorReason.OCCUPANCY_UNKNOWN),
        (observations(1, ("stranger",)), CorridorReason.OCCUPIED),
    ]:
        result = request_corridor(empty_state(), request(), 1, seen, 10)
        assert not result.granted and result.reason == reason
        assert all(zone.lease.token == 0 for zone in result.state.zones)
    future = request_corridor(empty_state(), request(), 1, observations(2), 10)
    assert not future.granted


def test_atomic_conflict_leaves_no_partial_grant_and_order_is_canonical() -> None:
    first = request_corridor(empty_state(), request("b", ("west",)), 0, observations(0), 10)
    blocked = request_corridor(first.state, request(), 1, observations(1), 10)
    assert not blocked.granted
    assert blocked.state.zones[0].lease.holder is None
    assert blocked.state.zones[0].lease.token == 0
    assert blocked.state.zones[1].lease.holder == "b"
    reordered = request_corridor(
        empty_state(), request(resources=("west", "east")), 0, observations(0), 10
    )
    canonical = request_corridor(empty_state(), request(), 0, observations(0), 10)
    assert reordered == canonical


def test_holder_cannot_extend_reservation_or_change_direction_by_retry() -> None:
    first = request_corridor(empty_state(), request(), 0, observations(0), 10)
    retry = request_corridor(first.state, request(), 1, observations(1, ("a",)), 100)
    assert retry.granted and retry.reason == CorridorReason.ALREADY_HELD
    assert retry.tokens == first.tokens
    assert all(zone.lease.expires_tick == 10 for zone in retry.state.zones)
    reverse = request_corridor(
        first.state, request(direction=Direction.REVERSE), 1, observations(1), 10
    )
    assert not reverse.granted and reverse.reason == CorridorReason.DIRECTION_CONFLICT
    partial = request_corridor(empty_state(), request(resources=("east",)), 0, observations(0), 10)
    expanded = request_corridor(partial.state, request(), 1, observations(1), 10)
    assert not expanded.granted and expanded.reason == CorridorReason.MUST_RELEASE
    disjoint = request_corridor(partial.state, request(resources=("west",)), 1, observations(1), 10)
    assert not disjoint.granted and disjoint.reason == CorridorReason.MUST_RELEASE


def test_release_is_atomic_and_rejects_occupied_missing_and_stale_grants() -> None:
    first = request_corridor(empty_state(), request(), 0, observations(0), 10)
    for tokens, seen, reason in [
        ((ZoneToken("east", 0), ZoneToken("west", 1)), observations(1), CorridorReason.STALE),
        (first.tokens[:1], observations(1), CorridorReason.MUST_RELEASE),
        (first.tokens, (), CorridorReason.OCCUPANCY_UNKNOWN),
        (first.tokens, observations(1, ("a",)), CorridorReason.OCCUPIED),
    ]:
        denied = release_corridor(first.state, "a", tokens, 1, seen)
        assert not denied.granted and denied.reason == reason
        assert all(zone.lease.holder == "a" for zone in denied.state.zones)
    assert not release_corridor(first.state, "b", first.tokens, 1, observations(1)).granted
    assert not release_corridor(first.state, "a", first.tokens, 10, observations(10)).granted


def test_invalid_requests_unknown_resources_and_clock_regression() -> None:
    for resources in [(), ("east", "east"), ("",)]:
        with pytest.raises(ValueError):
            request(resources=resources)
    with pytest.raises(ValueError):
        CorridorRequest("", ("east",), Direction.FORWARD)
    with pytest.raises(ValueError):
        CorridorState((CorridorZone(LeaseState("east")), CorridorZone(LeaseState("east"))))
    with pytest.raises(ValueError):
        CorridorZone(LeaseState("east"), Direction.FORWARD)
    with pytest.raises(ValueError):
        request_corridor(empty_state(), request(resources=("missing",)), 0, observations(0))
    with pytest.raises(ValueError):
        request_corridor(empty_state(), request(), 0, observations(0), 0)
    first = request_corridor(empty_state(), request(), 5, observations(5))
    with pytest.raises(ValueError):
        expire_corridors(first.state, 4, observations(4))
    with pytest.raises(ValueError):
        request_corridor(empty_state(), request(), 0, observations(0) * 2)
    with pytest.raises(ValueError):
        release_corridor(first.state, "a", first.tokens * 2, 6, observations(6))


@settings(max_examples=75, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["a", "b"]), st.booleans(), st.integers(0, 5), st.booleans()),
        min_size=1,
        max_size=40,
    )
)
def test_generated_corridor_requests_never_overlap(
    operations: list[tuple[str, bool, int, bool]],
) -> None:
    state = empty_state()
    tick = 0
    old_tokens: list[tuple[str, tuple[ZoneToken, ...]]] = []
    for holder, reverse, advance, release in operations:
        tick += advance
        previous = state
        direction = Direction.REVERSE if reverse else Direction.FORWARD
        result = request_corridor(
            state, request(holder, direction=direction), tick, observations(tick), 4
        )
        state = result.state
        assert all(
            a.lease.token <= b.lease.token for a, b in zip(previous.zones, state.zones, strict=True)
        )
        if result.granted:
            old_tokens.append((holder, result.tokens))
            if release:
                state = release_corridor(
                    state, holder, result.tokens, tick, observations(tick)
                ).state
        for zone in state.zones:
            assert sum(check_token(zone.lease, h, zone.lease.token, tick) for h in ("a", "b")) <= 1
            for old_holder, tokens in old_tokens:
                old_token = next(t.token for t in tokens if t.resource_id == zone.lease.resource_id)
                if old_token < zone.lease.token:
                    assert not check_token(zone.lease, old_holder, old_token, tick)
        assert len({z.lease.holder for z in state.zones if z.lease.holder is not None}) <= 1


def test_opposing_partial_holders_must_release_instead_of_waiting_on_a_cycle() -> None:
    left = request_corridor(empty_state(), request("a", ("east",)), 0, observations(0), 10)
    right = request_corridor(
        left.state, request("b", ("west",), Direction.REVERSE), 1, observations(1), 10
    )
    assert left.granted and right.granted
    for holder, direction in [("a", Direction.FORWARD), ("b", Direction.REVERSE)]:
        expansion = request_corridor(
            right.state, request(holder, direction=direction), 2, observations(2), 10
        )
        assert not expansion.granted
        assert expansion.reason == CorridorReason.MUST_RELEASE
    released_a = release_corridor(right.state, "a", left.tokens, 3, observations(3))
    released_b = release_corridor(released_a.state, "b", right.tokens, 3, observations(3))
    forward = request_corridor(released_b.state, request(), 3, observations(3), 10)
    assert forward.granted
    reverse = request_corridor(
        forward.state, request("b", direction=Direction.REVERSE), 3, observations(3), 10
    )
    assert not reverse.granted and reverse.reason == CorridorReason.HELD
