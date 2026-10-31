"""Pure all-or-nothing corridor reservations, with explicit occupancy evidence.

Every robot requests its entire corridor before entering. No partial expansion,
implicit renewal or physical clearance based only on lease expiry is allowed.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from waggle.coordination.leases import (
    DEFAULT_LEASE_TICKS,
    LeaseState,
    _identity,
    _integer,
    check_token,
    expire,
    grant,
    revoke,
)


class Direction(StrEnum):
    """Traversal direction relative to the caller's fixed corridor orientation."""

    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True)
class CorridorZone:
    """A resource lease, its reserved direction, and an occupancy fault latch."""

    lease: LeaseState
    direction: Direction | None = None
    fault_occupied: bool = False

    def __post_init__(self) -> None:
        if (self.lease.holder is None) != (self.direction is None):
            raise ValueError("a held corridor must have exactly one direction")
        if self.direction is not None and not isinstance(self.direction, Direction):
            raise ValueError("invalid direction")
        if type(self.fault_occupied) is not bool:
            raise ValueError("fault_occupied must be a boolean")
        if self.fault_occupied and self.lease.holder is None:
            raise ValueError("an occupancy fault must retain its previous holder")


@dataclass(frozen=True)
class CorridorState:
    """Explicit resource table in canonical resource-id order."""

    zones: tuple[CorridorZone, ...]

    def __post_init__(self) -> None:
        ids = [zone.lease.resource_id for zone in self.zones]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate resource_id")
        object.__setattr__(
            self, "zones", tuple(sorted(self.zones, key=lambda z: z.lease.resource_id))
        )


@dataclass(frozen=True)
class CorridorRequest:
    """One robot's complete capacity-one route, acquired in a single transition."""

    holder: str
    resource_ids: tuple[str, ...]
    direction: Direction
    directions_by_resource: tuple[tuple[str, Direction], ...] = ()

    def __post_init__(self) -> None:
        _identity(self.holder, "holder")
        if not self.resource_ids or len(self.resource_ids) != len(set(self.resource_ids)):
            raise ValueError("request must contain unique resources")
        for resource_id in self.resource_ids:
            _identity(resource_id, "resource_id")
        if not isinstance(self.direction, Direction):
            raise ValueError("invalid direction")
        object.__setattr__(self, "resource_ids", tuple(sorted(self.resource_ids)))
        if self.directions_by_resource:
            direction_ids = [resource_id for resource_id, _ in self.directions_by_resource]
            if (
                len(direction_ids) != len(set(direction_ids))
                or set(direction_ids) != set(self.resource_ids)
                or any(
                    not isinstance(direction, Direction)
                    for _, direction in self.directions_by_resource
                )
            ):
                raise ValueError("directions must cover each requested resource exactly once")
            object.__setattr__(
                self,
                "directions_by_resource",
                tuple(sorted(self.directions_by_resource, key=lambda item: item[0])),
            )

    def direction_for(self, resource_id: str) -> Direction:
        """Return the requested direction for one resource, using the legacy uniform value."""
        if resource_id not in self.resource_ids:
            raise ValueError("resource is not in this request")
        if not self.directions_by_resource:
            return self.direction
        return dict(self.directions_by_resource)[resource_id]


@dataclass(frozen=True)
class ZoneObservation:
    """Trusted occupancy at a tick; None means no knowledge, an empty tuple means clear."""

    resource_id: str
    observed_tick: int
    occupants: tuple[str, ...] | None

    def __post_init__(self) -> None:
        _identity(self.resource_id, "resource_id")
        _integer(self.observed_tick, "observed_tick")
        if self.occupants is not None:
            for occupant in self.occupants:
                _identity(occupant, "occupant")
            if len(self.occupants) != len(set(self.occupants)):
                raise ValueError("duplicate occupant")
            object.__setattr__(self, "occupants", tuple(sorted(self.occupants)))


@dataclass(frozen=True)
class ZoneToken:
    """Resource-scoped fencing token; never compare tokens across resources."""

    resource_id: str
    token: int

    def __post_init__(self) -> None:
        _identity(self.resource_id, "resource_id")
        _integer(self.token, "token")


class CorridorReason(StrEnum):
    """Grant or wait reasons; waiting never grants a subset of a request."""

    GRANTED = "granted"
    ALREADY_HELD = "already_held"
    RELEASED = "released"
    HELD = "held"
    MUST_RELEASE = "must_release"
    DIRECTION_CONFLICT = "direction_conflict"
    OCCUPANCY_UNKNOWN = "occupancy_unknown"
    OCCUPIED = "occupied"
    FAULT_OCCUPIED = "fault_occupied"
    STALE = "stale"


@dataclass(frozen=True)
class CorridorResult:
    """Next resource table and either a complete grant or a wait with its reason."""

    state: CorridorState
    granted: bool
    reason: CorridorReason
    tokens: tuple[ZoneToken, ...] = ()


def _observations(
    state: CorridorState,
    now_tick: int,
    observations: tuple[ZoneObservation, ...],
) -> dict[str, tuple[str, ...] | None]:
    _integer(now_tick, "now_tick")
    if any(now_tick < zone.lease.observed_tick for zone in state.zones):
        raise ValueError("now_tick must not precede the last observed tick")
    ids = [observation.resource_id for observation in observations]
    known = {zone.lease.resource_id for zone in state.zones}
    if len(ids) != len(set(ids)) or not set(ids) <= known:
        raise ValueError("duplicate or unknown observation resource")
    return {
        observation.resource_id: observation.occupants
        if observation.observed_tick == now_tick
        else None
        for observation in observations
    }


