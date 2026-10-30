"""Scenario format, S01 to S18, seeds, unavoidable flag, replay and the waypoint driver."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from waggle.sim import engine, params, robots, scenarios, scripted
from waggle.sim.params import RobotKind

ROOT = Path(__file__).resolve().parents[3]
IDS = [f"S{n:02d}" for n in range(1, 19)]
# sha256 of data/seeds.json as generated once from the master seed. The file is data and is
# never regenerated, so a stored hash is allowed (it is not a state-hash golden value).
SEEDS_SHA256 = "0d1ffe76f8a1a9d8663bef34dbbe58132505bf1406436e4120bfcccf6c9cf7af"


# ---------------------------------------------------------------- maps and catalog


def test_both_maps_load_and_map_a_has_a_one_lane_aisle() -> None:
    a, b = scenarios.load_map("A"), scenarios.load_map("B")
    assert a.name != b.name
    assert any(z.kind == "one_lane_aisle" and z.capacity == 1 for z in a.zones)
    assert any(z.kind == "blind_corner" for z in b.zones)
    with pytest.raises(ValueError):
        scenarios.load_map("C")


def test_the_catalog_is_s01_to_s18() -> None:
    assert scenarios.SCENARIO_IDS == IDS


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown scenario"):
        scenarios.generate("S19", 1)
    with pytest.raises(ValueError):
        scenarios.generate("S01", -1)


@pytest.mark.parametrize("sid", IDS)
def test_every_scenario_declares_its_target_layer_and_expected_outcome(sid: str) -> None:
    sc = scenarios.generate(sid, 12345)
    assert sc.id == sid and sc.seed == 12345
    assert sc.target_layer and sc.expected_outcome and sc.family
    assert sc.map_name in ("A", "B")
    assert sc.duration_ticks > 0 and len(sc.robots) >= 1
    assert sc.compound is None  # reserved for compound crisis templates
    assert sc.separation_margin > sc.near_miss_margin > 0


def test_density_scenarios_have_3_10_and_30_robots_on_maps_a_and_b() -> None:
    counts = {sid: len(scenarios.generate(sid, 1).robots) for sid in IDS[12:]}
    assert [counts[s] for s in IDS[12:15]] == [3, 10, 30]
    assert [counts[s] for s in IDS[15:]] == [3, 10, 30]
    assert {scenarios.generate(s, 1).map_name for s in IDS[12:15]} == {"A"}
    assert {scenarios.generate(s, 1).map_name for s in IDS[15:]} == {"B"}


@pytest.mark.parametrize("sid", IDS)
def test_generation_is_deterministic_and_round_trips_through_json(sid: str) -> None:
    first, second = scenarios.generate(sid, 77), scenarios.generate(sid, 77)
    assert first == second
    text = json.dumps(first.to_dict())
    assert scenarios.Scenario.from_dict(json.loads(text)) == first


def test_the_seed_changes_the_adversarial_timing() -> None:
    starts = {scenarios.generate("S07", s).humans[0].plan.start_tick for s in range(1, 12)}
    assert len(starts) > 5


def test_robots_start_inside_the_map_without_overlapping_each_other() -> None:
    for sid in IDS[12:]:
        sc = scenarios.generate(sid, 5)
        box = scenarios.load_map(sc.map_name)
        x0, y0, x1, y1 = box.bounds
        centers = np.array([[r.pose[0], r.pose[1]] for r in sc.robots])
        assert np.all((centers[:, 0] > x0) & (centers[:, 0] < x1))
        assert np.all((centers[:, 1] > y0) & (centers[:, 1] < y1))
        gaps = np.hypot(*(centers[:, None, :] - centers[None, :, :]).transpose(2, 0, 1))
        np.fill_diagonal(gaps, np.inf)
        assert gaps.min() > 1.0


# ---------------------------------------------------------------- unavoidable at spawn


def test_unavoidable_when_a_human_spawns_inside_the_stopping_distance_at_the_speed_cap() -> None:
    carrier = params.ROBOT_PARAMS[RobotKind.CARRIER]
    assert scenarios.unavoidable_at_spawn([(0.0, 0.0)], [carrier], [(1.5, 0.0)], 0.3)
    assert not scenarios.unavoidable_at_spawn([(0.0, 0.0)], [carrier], [(3.0, 0.0)], 0.3)


def test_unavoidable_is_checked_for_every_pair_and_with_the_class_stopping_distance() -> None:
    carrier = params.ROBOT_PARAMS[RobotKind.CARRIER]
    forklift = params.ROBOT_PARAMS[RobotKind.FORKLIFT]
    starts = [(0.0, 0.0), (20.0, 0.0)]
    assert scenarios.unavoidable_at_spawn(starts, [carrier, forklift], [(20.0, 2.0)], 0.3)
    assert not scenarios.unavoidable_at_spawn(starts, [carrier, forklift], [(10.0, 10.0)], 0.3)
    assert not scenarios.unavoidable_at_spawn(starts, [carrier, forklift], [], 0.3)


def test_generated_scenarios_flag_is_computed_from_geometry() -> None:
    for sid in IDS:
        sc = scenarios.generate(sid, 3)
        recomputed = scenarios.unavoidable_at_spawn(
            [(r.pose[0], r.pose[1]) for r in sc.robots],
            [params.ROBOT_PARAMS[r.kind] for r in sc.robots],
            [h.start for h in sc.humans],
            params.HUMAN_RADIUS,
        )
        assert sc.unavoidable_at_spawn == recomputed


# ---------------------------------------------------------------- seeds


def test_seed_split_has_5_dev_and_12_heldout_per_scenario_and_is_disjoint() -> None:
    data = scenarios.generate_seeds(20261027)
    assert set(data["dev"]) == set(IDS) == set(data["heldout"])
    assert all(len(v) == 5 for v in data["dev"].values())
    assert all(len(v) == 12 for v in data["heldout"].values())
    dev = {s for v in data["dev"].values() for s in v}
    held = {s for v in data["heldout"].values() for s in v}
    assert len(dev) == 90 and len(held) == 216 and not dev & held


def test_seed_generation_is_deterministic_by_master_seed() -> None:
    assert scenarios.generate_seeds(1) == scenarios.generate_seeds(1)
    assert scenarios.generate_seeds(1) != scenarios.generate_seeds(2)


def test_the_stored_seed_file_is_complete_disjoint_and_unchanged() -> None:
    path = ROOT / "data" / "seeds.json"
    raw = path.read_bytes()
    data = json.loads(raw)
    assert data == scenarios.generate_seeds(data["master_seed"])
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == SEEDS_SHA256


def test_writing_seeds_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "seeds.json"
    assert scenarios.write_seeds_once(path, 1) is True
    before = path.read_bytes()
    assert scenarios.write_seeds_once(path, 2) is False
    assert path.read_bytes() == before


# ---------------------------------------------------------------- waypoint driver


def test_the_driver_follows_waypoints_and_counts_tasks_without_any_safety_logic() -> None:
    fleet = robots.RobotFleet([RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[(10.0, 0.0), (0.0, 0.0)]], loop=True)
    arrays = {**fleet.initial_arrays(np.zeros((1, 3))), **driver.initial_arrays()}
    sim = engine.Engine(1, arrays, [driver.system(), fleet.system()], {})
    sim.run(40 * 20)
    tasks = int(np.asarray(sim.state.arrays["script_tasks"])[0])
    assert tasks >= 2


def test_a_one_shot_route_stops_at_the_last_waypoint() -> None:
    fleet = robots.RobotFleet([RobotKind.CARRIER])
    driver = scripted.WaypointDriver(fleet, [[(8.0, 0.0)]], loop=False)
    arrays = {**fleet.initial_arrays(np.zeros((1, 3))), **driver.initial_arrays()}
    sim = engine.Engine(1, arrays, [driver.system(), fleet.system()], {})
    sim.run(40 * 30)
    pose = np.asarray(sim.state.arrays["robot_pose"])[0]
    assert abs(pose[0] - 8.0) < 1.5 and np.asarray(sim.state.arrays["robot_speed"])[0] == 0.0


def test_a_forklift_reaches_a_waypoint_with_its_turning_radius() -> None:
    fleet = robots.RobotFleet([RobotKind.FORKLIFT])
    driver = scripted.WaypointDriver(fleet, [[(12.0, 6.0)]], loop=False)
    arrays = {**fleet.initial_arrays(np.zeros((1, 3))), **driver.initial_arrays()}
    sim = engine.Engine(1, arrays, [driver.system(), fleet.system()], {})
    sim.run(40 * 60)
    pose = np.asarray(sim.state.arrays["robot_pose"])[0]
    assert np.hypot(pose[0] - 12.0, pose[1] - 6.0) < 1.5


# ---------------------------------------------------------------- replay


def test_replay_by_seed_reproduces_the_per_tick_hash() -> None:
    sc = scenarios.generate("S03", 4242)
    first = scenarios.run_scenario(sc, ticks=200)
    again = scenarios.run_scenario(scenarios.generate("S03", 4242), ticks=200)
    assert first.hashes == again.hashes and len(first.hashes) == 200
    assert first.counts == again.counts


def test_a_walker_scenario_differs_by_seed_and_replays_by_seed() -> None:
    a = scenarios.run_scenario(scenarios.generate("S13", 1), ticks=120)
    b = scenarios.run_scenario(scenarios.generate("S13", 2), ticks=120)
    c = scenarios.run_scenario(scenarios.generate("S13", 1), ticks=120)
    assert a.hashes == c.hashes and a.hashes != b.hashes


def test_the_one_lane_scenario_collides_without_control() -> None:
    record = scenarios.run_scenario(scenarios.generate("S03", 1))
    assert record.counts["robot_collisions"] >= 1


def test_run_record_carries_counts_and_tasks() -> None:
    record = scenarios.run_scenario(scenarios.generate("S13", 1), ticks=80)
    assert set(record.counts) == {
        "human_collisions",
        "robot_collisions",
        "separation_violations",
        "near_misses",
    }
    assert record.ticks == 80 and record.tasks_completed >= 0


def test_a_raised_load_forklift_scenario_times_the_human_with_the_reduced_speed() -> None:
    """S05 is S01 with the load raised: the robot is slower, so the human must start later."""
    for seed in (1, 2, 3):
        plain, raised = scenarios.generate("S01", seed), scenarios.generate("S05", seed)
        assert raised.robots[0].load_raised and not plain.robots[0].load_raised
        assert raised.humans[0].plan.start_tick > plain.humans[0].plan.start_tick
        assert raised.robots[0].initial_speed == pytest.approx(
            plain.robots[0].initial_speed * params.LOAD_RAISED_SPEED_FACTOR
        )
