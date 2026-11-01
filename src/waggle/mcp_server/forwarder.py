"""Forwarder for the tools that already have a fenced backend (ADR-040).

``release_zone`` and ``get_task`` map onto the corridor and task repositories. The holder is the
authenticated robot id, never an argument. The tick and the occupancy evidence come from
injected trusted sources, never from the request. Every other tool raises ToolUnavailable until
its trusted backend exists, so the boundary returns an error result and nothing moves.
"""

from collections.abc import Mapping
from typing import Protocol

from waggle.coordination.corridors import CorridorResult, ZoneObservation, ZoneToken
from waggle.coordination.task_model import TaskRecord
from waggle.db.corridors import IdempotencyConflict
from waggle.db.inventory import PartStock, ReservationResult, UnknownPart
from waggle.mcp_server.identity import Identity


class ToolDenied(Exception):
    """The caller may not see or change this object. The message never says which case."""


class ToolUnavailable(Exception):
    """No trusted backend exists for this tool yet."""


class CorridorPort(Protocol):
    """The release operation of ``CorridorRepository``."""

    def release(
        self,
        holder: str,
        tokens: tuple[ZoneToken, ...],
        now_tick: int,
        observations: tuple[ZoneObservation, ...],
    ) -> CorridorResult:
        """Release a complete live bundle with current occupancy evidence."""
        ...


class TaskPort(Protocol):
    """The read operation of ``TaskRepository``."""

    def get(self, task_id: str) -> TaskRecord | None:
        """Return a committed snapshot or None."""
        ...


class InventoryPort(Protocol):
    """The catalog and reservation operations of ``InventoryRepository``."""

    def get(self, part_number: str) -> PartStock | None:
        """Counts for a catalog part, or None outside the catalog."""
        ...

    def reserve(self, key: str, part_number: str, quantity: int, holder: str) -> ReservationResult:
        """Reserve stock once per key."""
        ...


class TickSource(Protocol):
    """A trusted shared tick. It must not be derived from a request."""

    def now_tick(self) -> int:
        """Return the current tick, or raise."""
        ...


class OccupancySource(Protocol):
    """Trusted occupancy evidence. None occupants mean unknown, an empty tuple means clear."""

    def observe(self, zone_ids: tuple[str, ...], now_tick: int) -> tuple[ZoneObservation, ...]:
        """Return one observation per zone, or raise."""
        ...


class FencedForwarder:
    """Implements the ``Forwarder`` protocol of the boundary."""

    def __init__(
        self,
        corridors: CorridorPort,
        tasks: TaskPort,
        ticks: TickSource,
        occupancy: OccupancySource,
        inventory: InventoryPort | None = None,
    ) -> None:
        self._corridors = corridors
        self._tasks = tasks
        self._ticks = ticks
        self._occupancy = occupancy
        self._inventory = inventory

    def forward(
        self, identity: Identity, tool: str, args: Mapping[str, object], timeout_s: float
    ) -> Mapping[str, object]:
        """Run one validated call. ``timeout_s`` is enforced by the database timeouts."""
        if tool == "release_zone":
            return self._release_zone(identity, args)
        if tool == "get_task":
            return self._get_task(identity, args)
        if tool == "get_inventory" and self._inventory is not None:
            return self._get_inventory(self._inventory, args)
        if tool == "reserve_part" and self._inventory is not None:
            return self._reserve_part(self._inventory, identity, args)
        raise ToolUnavailable(tool)

    @staticmethod
    def _get_inventory(
        inventory: InventoryPort, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        part_number = str(args["part_number"])
        stock = inventory.get(part_number)
        if stock is None:
            raise ToolDenied("part not available")
        return {"part_number": part_number, "available": stock.available}

    @staticmethod
    def _reserve_part(
        inventory: InventoryPort, identity: Identity, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            result = inventory.reserve(
                str(args["idempotency_key"]),
                str(args["part_number"]),
                int(str(args["quantity"])),
                identity.robot_id,
            )
        except (UnknownPart, IdempotencyConflict):
            raise ToolDenied("reservation not available") from None
        return {"reserved": result.granted, "reason": result.reason}

    def _release_zone(self, identity: Identity, args: Mapping[str, object]) -> Mapping[str, object]:
        zone_id, token = str(args["zone_id"]), int(str(args["token"]))
        tick = self._ticks.now_tick()
        observations = self._occupancy.observe((zone_id,), tick)
        result = self._corridors.release(
            identity.robot_id, (ZoneToken(zone_id, token),), tick, observations
        )
        return {"released": result.granted, "reason": str(result.reason)}

    def _get_task(self, identity: Identity, args: Mapping[str, object]) -> Mapping[str, object]:
        record = self._tasks.get(str(args["task_id"]))
        if record is None or record.worker_id != identity.robot_id:
            raise ToolDenied("task not available")
        return {
            "task_id": record.task_id,
            "state": str(record.state),
            "attempt": record.attempt,
            "token": record.token,
            "expires_tick": record.expires_tick,
        }