def expire_corridors(
    state: CorridorState,
    now_tick: int,
    observations: tuple[ZoneObservation, ...],
) -> CorridorState:
    """Expire clear zones, retaining occupied or unknown expired zones as faults."""
    seen = _observations(state, now_tick, observations)
    zones: list[CorridorZone] = []
    for zone in state.zones:
        expiry = zone.lease.expires_tick
        due = expiry is not None and now_tick >= expiry
        if due and seen.get(zone.lease.resource_id) != ():
            zones.append(
                replace(
                    zone, lease=replace(zone.lease, observed_tick=now_tick), fault_occupied=True
                )
            )
        else:
            result = expire(zone.lease, now_tick)
            zones.append(
                CorridorZone(
                    result.state,
                    zone.direction if result.state.holder else None,
                    zone.fault_occupied if result.state.holder else False,
                )
            )
    return CorridorState(tuple(zones))


def _wait(state: CorridorState, reason: CorridorReason) -> CorridorResult:
    return CorridorResult(state, False, reason)


def request_corridor(
    state: CorridorState,
    request: CorridorRequest,
    now_tick: int,
    observations: tuple[ZoneObservation, ...],
    lease_ticks: int = DEFAULT_LEASE_TICKS,
) -> CorridorResult:
    """Reserve every route resource or wait; a retry never renews or expands a grant."""
    _integer(lease_ticks, "lease_ticks", 1)
    known = {zone.lease.resource_id for zone in state.zones}
    requested = set(request.resource_ids)
    if not requested <= known:
        raise ValueError("unknown corridor resource")
    seen = _observations(state, now_tick, observations)
    current = expire_corridors(state, now_tick, observations)
    required = [z for z in current.zones if z.lease.resource_id in requested]
    owned = {z.lease.resource_id for z in current.zones if z.lease.holder == request.holder}
    if any(zone.fault_occupied for zone in required):
        return _wait(current, CorridorReason.FAULT_OCCUPIED)
    if owned and owned != requested:
        return _wait(current, CorridorReason.MUST_RELEASE)
    if any(z.lease.holder not in (None, request.holder) for z in required):
        return _wait(current, CorridorReason.HELD)
    if owned and any(z.direction != request.direction_for(z.lease.resource_id) for z in required):
        return _wait(current, CorridorReason.DIRECTION_CONFLICT)
    for zone in required:
        occupants = seen.get(zone.lease.resource_id)
        if occupants is None:
            return _wait(current, CorridorReason.OCCUPANCY_UNKNOWN)
        if occupants and (not owned or occupants != (request.holder,)):
            return _wait(current, CorridorReason.OCCUPIED)
    if owned:
        return CorridorResult(
            current,
            True,
            CorridorReason.ALREADY_HELD,
            tuple(ZoneToken(z.lease.resource_id, z.lease.token) for z in required),
        )
    zones = tuple(
        CorridorZone(
            grant(z.lease, request.holder, now_tick, lease_ticks).state,
            request.direction_for(z.lease.resource_id),
        )
        if z.lease.resource_id in requested
        else z
        for z in current.zones
    )
    updated = CorridorState(zones)
    tokens = tuple(
        ZoneToken(z.lease.resource_id, z.lease.token)
        for z in updated.zones
        if z.lease.resource_id in requested
    )
    return CorridorResult(updated, True, CorridorReason.GRANTED, tokens)


def release_corridor(
    state: CorridorState,
    holder: str,
    tokens: tuple[ZoneToken, ...],
    now_tick: int,
    observations: tuple[ZoneObservation, ...],
) -> CorridorResult:
    """Release the holder's whole route only with live tokens and clear occupancy."""
    _identity(holder, "holder")
    ids = [token.resource_id for token in tokens]
    if not tokens or len(ids) != len(set(ids)):
        raise ValueError("release must contain unique tokens")
    seen = _observations(state, now_tick, observations)
    current = expire_corridors(state, now_tick, observations)
    owned = {z.lease.resource_id for z in current.zones if z.lease.holder == holder}
    supplied = {token.resource_id: token.token for token in tokens}
    if owned and set(supplied) != owned:
        return _wait(current, CorridorReason.MUST_RELEASE)
    required = [z for z in current.zones if z.lease.resource_id in supplied]
    if (
        len(required) != len(supplied)
        or not required
        or any(
            not check_token(z.lease, holder, supplied[z.lease.resource_id], now_tick)
            for z in required
        )
    ):
        return _wait(current, CorridorReason.STALE)
    for zone in required:
        occupants = seen.get(zone.lease.resource_id)
        if occupants is None:
            return _wait(current, CorridorReason.OCCUPANCY_UNKNOWN)
        if occupants:
            return _wait(current, CorridorReason.OCCUPIED)
    zones = tuple(
        CorridorZone(revoke(z.lease, holder, supplied[z.lease.resource_id], now_tick).state)
        if z.lease.resource_id in supplied
        else z
        for z in current.zones
    )
    return CorridorResult(CorridorState(zones), True, CorridorReason.RELEASED)
