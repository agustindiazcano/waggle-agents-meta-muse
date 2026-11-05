"""Package ground truth: status, holder and position as state arrays (PACKAGE_MODEL_DESIGN).

The simulator owns where every package is. Arrays are named ``pkg_status``, ``pkg_holder`` and
``pkg_pos``, so snapshots, forks and the canonical hash cover them. A scenario with no packages
adds no array and its hash does not change.

Legal transitions: AT_STATION to HELD (pick), HELD to DELIVERED (deliver in a station or depot),
HELD to AT_STATION (the holder failed, released at its last pose), HELD to LOST (explicit drop
outside any station or depot). DELIVERED and LOST are terminal. Every check reads state, never
the order text, and any missing, non-finite or unknown value fails closed. The model has no
random draw and no clock.
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import cast

import numpy as np
from numpy.typing import NDArray

from waggle.sim import params, state, streams, world
from waggle.sim.engine import System

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_DROP_KINDS = frozenset({"station", "depot"})
NO_HOLDER = -1


class Status(IntEnum):
    """Package status codes stored in ``pkg_status``."""

    AT_STATION = 0
    HELD = 1
    DELIVERED = 2
    LOST = 3


class PackageError(ValueError):
    """A package declaration is malformed."""


class PackageInvariantError(RuntimeError):
    """The package arrays break an invariant."""


@dataclass(frozen=True)
class PackageSpec:
    """One package at load: id, home zone and start position in meters."""

    package_id: str
    zone_id: str
    x: float
    y: float


@dataclass(frozen=True)
class PackageOutcome:
    """Result of an order. ``reason`` names the failed check, for tests and logs only."""

    ok: bool
    reason: str


def _fail(reason: str) -> PackageOutcome:
    return PackageOutcome(False, reason)


_DONE = PackageOutcome(True, "done")


def point_in_polygon(x: float, y: float, polygon: world.Polygon) -> bool:
    """Ray casting test: True when ``(x, y)`` is inside ``polygon``."""
    inside = False
    pts = polygon.points
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def validate_specs(box: world.World, specs: Sequence[PackageSpec]) -> None:
    """Raise PackageError unless ids are unique and valid and each package is inside a station
    or depot zone of ``box``."""
    seen: set[str] = set()
    for spec in specs:
        if not isinstance(spec.package_id, str) or _ID.fullmatch(spec.package_id) is None:
            raise PackageError("package id must match [A-Za-z0-9_.-]{1,64}")
        if spec.package_id in seen:
            raise PackageError(f"duplicate package id {spec.package_id!r}")
        seen.add(spec.package_id)
        try:
            zone = box.zone(spec.zone_id)
        except KeyError as err:
            raise PackageError(f"unknown zone {spec.zone_id!r}") from err
        if zone.kind not in _DROP_KINDS:
            raise PackageError(f"package zone {spec.zone_id!r} must be a station or depot")
        if not _finite(spec.x, spec.y) or not point_in_polygon(spec.x, spec.y, zone.polygon):
            raise PackageError(f"package {spec.package_id!r} is not inside zone {spec.zone_id!r}")


MAX_PLACED = 1000
_PLACEMENT_TRIES = 1000


def place_packages(box: world.World, count: int, seed: int) -> tuple[PackageSpec, ...]:
    """``count`` packages placed in the station and depot zones, a pure function of the seed.

    Uses its own stream (subsystem ``scenario``), never an engine stream, so a run's random
    state does not change. Raises PackageError for a bad count or seed or a map with no
    station or depot.
    """
    if type(count) is not int or not 0 <= count <= MAX_PLACED:
        raise PackageError(f"count must be an integer from 0 to {MAX_PLACED}")
    if type(seed) is not int or seed < 0:
        raise PackageError("seed must be a non-negative integer")
    zones = [z for z in box.zones if z.kind in _DROP_KINDS]
    if count == 0:
        return ()
    if not zones:
        raise PackageError("the map has no station or depot zone")
    rng = streams.make_streams(seed, "scenario", 1)[0]
    placed: list[PackageSpec] = []
    for n in range(count):
        zone = zones[int(rng.integers(0, len(zones)))]
        xs = [p[0] for p in zone.polygon.points]
        ys = [p[1] for p in zone.polygon.points]
        for _ in range(_PLACEMENT_TRIES):
            x = float(rng.uniform(min(xs), max(xs)))
            y = float(rng.uniform(min(ys), max(ys)))
            if point_in_polygon(x, y, zone.polygon):
                placed.append(PackageSpec(f"pk-{n + 1:03d}", zone.id, x, y))
                break
        else:
            raise PackageError(f"could not place a package in zone {zone.id!r}")
    return tuple(placed)


def _validate_capacities(capacities: Sequence[int]) -> tuple[int, ...]:
    for c in capacities:
        if type(c) is not int or c < 0:
            raise PackageError("capacity must be a non-negative integer")
    return tuple(capacities)


class PackageModel:
    """Static package facts plus the functions that read and change the package arrays.

    The model itself holds no ground truth: ids, the map and capacities are fixed at load, and
    the only mutable member is the table of outcomes by order id, which makes a replayed order
    id return its first outcome without a second effect.
    """

    def __init__(
        self,
        box: world.World,
        specs: Sequence[PackageSpec],
        capacities: Sequence[int],
    ) -> None:
        validate_specs(box, specs)
        self._world = box
        self._specs = tuple(specs)
        self._capacity = _validate_capacities(capacities)
        self._index = {s.package_id: i for i, s in enumerate(self._specs)}
        self._outcomes: dict[int, PackageOutcome] = {}

    @property
    def package_ids(self) -> tuple[str, ...]:
        """The simulator package ids, in spec order."""
        return tuple(spec.package_id for spec in self._specs)

    @property
    def count(self) -> int:
        """Number of packages. Constant for the whole run (conservation)."""
        return len(self._specs)

    def initial_arrays(self) -> dict[str, state.Array]:
        """State arrays at load. Empty when there are no packages, so no hash changes."""
        if not self._specs:
            return {}
        n = len(self._specs)
        pos = np.array([[s.x, s.y] for s in self._specs], dtype=np.float64)
        return {
            "pkg_status": np.full(n, int(Status.AT_STATION), dtype=np.int64),
            "pkg_holder": np.full(n, NO_HOLDER, dtype=np.int64),
            "pkg_pos": pos,
        }

    def system(self) -> System:
        """Each tick, a held package takes the pose of its holder. Place it after the robots."""

        def follow(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
            if "pkg_status" not in sim.arrays:
                return
            status, holder, pos, pose = self._arrays(sim)
            for i in np.flatnonzero(status == int(Status.HELD)):
                pos[i] = pose[int(holder[i]), :2]

        return follow

    # ------------------------------------------------------------ orders

    def pick(
        self, sim: state.SimState, order_id: int, robot: int, package_id: str
    ) -> PackageOutcome:
        """AT_STATION to HELD when every precondition holds. Replays return the first outcome."""
        return self._once(order_id, lambda: self._pick(sim, robot, package_id))

    def deliver(
        self, sim: state.SimState, order_id: int, robot: int, package_id: str, zone_id: str
    ) -> PackageOutcome:
        """HELD to DELIVERED inside a station or depot zone, by the holder."""
        return self._once(order_id, lambda: self._deliver(sim, robot, package_id, zone_id))

    def drop(
        self, sim: state.SimState, order_id: int, robot: int, package_id: str
    ) -> PackageOutcome:
        """HELD to LOST when the holder drops it outside every station and depot."""
        return self._once(order_id, lambda: self._drop(sim, robot, package_id))

    def release_holder(self, sim: state.SimState, robot: int) -> int:
        """HELD to AT_STATION at the last pose for every package this robot holds.

        Called when the robot fails. Returns how many packages were released.
        """
        if type(robot) is not int or "pkg_status" not in sim.arrays:
            return 0
        status, holder, pos, pose = self._arrays(sim)
        if not 0 <= robot < pose.shape[0]:
            return 0
        released = np.flatnonzero((status == int(Status.HELD)) & (holder == robot))
        for i in released:
            status[i] = int(Status.AT_STATION)
            holder[i] = NO_HOLDER
            pos[i] = pose[robot, :2]
        return int(released.size)

    def status_of(self, sim: state.SimState, package_id: str) -> Status | None:
        """The status of a package, or None for an unknown id or missing arrays."""
        i = self._index.get(package_id) if isinstance(package_id, str) else None
        if i is None or "pkg_status" not in sim.arrays:
            return None
        try:
            return Status(int(np.asarray(sim.arrays["pkg_status"])[i]))
        except ValueError:
            return None

    # ------------------------------------------------------------ invariants

    def check_invariants(self, sim: state.SimState) -> None:
        """Raise PackageInvariantError when the arrays break an invariant."""
        if not self._specs:
            if any(name.startswith("pkg_") for name in sim.arrays):
                raise PackageInvariantError("package arrays exist for a run with no packages")
            return
        try:
            status, holder, pos, pose = self._arrays(sim)
        except (KeyError, ValueError) as err:
            raise PackageInvariantError(f"package arrays are missing or malformed: {err}") from err
        n = self.count
        if status.shape != (n,) or holder.shape != (n,) or pos.shape != (n, 2):
            raise PackageInvariantError("conservation: package array shapes changed")
        if not np.all(np.isin(status, [int(s) for s in Status])):
            raise PackageInvariantError("unknown status code")
        if not np.all(np.isfinite(pos)):
            raise PackageInvariantError("non-finite package position")
        held = status == int(Status.HELD)
        if np.any(holder[~held] != NO_HOLDER):
            raise PackageInvariantError("a package that is not held has a holder")
        if np.any((holder[held] < 0) | (holder[held] >= pose.shape[0])):
            raise PackageInvariantError("a held package has no valid holder")
        for robot in range(pose.shape[0]):
            limit = self._capacity[robot] if robot < len(self._capacity) else 0
            if int(np.count_nonzero(held & (holder == robot))) > limit:
                raise PackageInvariantError(f"robot {robot} holds more than its capacity")

    # ------------------------------------------------------------ internals

    def _once(self, order_id: int, run: Callable[[], PackageOutcome]) -> PackageOutcome:
        if type(order_id) is not int:
            return _fail("bad order id")
        cached = self._outcomes.get(order_id)
        if cached is not None:
            return cached
        outcome = run()
        self._outcomes[order_id] = outcome
        return outcome

    def _arrays(
        self, sim: state.SimState
    ) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64], NDArray[np.float64]]:
        a = sim.arrays
        return (
            _ints(a["pkg_status"]),
            _ints(a["pkg_holder"]),
            _floats(a["pkg_pos"]),
            _floats(a["robot_pose"]),
        )

    def _pick(self, sim: state.SimState, robot: int, package_id: str) -> PackageOutcome:
        ready = self._ready(sim, robot, package_id)
        if isinstance(ready, PackageOutcome):
            return ready
        i, x, y = ready
        status, holder, pos, _ = self._arrays(sim)
        if status[i] != int(Status.AT_STATION):
            return _fail("package not at a station")
        px, py = float(pos[i, 0]), float(pos[i, 1])
        if not _finite(px, py) or math.hypot(px - x, py - y) > params.PACKAGE_PICK_RADIUS:
            return _fail("too far")
        if not any(
            point_in_polygon(x, y, z.polygon) and point_in_polygon(px, py, z.polygon)
            for z in self._world.zones
        ):
            return _fail("not in the package zone")
        held = int(np.count_nonzero((status == int(Status.HELD)) & (holder == robot)))
        if held >= self._capacity_of(robot):
            return _fail("over capacity")
        status[i] = int(Status.HELD)
        holder[i] = robot
        pos[i] = (x, y)
        return _DONE

    def _deliver(
        self, sim: state.SimState, robot: int, package_id: str, zone_id: str
    ) -> PackageOutcome:
        ready = self._ready(sim, robot, package_id)
        if isinstance(ready, PackageOutcome):
            return ready
        i, x, y = ready
        status, holder, pos, _ = self._arrays(sim)
        if status[i] != int(Status.HELD) or holder[i] != robot:
            return _fail("package not held by this robot")
        try:
            zone = self._world.zone(zone_id)
        except (KeyError, TypeError):
            return _fail("unknown zone")
        if zone.kind not in _DROP_KINDS or not point_in_polygon(x, y, zone.polygon):
            return _fail("not inside a delivery zone")
        status[i] = int(Status.DELIVERED)
        holder[i] = NO_HOLDER
        pos[i] = (x, y)
        return _DONE

    def _drop(self, sim: state.SimState, robot: int, package_id: str) -> PackageOutcome:
        ready = self._ready(sim, robot, package_id)
        if isinstance(ready, PackageOutcome):
            return ready
        i, x, y = ready
        status, holder, pos, _ = self._arrays(sim)
        if status[i] != int(Status.HELD) or holder[i] != robot:
            return _fail("package not held by this robot")
        if any(
            z.kind in _DROP_KINDS and point_in_polygon(x, y, z.polygon) for z in self._world.zones
        ):
            return _fail("inside a delivery zone, deliver instead")
        status[i] = int(Status.LOST)
        holder[i] = NO_HOLDER
        pos[i] = (x, y)
        return _DONE

    def _ready(
        self, sim: state.SimState, robot: int, package_id: str
    ) -> tuple[int, float, float] | PackageOutcome:
        """(package index, x, y) when the robot and the package are known, finite and slow."""
        if type(robot) is not int:
            return _fail("bad robot")
        if not isinstance(package_id, str) or package_id not in self._index:
            return _fail("unknown package")
        try:
            _, _, _, pose = self._arrays(sim)
            speed = _floats(sim.arrays["robot_speed"])
        except (KeyError, ValueError):
            return _fail("missing state")
        if not 0 <= robot < pose.shape[0] or speed.shape != (pose.shape[0],):
            return _fail("unknown robot")
        x, y, v = float(pose[robot, 0]), float(pose[robot, 1]), float(speed[robot])
        if not _finite(x, y, v):
            return _fail("non-finite robot value")
        if abs(v) > params.PACKAGE_SPEED_BOUND:
            return _fail("too fast")
        return self._index[package_id], x, y

    def _capacity_of(self, robot: int) -> int:
        return self._capacity[robot] if robot < len(self._capacity) else 0


def _ints(array: state.Array) -> NDArray[np.int64]:
    """The array itself when it is int64, else a ValueError (never a silent copy)."""
    if array.dtype != np.int64:
        raise ValueError(f"expected int64, got {array.dtype}")
    return cast(NDArray[np.int64], array)


def _floats(array: state.Array) -> NDArray[np.float64]:
    """The array itself when it is float64, else a ValueError (never a silent copy)."""
    if array.dtype != np.float64:
        raise ValueError(f"expected float64, got {array.dtype}")
    return cast(NDArray[np.float64], array)
