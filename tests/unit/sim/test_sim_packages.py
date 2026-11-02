"""The pure package model: transitions, preconditions, invariants, hash and fork isolation."""

import math

import numpy as np
import pytest

from waggle.sim import engine, packages, params, robots, scenarios
from waggle.sim.packages import PackageModel, PackageSpec, Status
from waggle.sim.params import RobotKind

ST = packages.Status
SPECS = (
    PackageSpec("pk-1", "station_1", 3.0, 21.5),
    PackageSpec("pk-2", "station_1", 4.0, 22.0),
    PackageSpec("pk-3", "depot_n", 31.0, 21.0),
)
AT_ONE = (3.0, 21.0)  # inside station_1, near pk-1
AT_THREE = (31.0, 21.0)  # inside depot_n, on pk-3
ELSEWHERE = (20.0, 2.0)  # corridor_s, no station


def _rig(
    kinds: tuple[RobotKind, ...] = (RobotKind.CARRIER, RobotKind.CARRIER),
    specs: tuple[PackageSpec, ...] = SPECS,
) -> tuple[engine.Engine, PackageModel]:
    box = scenarios.load_map("A")
    fleet = robots.RobotFleet(list(kinds))
    model = PackageModel(box, specs, [params.PACKAGE_CAPACITY[k] for k in kinds])
    poses = np.array([[AT_ONE[0], AT_ONE[1], 0.0], [AT_THREE[0], AT_THREE[1], 0.0]])
    poses = poses[: len(kinds)] if len(kinds) <= 2 else np.tile(poses[0], (len(kinds), 1))
    arrays = {**fleet.initial_arrays(poses), **model.initial_arrays()}
    return engine.Engine(7, arrays, [model.system(), fleet.system()], {}), model


def _put(sim: engine.Engine, robot: int, at: tuple[float, float], speed: float = 0.0) -> None:
    pose = sim.state.arrays["robot_pose"]
    pose[robot, 0], pose[robot, 1] = at
    sim.state.arrays["robot_speed"][robot] = speed


def _status(sim: engine.Engine) -> list[int]:
    return [int(v) for v in np.asarray(sim.state.arrays["pkg_status"])]


# ---------------------------------------------------------------- transitions


def test_a_package_starts_at_the_station_with_no_holder() -> None:
    sim, model = _rig()
    assert _status(sim) == [ST.AT_STATION] * 3
    assert np.asarray(sim.state.arrays["pkg_holder"]).tolist() == [-1, -1, -1]
    model.check_invariants(sim.state)


def test_pick_then_deliver_moves_the_package_through_its_states() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    assert _status(sim)[0] == ST.HELD
    assert np.asarray(sim.state.arrays["pkg_holder"])[0] == 0
    _put(sim, 0, (31.0, 21.0))
    out = model.deliver(sim.state, 2, 0, "pk-1", "depot_n")
    assert out.ok
    assert _status(sim)[0] == ST.DELIVERED
    assert np.asarray(sim.state.arrays["pkg_holder"])[0] == -1
    model.check_invariants(sim.state)


def test_a_held_package_follows_its_holder() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    _put(sim, 0, (10.0, 3.0))
    sim.step()
    assert np.asarray(sim.state.arrays["pkg_pos"])[0].tolist() == [10.0, 3.0]


def test_a_failed_holder_releases_its_packages_at_the_last_pose() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    _put(sim, 0, (10.0, 3.0))
    sim.step()
    model.release_holder(sim.state, 0)
    assert _status(sim)[0] == ST.AT_STATION
    assert np.asarray(sim.state.arrays["pkg_holder"])[0] == -1
    assert np.asarray(sim.state.arrays["pkg_pos"])[0].tolist() == [10.0, 3.0]
    model.check_invariants(sim.state)


def test_an_explicit_drop_outside_a_station_loses_the_package() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    _put(sim, 0, ELSEWHERE)
    assert model.drop(sim.state, 2, 0, "pk-1").ok
    assert _status(sim)[0] == ST.LOST
    model.check_invariants(sim.state)


