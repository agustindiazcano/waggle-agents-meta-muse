"""PostgreSQL motion order queue (ADR-050).

The MCP server does not move robots. A motion tool call that passes every check becomes a
pending row here, and the simulator bridge (the only owner of ground truth) consumes it and
reports the outcome. Checks run in one transaction: the task must be live and owned by the
caller, and a delivery needs a live lease on the zone held by the caller. A robot has at most one
pending order, so an unexecuted order cannot be buried under later ones.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Literal, cast

import psycopg

from waggle.db.connection import Database, Row

_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_TOOLS = ("move_waypoint", "pick_package", "deliver_package")
_TICK_MAX = 2**62
_LIST_MAX = 1000


class MotionRefused(Exception):
    """The call may not queue an order. ``reason`` is for audit and tests, not for the caller."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _id(value: object, what: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"invalid {what}")
    return value


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"invalid {what}")
    return float(value)


def _tick(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _TICK_MAX:
        raise ValueError("tick must be a nonnegative bounded integer")
    return value


@dataclass(frozen=True)
class NewOrder:
    """One validated motion request. Which fields are set depends on the tool."""

    tool: str
    task_id: str
    x: float | None = None
    y: float | None = None
    speed: float | None = None
    package_id: str | None = None
    zone_id: str | None = None

    def __post_init__(self) -> None:
        if self.tool not in _TOOLS:
            raise ValueError("unknown motion tool")
        _id(self.task_id, "task id")
        move = (self.x, self.y, self.speed)
        if self.tool == "move_waypoint":
            if None in move or self.package_id is not None or self.zone_id is not None:
                raise ValueError("move_waypoint takes x, y and speed only")
            _number(self.x, "x")
            _number(self.y, "y")
            if _number(self.speed, "speed") <= 0:
                raise ValueError("invalid speed")
            return
        if any(v is not None for v in move) or self.package_id is None:
            raise ValueError("a package tool takes a package id only")
        _id(self.package_id, "package id")
        if self.tool == "pick_package":
            if self.zone_id is not None:
                raise ValueError("pick_package takes no zone")
        else:
            _id(self.zone_id, "zone id")

    def signature(self) -> str:
        """Digest of every field, to tell a retry from a different order."""
        fields = [self.tool, self.task_id, self.x, self.y, self.speed, self.package_id]
        fields.append(self.zone_id)
        return hashlib.sha256(json.dumps(fields, allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EnqueueResult:
    """A busy robot is a result, not an error."""

    queued: bool
    reason: Literal["queued", "replayed", "busy"]
    order_id: int | None


@dataclass(frozen=True)
class MotionOrder:
    """A pending order as the simulator bridge reads it."""

    order_id: int
    robot_id: str
    order: NewOrder
    created_tick: int


class MotionOrderRepository:
    """Queue orders for the simulator bridge and record what it did with them."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def enqueue(self, robot_id: str, order: NewOrder, now_tick: int) -> EnqueueResult:
        """Queue one order for ``robot_id`` or raise MotionRefused."""
        _id(robot_id, "robot id")
        _tick(now_tick)
        signature = order.signature()
        with self._database.transaction() as connection:
            self._check_task(connection, robot_id, order.task_id, now_tick)
            if order.tool == "deliver_package":
                self._check_zone(connection, robot_id, cast(str, order.zone_id), now_tick)
            decided = self._decide(connection, robot_id, signature)
            if decided is not None:
                return decided
            row = connection.execute(
                "INSERT INTO motion_orders (robot_id, task_id, tool, x, y, speed, package_id, "
                "zone_id, signature, created_tick) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (robot_id) WHERE status='pending' DO NOTHING RETURNING order_id",
                (
                    robot_id,
                    order.task_id,
                    order.tool,
                    order.x,
                    order.y,
                    order.speed,
                    order.package_id,
                    order.zone_id,
                    signature,
                    now_tick,
                ),
            ).fetchone()
            if row is not None:
                return EnqueueResult(True, "queued", cast(int, row[0]))
            return self._decide(connection, robot_id, signature) or EnqueueResult(
                False, "busy", None
            )

    @staticmethod
    def _check_task(
        connection: psycopg.Connection[Row], robot_id: str, task_id: str, now_tick: int
    ) -> None:
        row = connection.execute(
            "SELECT state, worker_id, expires_tick FROM tasks WHERE task_id=%s FOR SHARE",
            (task_id,),
        ).fetchone()
        if row is None:
            raise MotionRefused("no_task")
        if row[1] != robot_id:
            raise MotionRefused("not_your_task")
        if (
            row[0] not in ("ASSIGNED", "EXECUTING")
            or row[2] is None
            or cast(int, row[2]) <= now_tick
        ):
            raise MotionRefused("task_not_live")

    @staticmethod
    def _check_zone(
        connection: psycopg.Connection[Row], robot_id: str, zone_id: str, now_tick: int
    ) -> None:
        row = connection.execute(
            "SELECT holder, expires_tick FROM zones WHERE zone_id=%s FOR SHARE", (zone_id,)
        ).fetchone()
        if row is None:
            raise MotionRefused("unknown_zone")
        if row[0] != robot_id or row[1] is None or cast(int, row[1]) <= now_tick:
            raise MotionRefused("zone_not_held")

    @staticmethod
    def _decide(
        connection: psycopg.Connection[Row], robot_id: str, signature: str
    ) -> EnqueueResult | None:
        row = connection.execute(
            "SELECT order_id, signature FROM motion_orders WHERE robot_id=%s AND status='pending'",
            (robot_id,),
        ).fetchone()
        if row is None:
            return None
        if row[1] == signature:
            return EnqueueResult(True, "replayed", cast(int, row[0]))
        return EnqueueResult(False, "busy", None)

    def pending(self, limit: int = 100) -> tuple[MotionOrder, ...]:
        """Pending orders, oldest first."""
        if type(limit) is not int or not 1 <= limit <= _LIST_MAX:
            raise ValueError("invalid limit")
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT order_id, robot_id, task_id, tool, x, y, speed, package_id, zone_id, "
                "created_tick FROM motion_orders WHERE status='pending' ORDER BY order_id LIMIT %s",
                (limit,),
            ).fetchall()
        # Column types and constraints fix the row types.
        return tuple(
            MotionOrder(
                cast(int, r[0]),
                cast(str, r[1]),
                NewOrder(
                    cast(str, r[3]),
                    cast(str, r[2]),
                    cast("float | None", r[4]),
                    cast("float | None", r[5]),
                    cast("float | None", r[6]),
                    cast("str | None", r[7]),
                    cast("str | None", r[8]),
                ),
                cast(int, r[9]),
            )
            for r in rows
        )

    def resolve(self, order_id: int, outcome: Literal["done", "failed"], now_tick: int) -> bool:
        """Record the bridge outcome. False when the order is unknown or already resolved."""
        if type(order_id) is not int or order_id < 1:
            raise ValueError("invalid order id")
        if outcome not in ("done", "failed"):
            raise ValueError("invalid outcome")
        _tick(now_tick)
        with self._database.transaction() as connection:
            row = connection.execute(
                "UPDATE motion_orders SET status=%s, resolved_tick=%s, "
                "resolved_at=clock_timestamp() WHERE order_id=%s AND status='pending' "
                "RETURNING order_id",
                (outcome, now_tick, order_id),
            ).fetchone()
        return row is not None
