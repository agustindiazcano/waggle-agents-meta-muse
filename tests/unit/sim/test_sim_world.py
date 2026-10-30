"""waggle.sim.world: JSON world format, loader and rejection of malformed maps."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from waggle.sim import world

SQUARE = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]]


def good() -> dict[str, Any]:
    return {
        "version": 1,
        "name": "toy",
        "bounds": [0.0, 0.0, 30.0, 20.0],
        "walls": [[[0, 0], [30, 0], [30, 0.4], [0, 0.4]]],
        "racks": [[[5, 5], [15, 5], [15, 7], [5, 7]]],
        "zones": [
            {"id": "aisle_1", "kind": "aisle", "polygon": [[1, 1], [29, 1], [29, 4], [1, 4]]},
            {
                "id": "lane_1",
                "kind": "one_lane_aisle",
                "capacity": 1,
                "polygon": [[16, 8], [20, 8], [20, 18], [16, 18]],
            },
            {"id": "corner_1", "kind": "blind_corner", "polygon": [[21, 8], [24, 8], [24, 11]]},
            {"id": "st_1", "kind": "station", "polygon": [[2, 9], [4, 9], [4, 11], [2, 11]]},
            {"id": "depot_n", "kind": "depot", "polygon": [[25, 12], [28, 12], [28, 15], [25, 15]]},
        ],
    }


def test_parse_builds_a_world_with_all_features() -> None:
    w = world.parse_world(good())
    assert w.name == "toy"
    assert w.bounds == (0.0, 0.0, 30.0, 20.0)
    assert len(w.walls) == 1 and len(w.racks) == 1
    kinds = {z.kind for z in w.zones}
    assert kinds == {"aisle", "one_lane_aisle", "blind_corner", "station", "depot"}
    assert w.zone("lane_1").capacity == 1
    assert w.zone("aisle_1").capacity is None


def test_world_is_immutable() -> None:
    w = world.parse_world(good())
    with pytest.raises(AttributeError):
        w.name = "other"  # type: ignore[misc]


def test_load_world_reads_a_json_file(tmp_path: Path) -> None:
    path = tmp_path / "toy.json"
    path.write_text(json.dumps(good()), encoding="utf-8")
    assert world.load_world(path).name == "toy"


def test_load_world_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(world.WorldFormatError, match="JSON"):
        world.load_world(path)


def test_load_world_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(world.WorldFormatError, match="read"):
        world.load_world(tmp_path / "absent.json")


def mutated(change: Any) -> dict[str, Any]:
    data = copy.deepcopy(good())
    change(data)
    return data


MALFORMED: dict[str, Callable[[dict[str, Any]], Any]] = {
    "not an object": lambda d: [1, 2],
    "wrong version": lambda d: d.update(version=2),
    "missing name": lambda d: d.pop("name"),
    "empty name": lambda d: d.update(name=""),
    "unknown field": lambda d: d.update(turbo=True),
    "missing bounds": lambda d: d.pop("bounds"),
    "bounds wrong length": lambda d: d.update(bounds=[0, 0, 5]),
    "bounds inverted": lambda d: d.update(bounds=[10, 0, 0, 5]),
    "bounds not numbers": lambda d: d.update(bounds=["a", 0, 5, 5]),
    "wall with two points": lambda d: d["walls"].append([[0, 0], [1, 1]]),
    "wall with nan": lambda d: d["walls"].append([[0, 0], [1, 0], [float("nan"), 1]]),
    "wall with zero area": lambda d: d["walls"].append([[0, 0], [1, 1], [2, 2]]),
    "wall outside bounds": lambda d: d["walls"].append([[40, 0], [41, 0], [41, 1]]),
    "point not a pair": lambda d: d["racks"].append([[0, 0], [1, 0, 3], [1, 1]]),
    "duplicate zone id": lambda d: d["zones"].append(dict(d["zones"][0])),
    "unknown zone kind": lambda d: d["zones"][0].update(kind="swamp"),
    "zone without polygon": lambda d: d["zones"][0].pop("polygon"),
    "zone without id": lambda d: d["zones"][0].pop("id"),
    "one lane with capacity 2": lambda d: d["zones"][1].update(capacity=2),
    "one lane without capacity": lambda d: d["zones"][1].pop("capacity"),
    "capacity zero": lambda d: d["zones"][0].update(capacity=0),
    "capacity bool": lambda d: d["zones"][0].update(capacity=True),
    "zone unknown field": lambda d: d["zones"][0].update(color="red"),
    "no zones": lambda d: d.update(zones=[]),
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_loader_rejects_malformed_maps(name: str) -> None:
    data = good()
    result = MALFORMED[name](data)
    if name == "not an object":
        data = result
    with pytest.raises(world.WorldFormatError):
        world.parse_world(data)


def test_polygon_area_is_positive_for_either_winding() -> None:
    ccw = world.Polygon.from_points(SQUARE)
    cw = world.Polygon.from_points(list(reversed(SQUARE)))
    assert ccw.area() == pytest.approx(16.0)
    assert cw.area() == pytest.approx(16.0)