def test_a_drop_inside_a_station_is_refused() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    assert not model.drop(sim.state, 2, 0, "pk-1").ok
    assert _status(sim)[0] == ST.HELD


@pytest.mark.parametrize("terminal", ["deliver", "drop"])
def test_delivered_and_lost_are_terminal(terminal: str) -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    if terminal == "deliver":
        _put(sim, 0, AT_THREE)
        assert model.deliver(sim.state, 2, 0, "pk-1", "depot_n").ok
    else:
        _put(sim, 0, ELSEWHERE)
        assert model.drop(sim.state, 2, 0, "pk-1").ok
    before = _status(sim)
    _put(sim, 0, AT_ONE)
    assert not model.pick(sim.state, 3, 0, "pk-1").ok
    assert not model.deliver(sim.state, 4, 0, "pk-1", "station_1").ok
    assert not model.drop(sim.state, 5, 0, "pk-1").ok
    model.release_holder(sim.state, 0)
    assert _status(sim) == before


# ---------------------------------------------------------------- preconditions


def test_two_picks_of_one_package_give_one_done_and_one_failed() -> None:
    sim, model = _rig()
    _put(sim, 1, AT_ONE)
    results = [model.pick(sim.state, 1, 0, "pk-1").ok, model.pick(sim.state, 2, 1, "pk-1").ok]
    assert results == [True, False]


def test_deliver_of_an_unpicked_package_fails() -> None:
    sim, model = _rig()
    assert not model.deliver(sim.state, 1, 0, "pk-1", "station_1").ok
    assert _status(sim)[0] == ST.AT_STATION


def test_only_the_holder_can_deliver() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    _put(sim, 1, AT_THREE)
    assert not model.deliver(sim.state, 2, 1, "pk-1", "depot_n").ok


def test_deliver_needs_a_station_or_depot_zone_and_the_pose_inside_it() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    assert not model.deliver(sim.state, 2, 0, "pk-1", "depot_n").ok  # robot is in station_1
    _put(sim, 0, (20.0, 2.0))
    assert not model.deliver(sim.state, 3, 0, "pk-1", "corridor_s").ok  # transit zone
    assert not model.deliver(sim.state, 4, 0, "pk-1", "no_such_zone").ok
    assert _status(sim)[0] == ST.HELD


def test_a_pick_far_from_the_package_fails() -> None:
    sim, model = _rig()
    _put(sim, 0, (7.5, 20.5))  # inside station_1, farther than the pick radius from pk-1
    assert not model.pick(sim.state, 1, 0, "pk-1").ok


def test_a_pick_above_the_speed_bound_fails() -> None:
    sim, model = _rig()
    _put(sim, 0, AT_ONE, speed=params.PACKAGE_SPEED_BOUND + 0.01)
    assert not model.pick(sim.state, 1, 0, "pk-1").ok
    _put(sim, 0, AT_ONE, speed=params.PACKAGE_SPEED_BOUND)
    assert model.pick(sim.state, 2, 0, "pk-1").ok


def test_a_pick_over_capacity_fails() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    assert params.PACKAGE_CAPACITY[RobotKind.CARRIER] == 1
    assert not model.pick(sim.state, 2, 0, "pk-2").ok
    assert _status(sim)[1] == ST.AT_STATION


def test_a_forklift_can_hold_more_than_a_carrier() -> None:
    sim, model = _rig(kinds=(RobotKind.FORKLIFT, RobotKind.CARRIER))
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    _put(sim, 0, (3.5, 21.5))  # within the radius of both packages
    assert model.pick(sim.state, 2, 0, "pk-2").ok


