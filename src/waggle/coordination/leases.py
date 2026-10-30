"""Pure capacity-one leases with caller-supplied ticks and persistent token history.

This is a logical model, not a transaction or a physical occupancy check. A caller
must serialize transitions and persist the returned state before using a grant.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

DEFAULT_LEASE_TICKS = 400


def _integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _identity(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


@dataclass(frozen=True)
class LeaseState:
    """Authoritative resource state; keep token history even while unassigned."""

    resource_id: str
    token: int = 0
    holder: str | None = None
    expires_tick: int | None = None
    observed_tick: int = 0

    def __post_init__(self) -> None:
        _identity(self.resource_id, "resource_id")
        _integer(self.token, "token")
        _integer(self.observed_tick, "observed_tick")
        if (self.holder is None) != (self.expires_tick is None):
            raise ValueError("holder and expiry must be present together")
        if self.holder is not None:
            _identity(self.holder, "holder")
            _integer(self.token, "active token", 1)
        if self.expires_tick is not None:
            _integer(self.expires_tick, "expires_tick", 1)


class LeaseReason(StrEnum):
    """Stable outcomes for a lease transition."""

    GRANTED = "granted"
    RENEWED = "renewed"
    REVOKED = "revoked"
    EXPIRED = "expired"
    HELD = "held"
    STALE = "stale"
    NO_LEASE = "no_lease"
    NOT_EXPIRED = "not_expired"


@dataclass(frozen=True)
class LeaseResult:
    """A transition result and the next authoritative state, including denials."""

    state: LeaseState
    accepted: bool
    reason: LeaseReason


def _at_tick(state: LeaseState, now_tick: int) -> LeaseState:
    _integer(now_tick, "now_tick")
    if now_tick < state.observed_tick:
        raise ValueError("now_tick must not precede the last observed tick")
    return replace(state, observed_tick=now_tick)


def check_token(state: LeaseState, holder: str | None, token: int | None, now_tick: int) -> bool:
    """Accept only the exact live holder and token; missing or invalid data denies."""
    return (
        type(now_tick) is int
        and now_tick >= state.observed_tick
        and isinstance(holder, str)
        and bool(holder.strip())
        and holder == state.holder
        and type(token) is int
        and token > 0
        and token == state.token
        and state.expires_tick is not None
        and now_tick < state.expires_tick
    )


def grant(
    state: LeaseState, holder: str, now_tick: int, lease_ticks: int = DEFAULT_LEASE_TICKS
) -> LeaseResult:
    """Grant a free or expired logical resource, incrementing its token once."""
    _identity(holder, "holder")
    _integer(lease_ticks, "lease_ticks", 1)
    current = _at_tick(state, now_tick)
    if current.expires_tick is not None and now_tick < current.expires_tick:
        return LeaseResult(current, False, LeaseReason.HELD)
    return LeaseResult(
        replace(
            current, holder=holder, token=current.token + 1, expires_tick=now_tick + lease_ticks
        ),
        True,
        LeaseReason.GRANTED,
    )


def renew(
    state: LeaseState,
    holder: str,
    token: int,
    now_tick: int,
    lease_ticks: int = DEFAULT_LEASE_TICKS,
) -> LeaseResult:
    """Extend a live grant without changing its token or shortening its lifetime."""
    _identity(holder, "holder")
    _integer(lease_ticks, "lease_ticks", 1)
    current = _at_tick(state, now_tick)
    if not check_token(current, holder, token, now_tick):
        return LeaseResult(current, False, LeaseReason.STALE)
    assert current.expires_tick is not None
    return LeaseResult(
        replace(current, expires_tick=max(current.expires_tick, now_tick + lease_ticks)),
        True,
        LeaseReason.RENEWED,
    )


def expire(state: LeaseState, now_tick: int) -> LeaseResult:
    """Clear an expired logical grant at its exclusive endpoint, retaining its token."""
    current = _at_tick(state, now_tick)
    if current.expires_tick is None:
        return LeaseResult(current, False, LeaseReason.NO_LEASE)
    if now_tick < current.expires_tick:
        return LeaseResult(current, False, LeaseReason.NOT_EXPIRED)
    return LeaseResult(replace(current, holder=None, expires_tick=None), True, LeaseReason.EXPIRED)


def revoke(state: LeaseState, holder: str, token: int, now_tick: int) -> LeaseResult:
    """Release a live grant only for its exact holder and token."""
    _identity(holder, "holder")
    current = _at_tick(state, now_tick)
    if not check_token(current, holder, token, now_tick):
        return LeaseResult(current, False, LeaseReason.STALE)
    return LeaseResult(replace(current, holder=None, expires_tick=None), True, LeaseReason.REVOKED)
