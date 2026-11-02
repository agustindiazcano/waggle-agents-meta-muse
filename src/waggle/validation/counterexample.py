"""Counterexample record of the plan validator (ADR-023, section 3 of the validator design).

The record is frozen and every field is typed and bounded. ``code`` and ``rule`` are closed
enums, so no free text can be stored in them. The three fields of the first geofence check
(``code``, ``node``, ``zone``) keep their position and meaning.
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

MAX_ENTITIES: Final = 4


class CounterexampleCode(StrEnum):
    """The eight counterexample types of ADR-023, in severity order (first is worst)."""

    COLLISION = "COLLISION"
    SEPARATION_VIOLATION = "SEPARATION_VIOLATION"
    GEOFENCE_INTRUSION = "GEOFENCE_INTRUSION"
    CORRIDOR_DEADLOCK = "CORRIDOR_DEADLOCK"
    LEASE_CONFLICT = "LEASE_CONFLICT"
    ROUTE_INFEASIBLE = "ROUTE_INFEASIBLE"
    NO_PROGRESS = "NO_PROGRESS"
    UNSAFE_TERMINAL_STATE = "UNSAFE_TERMINAL_STATE"


class Rule(StrEnum):
    """Name of the violated rule. The list is an assumption to extend with later stages."""

    COLLISION_FREE = "COLLISION_FREE"
    SEPARATION_MIN = "SEPARATION_MIN"
    GEOFENCE_NO_ENTRY = "GEOFENCE_NO_ENTRY"
    ACYCLIC_WAIT = "ACYCLIC_WAIT"
    LEASE_EXCLUSIVE = "LEASE_EXCLUSIVE"
    NO_ROUTE = "NO_ROUTE"
    UNDECLARED_CORRIDOR = "UNDECLARED_CORRIDOR"
    AVOID_UNSATISFIABLE = "AVOID_UNSATISFIABLE"
    STATIC_CLEARANCE = "STATIC_CLEARANCE"
    PROGRESS_REQUIRED = "PROGRESS_REQUIRED"
    RECOVERABLE_TERMINAL = "RECOVERABLE_TERMINAL"


def _finite(value: object, name: str, *, minimum: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True)
class Counterexample:
    """Why a plan fails.

    ``variant`` is the human variant index, or None for a static check. ``time_s`` is the
    simulation time of the first occurrence, None for a static check. ``entities`` are robot
    ids, zone ids or the kind ``human``. ``zone`` is a zone id, ``place_xy_m`` a point in metres.
    The ``code`` annotation is ``str`` so that callers may pass the plain name, which is
    converted to ``CounterexampleCode`` on construction; any other value raises ValueError.
    """

    code: str
    node: str | None = None
    zone: str | None = None
    variant: int | None = None
    time_s: float | None = None
    entities: tuple[str, ...] = ()
    place_xy_m: tuple[float, float] | None = None
    min_clearance_m: float | None = None
    rule: Rule | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "code", CounterexampleCode(self.code))
        except ValueError:
            raise ValueError("code must be one of the eight counterexample types") from None
        if self.rule is not None:
            try:
                object.__setattr__(self, "rule", Rule(self.rule))
            except ValueError:
                raise ValueError("rule must be a known rule name") from None
        if self.variant is not None and (
            isinstance(self.variant, bool) or not isinstance(self.variant, int) or self.variant < 0
        ):
            raise ValueError("variant must be a non-negative integer or None")
        _finite(self.time_s, "time_s", minimum=0.0)
        _finite(self.min_clearance_m, "min_clearance_m", minimum=None)
        if len(self.entities) > MAX_ENTITIES:
            raise ValueError(f"entities holds at most {MAX_ENTITIES} items")
        if self.place_xy_m is not None:
            if len(self.place_xy_m) != 2:
                raise ValueError("place_xy_m must be an x, y pair")
            for coordinate in self.place_xy_m:
                _finite(coordinate, "place_xy_m", minimum=None)
                if coordinate is None:
                    raise ValueError("place_xy_m must be an x, y pair of numbers")
