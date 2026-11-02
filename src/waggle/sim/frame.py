"""Versioned frame of the snapshot contract (docs/MULTIMODAL_AND_VIEWER_DESIGN.md, section 8).

``export_frame`` copies what the simulator holds at a tick into a plain JSON tree. It reads
only the engine, the run metadata and the views the caller passes, and it never changes the
state. No wall clock, no random and no file or network access: the same seed and scenario give
byte-identical frames for one schema version. Values the simulator does not own (speed limit
in force, mode, zone occupancy, machines, events) are passed in by the caller and are null or
empty when absent, never invented. The ``overlays`` object is present and empty in version 1.
The reader side (``parse_frame``) rejects unknown versions, unknown fields and oversize input.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from waggle.sim import params, state
from waggle.sim.engine import Engine
from waggle.sim.world import Polygon, World

SCHEMA_VERSION = 1
WORLD_SCHEMA_VERSION = 1
DECIMALS = state.HASH_DECIMALS
MAX_FRAME_BYTES = 262_144
MAX_STRING = 64
SOURCES = frozenset({"live", "replay"})
MODES = frozenset({"normal", "reduced", "stopped"})
EVENT_KINDS = frozenset({"stop", "geofence", "denial", "ticket"})

JsonObject = dict[str, Any]  # a JSON tree: nested dicts, lists, strings, numbers, booleans, null

_TOP = {
    "schema_version",
    "tick",
    "dt",
    "sim_time",
    "state_hash",
    "run",
    "robots",
    "humans",
    "zones",
    "machines",
    "overlays",
    "events",
}
_RUN = {"commit", "seed", "scenario_id", "source"}
_ROBOT = {"id", "x", "y", "heading", "active", "speed_limit", "mode"}
_ACTIVE = {"speed", "turn"}
_HUMAN = {"id", "x", "y", "heading"}
_ZONE = {"id", "polygon_id", "occupant", "token"}
_MACHINE = {"id", "state", "temperature", "severity"}
_EVENT = {"kind", "text"}


class FrameError(ValueError):
    """A frame is malformed, of an unknown version or over the size cap."""


class FrameTooLarge(FrameError):
    """An exported frame is over the size cap. It is refused, never truncated."""


@dataclass(frozen=True)
class RunInfo:
    """Run metadata: the commit is passed by the caller, never read here."""

    commit: str
    seed: int
    scenario_id: str
    source: str


@dataclass(frozen=True)
class ZoneView:
    """Trusted zone state. ``occupant`` None means unknown."""

    id: str
    polygon_id: str
    occupant: str | None
    token: int | None


@dataclass(frozen=True)
class MachineView:
    """Maintenance state of one machine."""

    id: str
    state: str
    temperature: float
    severity: int


@dataclass(frozen=True)
class FrameEvent:
    """A typed event since the last frame."""

    kind: str
    text: str


def _round(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("frame values must be finite")
    return round(float(value), DECIMALS) + 0.0


def _text(value: str, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING:
        raise ValueError(f"{what} is empty or too long (limit {MAX_STRING})")
    return value


def _run(run: RunInfo) -> JsonObject:
    if run.source not in SOURCES:
        raise ValueError("run source must be live or replay")
    if type(run.seed) is not int or run.seed < 0:
        raise ValueError("run seed must be a non-negative integer")
    return {
        "commit": _text(run.commit, "commit"),
        "seed": run.seed,
        "scenario_id": _text(run.scenario_id, "scenario_id"),
        "source": run.source,
    }


def _array(sim: Engine, name: str, width: int) -> np.ndarray[Any, np.dtype[np.float64]]:
    raw = sim.state.arrays.get(name)
    if raw is None:
        return np.zeros((0, width))
    return np.asarray(raw, dtype=np.float64).reshape(-1, width)


def _per_robot(values: Sequence[Any] | None, count: int, what: str) -> list[Any]:
    if values is None:
        return [None] * count
    if len(values) != count:
        raise ValueError(f"{what} needs one value per robot")
    return list(values)


def _robots(
    sim: Engine, limits: Sequence[float | None] | None, modes: Sequence[str | None] | None
) -> list[JsonObject]:
    pose = _array(sim, "robot_pose", 3)
    active = _array(sim, "robot_active", 2)
    count = len(pose)
    limit_list = _per_robot(limits, count, "speed_limits")
    mode_list = _per_robot(modes, count, "modes")
    out: list[JsonObject] = []
    for i in range(count):
        mode = mode_list[i]
        if mode is not None and mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        limit = limit_list[i]
        out.append(
            {
                "id": f"robot_{i}",
                "x": _round(pose[i, 0]),
                "y": _round(pose[i, 1]),
                "heading": _round(pose[i, 2]),
                "active": {
                    "speed": _round(active[i, 0]) if i < len(active) else 0.0,
                    "turn": _round(active[i, 1]) if i < len(active) else 0.0,
                },
                "speed_limit": None if limit is None else _round(limit),
                "mode": mode,
            }
        )
    return out


def _humans(sim: Engine) -> list[JsonObject]:
    pos = _array(sim, "human_pos", 2)
    heading = _array(sim, "human_heading", 1)
    return [
        {
            "id": f"human_{i}",
            "x": _round(pos[i, 0]),
            "y": _round(pos[i, 1]),
            "heading": _round(heading[i, 0]) if i < len(heading) else 0.0,
        }
        for i in range(len(pos))
    ]


def _zones(zones: Sequence[ZoneView]) -> list[JsonObject]:
    return [
        {
            "id": _text(z.id, "zone id"),
            "polygon_id": _text(z.polygon_id, "polygon id"),
            "occupant": None if z.occupant is None else _text(z.occupant, "occupant"),
            "token": z.token,
        }
        for z in zones
    ]


def _machines(machines: Sequence[MachineView]) -> list[JsonObject]:
    return [
        {
            "id": _text(m.id, "machine id"),
            "state": _text(m.state, "machine state"),
            "temperature": _round(m.temperature),
            "severity": int(m.severity),
        }
        for m in machines
    ]


def _events(events: Sequence[FrameEvent]) -> list[JsonObject]:
    out: list[JsonObject] = []
    for event in events:
        if event.kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind {event.kind!r}")
        out.append({"kind": event.kind, "text": _text(event.text, "event text")})
    return out


def encode_frame(frame: Mapping[str, Any]) -> str:
    """Canonical JSON text of a frame: sorted keys, no spaces, no NaN."""
    return json.dumps(frame, sort_keys=True, separators=(",", ":"), allow_nan=False)


def export_frame(
    sim: Engine,
    run: RunInfo,
    *,
    zones: Sequence[ZoneView] = (),
    machines: Sequence[MachineView] = (),
    events: Sequence[FrameEvent] = (),
    speed_limits: Sequence[float | None] | None = None,
    modes: Sequence[str | None] | None = None,
    max_bytes: int = MAX_FRAME_BYTES,
    schema_version: int = SCHEMA_VERSION,
) -> JsonObject:
    """The frame of the engine at its current tick. Raises FrameTooLarge over ``max_bytes``."""
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version {schema_version}")
    tick = sim.state.tick
    out: JsonObject = {
        "schema_version": SCHEMA_VERSION,
        "tick": tick,
        "dt": params.DT,
        "sim_time": _round(tick * params.DT),
        "state_hash": sim.state_hash(),
        "run": _run(run),
        "robots": _robots(sim, speed_limits, modes),
        "humans": _humans(sim),
        "zones": _zones(zones),
        "machines": _machines(machines),
        "overlays": {},
        "events": _events(events),
    }
    size = len(encode_frame(out).encode("utf-8"))
    if size > max_bytes:
        raise FrameTooLarge(f"frame of {size} bytes is over the cap of {max_bytes}")
    return out


# ---------------------------------------------------------------- reader


def _object(value: object, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FrameError(f"{what} must be an object")
    unknown = set(value) - fields
    if unknown:
        raise FrameError(f"unknown field in {what}: {sorted(unknown)[0]}")
    absent = fields - set(value)
    if absent:
        raise FrameError(f"missing field in {what}: {sorted(absent)[0]}")
    return value


def _check_list(value: object, fields: set[str], what: str) -> None:
    if not isinstance(value, list):
        raise FrameError(f"{what} must be a list")
    for item in value:
        entry = _object(item, fields, what)
        for key, field in entry.items():
            if isinstance(field, str) and len(field) > MAX_STRING:
                raise FrameError(f"{what}.{key} is too long")


def parse_frame(text: str, max_bytes: int = MAX_FRAME_BYTES) -> JsonObject:
    """Read a frame. Unknown versions, unknown fields and oversize input are rejected."""
    if len(text.encode("utf-8")) > max_bytes:
        raise FrameError("frame is too large")
    try:
        data = json.loads(text)
    except ValueError as error:
        raise FrameError("frame is not valid JSON") from error
    if isinstance(data, dict) and data.get("schema_version") != SCHEMA_VERSION:
        raise FrameError("unsupported schema version")
    top = _object(data, _TOP, "frame")
    _object(top["run"], _RUN, "run")
    _check_list(top["robots"], _ROBOT, "robots")
    for robot in top["robots"]:
        _object(robot["active"], _ACTIVE, "robots.active")
    _check_list(top["humans"], _HUMAN, "humans")
    _check_list(top["zones"], _ZONE, "zones")
    _check_list(top["machines"], _MACHINE, "machines")
    _check_list(top["events"], _EVENT, "events")
    if top["overlays"] != {}:
        raise FrameError("overlays must be empty in schema version 1")
    if type(top["tick"]) is not int or top["tick"] < 0:
        raise FrameError("tick must be a non-negative integer")
    if not isinstance(top["state_hash"], str) or len(top["state_hash"]) != 64:
        raise FrameError("state_hash must be a SHA-256 hex digest")
    return top


# ---------------------------------------------------------------- world message


def _polygon(polygon: Polygon) -> list[list[float]]:
    return [[_round(x), _round(y)] for x, y in polygon.points]


def world_hash(box: World) -> str:
    """SHA-256 of the canonical world payload (everything but the hash itself)."""
    payload = _world_payload(box)
    return hashlib.sha256(encode_frame(payload).encode("utf-8")).hexdigest()


def _world_payload(box: World) -> JsonObject:
    return {
        "schema_version": WORLD_SCHEMA_VERSION,
        "name": box.name,
        "bounds": [_round(v) for v in box.bounds],
        "walls": [_polygon(p) for p in box.walls],
        "racks": [_polygon(p) for p in box.racks],
        "zones": [
            {
                "id": z.id,
                "kind": z.kind,
                "capacity": z.capacity,
                "polygon": _polygon(z.polygon),
            }
            for z in box.zones
        ],
    }


def export_world(box: World) -> JsonObject:
    """The static world message, sent once, with its own version and hash."""
    return {**_world_payload(box), "hash": world_hash(box)}
