"""Packages in a scenario: deterministic placement from the seed, format checks, engine wiring."""

import dataclasses
import json

import numpy as np
import pytest

from waggle.sim import packages, scenarios, world
from waggle.sim.packages import PackageError, PackageSpec

_KINDS = ("station", "depot")


def _only_transit() -> world.World:
    return world.parse_world(
        {
            "version": 1,
            "name": "flat",
            "bounds": [0, 0, 10, 10],
            "walls": [],
            "racks": [],
            "zones": [
                {"id": "t", "kind": "transit", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}
            ],
        }
    )


@pytest.mark.parametrize("map_name", ["A", "B"])
def test_placement_is_a_pure_function_of_the_seed(map_name: str) -> None:
    box = scenarios.load_map(map_name)
    first = packages.place_packages(box, 6, 42)
    assert first == packages.place_packages(box, 6, 42)
    assert first != packages.place_packages(box, 6, 43)
    assert len({s.package_id for s in first}) == 6


@pytest.mark.parametrize("seed", range(8))
def test_placed_packages_lie_inside_a_station_or_depot(seed: int) -> None:
    box = scenarios.load_map("A")
    for spec in packages.place_packages(box, 10, seed):
        zone = box.zone(spec.zone_id)
        assert zone.kind in _KINDS
        assert packages.point_in_polygon(spec.x, spec.y, zone.polygon)


def test_zero_packages_is_an_empty_tuple() -> None:
    assert packages.place_packages(scenarios.load_map("A"), 0, 1) == ()


@pytest.mark.parametrize("count", [-1, True, 1.5, 100000])
def test_a_bad_count_is_refused(count: int) -> None:
    with pytest.raises(PackageError):
        packages.place_packages(scenarios.load_map("A"), count, 1)


def test_a_world_with_no_station_or_depot_is_refused() -> None:
    with pytest.raises(PackageError, match="station or depot"):
        packages.place_packages(_only_transit(), 1, 1)
    with pytest.raises(PackageError):
        packages.place_packages(scenarios.load_map("A"), 1, -5)


def test_a_scenario_without_packages_serializes_as_before() -> None:
    scenario = scenarios.generate("S01", 3)
    assert scenario.packages == ()
    assert "packages" not in scenario.to_dict()
    assert scenarios.Scenario.from_dict(scenario.to_dict()) == scenario


def test_a_scenario_with_packages_round_trips_through_json() -> None:
    base = scenarios.generate("S01", 3)
    scenario = scenarios.with_packages(base, 4)
    assert len(scenario.packages) == 4
    again = scenarios.Scenario.from_dict(json.loads(json.dumps(scenario.to_dict())))
    assert again == scenario
    assert scenarios.with_packages(base, 4) == scenario  # deterministic


def test_from_dict_validates_the_packages_against_the_map() -> None:
    data = scenarios.with_packages(scenarios.generate("S01", 3), 1).to_dict()
    data["packages"][0]["zone_id"] = "corridor_s"  # a transit zone
    with pytest.raises(PackageError):
        scenarios.Scenario.from_dict(data)
    data["packages"][0]["zone_id"] = "station_1"
    data["packages"][0]["x"] = 30.0  # outside the station
    with pytest.raises(PackageError):
        scenarios.Scenario.from_dict(data)
    data["packages"].append(dict(data["packages"][0]))
    data["packages"][0]["x"] = 3.0
    data["packages"][1]["x"] = 3.0
    with pytest.raises(PackageError, match="duplicate"):
        scenarios.Scenario.from_dict(data)


def test_build_engine_adds_package_arrays_only_when_declared() -> None:
    plain = scenarios.generate("S01", 3)
    sim, _ = scenarios.build_engine(plain)
    assert not any(name.startswith("pkg_") for name in sim.state.arrays)
    with_pk = scenarios.with_packages(plain, 3)
    sim2, _ = scenarios.build_engine(with_pk)
    assert np.asarray(sim2.state.arrays["pkg_status"]).shape == (3,)
    assert np.asarray(sim2.state.arrays["pkg_pos"]).shape == (3, 2)


def test_a_scenario_with_packages_replays_to_the_same_hash_and_forks_cleanly() -> None:
    scenario = scenarios.with_packages(scenarios.generate("S01", 3), 3)
    runs = []
    for _ in range(2):
        sim, _ = scenarios.build_engine(scenario)
        sim.run(200)
        runs.append(sim.state_hash())
    assert runs[0] == runs[1]
    sim, _ = scenarios.build_engine(scenario)
    fork = sim.fork()
    model = scenarios.package_model(scenario)
    fork.state.arrays["pkg_status"][0] = int(packages.Status.LOST)
    assert model.status_of(sim.state, scenario.packages[0].package_id) is packages.Status.AT_STATION


def test_the_package_model_of_a_scenario_matches_its_robots() -> None:
    scenario = scenarios.with_packages(scenarios.generate("S01", 3), 2)
    model = scenarios.package_model(scenario)
    assert model.count == 2
    sim, _ = scenarios.build_engine(scenario)
    model.check_invariants(sim.state)


def test_with_packages_does_not_touch_other_fields() -> None:
    base = scenarios.generate("S05", 9)
    changed = scenarios.with_packages(base, 2)
    assert dataclasses.replace(changed, packages=()) == base
    assert PackageSpec in {type(s) for s in changed.packages}