def test_fail_closed_on_bad_values() -> None:
    sim, model = _rig()
    pose = sim.state.arrays["robot_pose"]
    for bad in (math.nan, math.inf):
        pose[0, 0] = bad
        assert not model.pick(sim.state, 1, 0, "pk-1").ok
        pose[0, 0] = AT_ONE[0]
    sim.state.arrays["robot_speed"][0] = math.nan
    assert not model.pick(sim.state, 2, 0, "pk-1").ok
    sim.state.arrays["robot_speed"][0] = 0.0
    assert not model.pick(sim.state, 3, 0, "unknown").ok
    assert not model.pick(sim.state, 4, 9, "pk-1").ok
    assert not model.pick(sim.state, 5, -1, "pk-1").ok
    assert not model.pick(sim.state, 6, True, "pk-1").ok
    assert not model.pick(sim.state, 7, 0, 5).ok  # type: ignore[arg-type]
    assert _status(sim) == [ST.AT_STATION] * 3


def test_a_state_without_the_package_arrays_fails_closed() -> None:
    sim, model = _rig()
    del sim.state.arrays["pkg_status"]
    assert not model.pick(sim.state, 1, 0, "pk-1").ok


def test_a_replayed_order_id_changes_nothing_a_second_time() -> None:
    sim, model = _rig()
    first = model.pick(sim.state, 1, 0, "pk-1")
    again = model.pick(sim.state, 1, 0, "pk-1")
    assert first.ok and again.ok == first.ok
    model.release_holder(sim.state, 0)
    assert model.pick(sim.state, 1, 0, "pk-1").ok  # the cached outcome, no second pick
    assert _status(sim)[0] == ST.AT_STATION


# ---------------------------------------------------------------- construction


@pytest.mark.parametrize(
    "specs",
    [
        (PackageSpec("pk-1", "station_1", 3.0, 21.0), PackageSpec("pk-1", "station_1", 4.0, 21.0)),
        (PackageSpec("pk-1", "nowhere", 3.0, 21.0),),
        (PackageSpec("pk-1", "corridor_s", 3.0, 2.0),),  # not a station or depot
        (PackageSpec("pk-1", "station_1", 30.0, 2.0),),  # outside its zone
        (PackageSpec("pk-1", "station_1", math.nan, 21.0),),
        (PackageSpec("bad id", "station_1", 3.0, 21.0),),
        (PackageSpec("", "station_1", 3.0, 21.0),),
    ],
)
def test_bad_specs_are_refused(specs: tuple[PackageSpec, ...]) -> None:
    with pytest.raises(packages.PackageError):
        PackageModel(scenarios.load_map("A"), specs, [1])


def test_bad_capacities_are_refused() -> None:
    for caps in ([-1], [True], [1.5]):
        with pytest.raises(packages.PackageError):
            PackageModel(scenarios.load_map("A"), SPECS, caps)  # type: ignore[arg-type]


def test_no_packages_means_no_arrays() -> None:
    model = PackageModel(scenarios.load_map("A"), (), [1])
    assert model.initial_arrays() == {}


# ---------------------------------------------------------------- invariants


def test_the_invariant_check_catches_a_corrupted_state() -> None:
    sim, model = _rig()
    holder = sim.state.arrays["pkg_holder"]
    holder[0] = 1  # a holder on an AT_STATION package
    with pytest.raises(packages.PackageInvariantError):
        model.check_invariants(sim.state)
    holder[0] = -1
    sim.state.arrays["pkg_status"][0] = 9
    with pytest.raises(packages.PackageInvariantError):
        model.check_invariants(sim.state)
    sim.state.arrays["pkg_status"][0] = ST.AT_STATION
    sim.state.arrays["pkg_pos"][0, 0] = math.nan
    with pytest.raises(packages.PackageInvariantError):
        model.check_invariants(sim.state)


