"""Ground-truth world model: map geometry and zones, with a JSON format and a strict loader.

Control never imports this module (contract ``control-no-ground-truth``). A malformed map is
rejected with WorldFormatError. Nothing is repaired or guessed.

JSON format (version 1)::

    {"version": 1, "name": "map_a", "bounds": [x0, y0, x1, y1],
     "walls": [polygon, ...], "racks": [polygon, ...],
     "zones": [{"id": "lane_1", "kind": "one_lane_aisle", "capacity": 1, "polygon": polygon}]}

A polygon is a list of at least three ``[x, y]`` points in meters, inside the bounds.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

FORMAT_VERSION = 1
ZONE_KINDS = frozenset(
    {"aisle", "one_lane_aisle", "blind_corner", "station", "depot", "transit", "hazard"}
)
_MIN_AREA = 1e-9
_TOP_FIELDS = {"version", "name", "bounds", "walls", "racks", "zones"}
_ZONE_FIELDS = {"id", "kind", "polygon", "capacity"}

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]


class WorldFormatError(ValueError):
    """The map file or mapping is malformed."""


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise WorldFormatError(f"{what} must be a number")
    if not math.isfinite(value):
        raise WorldFormatError(f"{what} must be finite")
    return float(value)


@dataclass(frozen=True)
class Polygon:
    """A simple polygon given by its vertices in order."""

    points: tuple[Point, ...]

    @classmethod
    def from_points(cls, points: Sequence[Sequence[float]]) -> "Polygon":
        """Build a polygon from at least three ``[x, y]`` pairs. Raises WorldFormatError."""
        if len(points) < 3:
            raise WorldFormatError("a polygon needs at least three points")
        parsed: list[Point] = []
        for point in points:
            if len(point) != 2:
                raise WorldFormatError("a point must be an [x, y] pair")
            parsed.append((_number(point[0], "x"), _number(point[1], "y")))
        polygon = cls(tuple(parsed))
        if polygon.area() < _MIN_AREA:
            raise WorldFormatError("a polygon must have an area above zero")
        return polygon

    def area(self) -> float:
        """Absolute area by the shoelace formula, in square meters."""
        total = 0.0
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:] + self.points[:1], strict=True):
            total += x0 * y1 - x1 * y0
        return abs(total) / 2.0


@dataclass(frozen=True)
class Zone:
    """A named region. ``capacity`` is the number of robots allowed at once, or None."""

    id: str
    kind: str
    polygon: Polygon
    capacity: int | None


@dataclass(frozen=True)
class World:
    """The static map."""

    name: str
    bounds: Bounds
    walls: tuple[Polygon, ...]
    racks: tuple[Polygon, ...]
    zones: tuple[Zone, ...]

    def zone(self, zone_id: str) -> Zone:
        """The zone with this id. Raises KeyError when there is none."""
        for zone in self.zones:
            if zone.id == zone_id:
                return zone
        raise KeyError(zone_id)


def _bounds(raw: object) -> Bounds:
    if not isinstance(raw, list) or len(raw) != 4:
        raise WorldFormatError("bounds must be [x0, y0, x1, y1]")
    x0, y0, x1, y1 = (_number(v, "bounds value") for v in raw)
    if x1 <= x0 or y1 <= y0:
        raise WorldFormatError("bounds must have x1 > x0 and y1 > y0")
    return (x0, y0, x1, y1)


def _polygon(raw: object, bounds: Bounds, what: str) -> Polygon:
    if not isinstance(raw, list):
        raise WorldFormatError(f"{what} must be a list of points")
    polygon = Polygon.from_points(raw)
    x0, y0, x1, y1 = bounds
    if any(not (x0 <= x <= x1 and y0 <= y <= y1) for x, y in polygon.points):
        raise WorldFormatError(f"{what} has a point outside the bounds")
    return polygon


def _polygons(raw: object, bounds: Bounds, what: str) -> tuple[Polygon, ...]:
    if not isinstance(raw, list):
        raise WorldFormatError(f"{what} must be a list")
    return tuple(_polygon(item, bounds, what) for item in raw)


def _zone(raw: object, bounds: Bounds) -> Zone:
    if not isinstance(raw, dict):
        raise WorldFormatError("a zone must be an object")
    unknown = set(raw) - _ZONE_FIELDS
    if unknown:
        raise WorldFormatError(f"unknown zone fields: {sorted(unknown)}")
    for key in ("id", "kind", "polygon"):
        if key not in raw:
            raise WorldFormatError(f"zone is missing {key}")
    zone_id, kind = raw["id"], raw["kind"]
    if not isinstance(zone_id, str) or not zone_id:
        raise WorldFormatError("zone id must be a non-empty string")
    if kind not in ZONE_KINDS:
        raise WorldFormatError(f"unknown zone kind: {kind!r}")
    capacity: int | None = None
    if "capacity" in raw:
        value = raw["capacity"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise WorldFormatError("capacity must be an integer of at least 1")
        capacity = value
    if kind == "one_lane_aisle" and capacity != 1:
        raise WorldFormatError("a one_lane_aisle must declare capacity 1")
    return Zone(zone_id, str(kind), _polygon(raw["polygon"], bounds, f"zone {zone_id}"), capacity)


def parse_world(data: object) -> World:
    """Validate a decoded JSON mapping and build the World. Raises WorldFormatError."""
    if not isinstance(data, Mapping):
        raise WorldFormatError("a world must be a JSON object")
    unknown = set(data) - _TOP_FIELDS
    if unknown:
        raise WorldFormatError(f"unknown fields: {sorted(unknown)}")
    for key in sorted(_TOP_FIELDS):
        if key not in data:
            raise WorldFormatError(f"missing field: {key}")
    if data["version"] != FORMAT_VERSION or isinstance(data["version"], bool):
        raise WorldFormatError(f"version must be {FORMAT_VERSION}")
    name = data["name"]
    if not isinstance(name, str) or not name:
        raise WorldFormatError("name must be a non-empty string")
    bounds = _bounds(data["bounds"])
    raw_zones = data["zones"]
    if not isinstance(raw_zones, list) or not raw_zones:
        raise WorldFormatError("zones must be a non-empty list")
    zones = tuple(_zone(z, bounds) for z in raw_zones)
    ids = [z.id for z in zones]
    if len(set(ids)) != len(ids):
        raise WorldFormatError("zone ids must be unique")
    return World(
        name=name,
        bounds=bounds,
        walls=_polygons(data["walls"], bounds, "wall"),
        racks=_polygons(data["racks"], bounds, "rack"),
        zones=zones,
    )


def load_world(path: Path) -> World:
    """Read a world from a JSON file. Raises WorldFormatError on any problem."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise WorldFormatError(f"could not read {path}: {err}") from err
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise WorldFormatError(f"{path} is not valid JSON: {err}") from err
    return parse_world(data)
