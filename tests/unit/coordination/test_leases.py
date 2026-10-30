"""Lease boundaries, failed operations and generated operation sequences."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from waggle.coordination.leases import (
    LeaseReason,
    LeaseState,
    check_token,
    expire,
    grant,
    renew,
    revoke,
)


def test_grant_is_immutable_and_exclusive() -> None:
    initial = LeaseState("aisle")
    result = grant(initial, "robot-a", 0, 10)
    assert result.accepted and result.reason == LeaseReason.GRANTED
    assert result.state == LeaseState("aisle", 1, "robot-a", 10, 0)
    assert initial == LeaseState("aisle")
    denied = grant(result.state, "robot-b", 1, 10)
    assert not denied.accepted and denied.reason == LeaseReason.HELD
    assert denied.state.holder == "robot-a"
    assert denied.state.token == 1
    with pytest.raises(FrozenInstanceError):
        result.state.token = 2  # type: ignore[misc]


def test_repeated_grant_does_not_extend_or_increment() -> None:
    state = grant(LeaseState("aisle"), "a", 0, 10).state
    again = grant(state, "a", 2, 100)
    assert not again.accepted
    assert again.state.expires_tick == 10 and again.state.token == 1


def test_renew_preserves_token_and_cannot_shorten() -> None:
    state = grant(LeaseState("aisle"), "a", 0, 10).state
    result = renew(state, "a", 1, 4, 20)
    assert result.accepted and result.reason == LeaseReason.RENEWED
    assert result.state.token == 1 and result.state.expires_tick == 24
    shorter = renew(result.state, "a", 1, 5, 1)
    assert shorter.accepted and shorter.state.expires_tick == 24


@pytest.mark.parametrize(
    ("holder", "token", "tick"), [("b", 1, 1), ("a", 0, 1), ("a", 2, 1), ("a", 1, 10)]
)
def test_failed_renew_cannot_resurrect(holder: str, token: int, tick: int) -> None:
    state = grant(LeaseState("aisle"), "a", 0, 10).state
    result = renew(state, holder, token, tick, 10)
    assert not result.accepted and result.reason == LeaseReason.STALE
    assert result.state.expires_tick == 10
    assert not renew(LeaseState("aisle"), "a", 1, 0, 10).accepted


def test_expiry_is_half_open_and_keeps_token() -> None:
    state = grant(LeaseState("aisle"), "a", 2, 10).state
    early = expire(state, 11)
    assert not early.accepted and early.reason == LeaseReason.NOT_EXPIRED
    due = expire(early.state, 12)
    assert due.accepted and due.reason == LeaseReason.EXPIRED
    assert due.state.holder is None and due.state.token == 1
    assert due.state.expires_tick is None
    empty = expire(due.state, 12)
    assert not empty.accepted and empty.reason == LeaseReason.NO_LEASE
    assert grant(due.state, "b", 12, 10).state.token == 2


def test_revoke_requires_current_holder_and_token() -> None:
    state = grant(LeaseState("aisle"), "a", 0, 10).state
    for holder, token in [("b", 1), ("a", 0), ("a", 2)]:
        result = revoke(state, holder, token, 1)
        assert not result.accepted and result.state.holder == "a"
    assert not revoke(state, "a", 1, 10).accepted
    assert not revoke(LeaseState("aisle"), "a", 1, 0).accepted
    released = revoke(state, "a", 1, 1)
    assert released.accepted and released.reason == LeaseReason.REVOKED
    assert released.state.holder is None and released.state.token == 1
    replacement = grant(released.state, "a", 1, 10).state
    assert replacement.token == 2
    assert not check_token(replacement, "a", 1, 1)


def test_token_check_fails_closed_on_missing_future_and_expired_values() -> None:
    state = grant(LeaseState("aisle"), "a", 3, 10).state
    assert check_token(state, "a", 1, 3)
    assert check_token(state, "a", 1, 12)
    for holder, token, tick in [
        (None, 1, 3),
        ("a", None, 3),
        ("b", 1, 3),
        ("a", 0, 3),
        ("a", 2, 3),
        ("a", 1, 13),
        ("a", 1, 2),
    ]:
        assert not check_token(state, holder, token, tick)
    assert not check_token(LeaseState("aisle"), "a", 0, 0)
    assert not check_token(state, "a", True, 3)
    assert not check_token(state, "a", 1, True)


@pytest.mark.parametrize("bad", [-1, True, 1.5])
def test_invalid_ticks_and_durations_are_rejected(bad: int) -> None:
    state = LeaseState("aisle")
    with pytest.raises(ValueError):
        grant(state, "a", bad, 10)
    with pytest.raises(ValueError):
        grant(state, "a", 0, bad)
    with pytest.raises(ValueError):
        expire(state, bad)
    with pytest.raises(ValueError):
        renew(state, "a", 1, 0, bad)
    with pytest.raises(ValueError):
        revoke(state, "a", 1, bad)


def test_invalid_state_and_clock_regression_are_rejected() -> None:
    for state_args in [
        ("", 0, None, None, 0),
        ("x", -1, None, None, 0),
        ("x", 0, "a", 2, 0),
        ("x", 1, None, 2, 0),
        ("x", 1, "a", None, 0),
        ("x", 1, "", 2, 0),
    ]:
        with pytest.raises(ValueError):
            LeaseState(*state_args)
    state = grant(LeaseState("aisle"), "a", 10, 10).state
    operations: list[Callable[[], object]] = [
        lambda: grant(state, "b", 9, 10),
        lambda: expire(state, 9),
        lambda: renew(state, "a", 1, 9, 10),
        lambda: revoke(state, "a", 1, 9),
    ]
    for operation in operations:
        with pytest.raises(ValueError):
            operation()
    with pytest.raises(ValueError):
        grant(LeaseState("aisle"), "", 0, 10)
    with pytest.raises(ValueError):
        grant(LeaseState("aisle"), "a", 0, 0)


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["grant", "renew", "expire", "revoke"]),
            st.sampled_from(["a", "b", "c"]),
            st.integers(0, 8),
            st.integers(1, 12),
            st.booleans(),
        ),
        min_size=1,
        max_size=60,
    )
)
def test_generated_sequences_preserve_fencing_and_exclusion(
    operations: list[tuple[str, str, int, int, bool]],
) -> None:
    state = LeaseState("aisle")
    tick = 0
    issued: list[tuple[str, int]] = []
    for operation, holder, advance, duration, use_current in operations:
        tick += advance
        old = state
        token = state.token if use_current else max(0, state.token - 1)
        if operation == "grant":
            result = grant(state, holder, tick, duration)
            if result.accepted:
                assert result.state.token == old.token + 1
                issued.append((holder, result.state.token))
                if old.holder is not None and old.expires_tick is not None:
                    assert tick >= old.expires_tick
        elif operation == "renew":
            result = renew(state, holder, token, tick, duration)
        elif operation == "expire":
            result = expire(state, tick)
        else:
            result = revoke(state, holder, token, tick)
        state = result.state
        assert state.token >= old.token
        if operation != "grant" or not result.accepted:
            assert state.token == old.token
        accepted = [(h, t) for h, t in issued if check_token(state, h, t, tick)]
        assert len(accepted) <= 1
        for previous_holder, previous_token in issued:
            if previous_token < state.token:
                assert not check_token(state, previous_holder, previous_token, tick)
        assert sum(check_token(state, h, state.token, tick) for h in ("a", "b", "c")) <= 1