def _fuzz(seed: int) -> tuple[str, list[bool]]:
    sim, model = _rig(kinds=(RobotKind.CARRIER, RobotKind.FORKLIFT))
    rng = np.random.default_rng(seed)
    places = [AT_ONE, AT_THREE, ELSEWHERE, (3.5, 21.5)]
    names = ["pk-1", "pk-2", "pk-3", "ghost"]
    zones = ["station_1", "depot_n", "corridor_s", "x"]
    outcomes: list[bool] = []
    for order in range(300):
        robot = int(rng.integers(0, 2))
        _put(sim, robot, places[int(rng.integers(0, 4))], float(rng.choice([0.0, 0.05, 1.0])))
        name = names[int(rng.integers(0, 4))]
        tool = int(rng.integers(0, 4))
        if tool == 0:
            outcomes.append(model.pick(sim.state, order, robot, name).ok)
        elif tool == 1:
            zone = zones[int(rng.integers(0, 4))]
            outcomes.append(model.deliver(sim.state, order, robot, name, zone).ok)
        elif tool == 2:
            outcomes.append(model.drop(sim.state, order, robot, name).ok)
        else:
            model.release_holder(sim.state, robot)
        sim.step()
        model.check_invariants(sim.state)
        status = np.asarray(sim.state.arrays["pkg_status"])
        assert status.shape == (3,)  # conservation: the count never changes
        holder = np.asarray(sim.state.arrays["pkg_holder"])
        assert all(h == -1 for h, s in zip(holder, status, strict=True) if s != ST.HELD)
    return sim.state_hash(), outcomes


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_random_order_streams_keep_every_invariant_and_replay_equal(seed: int) -> None:
    assert _fuzz(seed) == _fuzz(seed)


def test_terminal_states_never_come_back_in_a_random_stream() -> None:
    sim, model = _rig(kinds=(RobotKind.FORKLIFT, RobotKind.FORKLIFT))
    rng = np.random.default_rng(11)
    terminal: set[int] = set()
    for order in range(400):
        robot = int(rng.integers(0, 2))
        _put(sim, robot, [AT_ONE, AT_THREE, ELSEWHERE][int(rng.integers(0, 3))])
        name = ["pk-1", "pk-2", "pk-3"][int(rng.integers(0, 3))]
        tool = int(rng.integers(0, 3))
        if tool == 0:
            model.pick(sim.state, order, robot, name)
        elif tool == 1:
            model.deliver(sim.state, order, robot, name, "depot_n")
        else:
            model.drop(sim.state, order, robot, name)
        status = _status(sim)
        for i in terminal:
            assert status[i] in (ST.DELIVERED, ST.LOST)
        terminal |= {i for i, s in enumerate(status) if s in (ST.DELIVERED, ST.LOST)}


# ---------------------------------------------------------------- hash, snapshot, fork


def test_package_arrays_are_in_the_canonical_hash() -> None:
    a, model_a = _rig()
    b, _ = _rig()
    assert a.state_hash() == b.state_hash()
    assert model_a.pick(a.state, 1, 0, "pk-1").ok
    assert a.state_hash() != b.state_hash()


def test_snapshot_and_fork_carry_the_package_state() -> None:
    sim, model = _rig()
    assert model.pick(sim.state, 1, 0, "pk-1").ok
    snap = sim.snapshot()
    restored = engine.Engine.from_snapshot(snap, sim.systems)
    assert restored.state_hash() == sim.state_hash()
    assert _status(restored)[0] == ST.HELD


def test_an_order_in_a_fork_does_not_change_the_live_arrays() -> None:
    sim, model = _rig()
    live = sim.state_hash()
    fork = sim.fork()
    assert model.pick(fork.state, 1, 0, "pk-1").ok
    assert _status(fork)[0] == ST.HELD
    assert sim.state_hash() == live
    assert _status(sim)[0] == ST.AT_STATION


def test_a_run_without_packages_has_the_hash_it_had_before() -> None:
    scenario = scenarios.generate("S01", 3)
    assert scenario.robots  # unchanged scenarios declare no packages and add no arrays
    sim, _ = scenarios.build_engine(scenario)
    assert not any(name.startswith("pkg_") for name in sim.state.arrays)


def test_status_codes_are_stable() -> None:
    assert [int(s) for s in Status] == [0, 1, 2, 3]
