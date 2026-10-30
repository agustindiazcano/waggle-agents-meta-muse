"""Humans: scripted paths, seeded walkers, adversarial timing and hidden-human sampling."""

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from waggle.sim import engine, humans, params, robots, streams, world
from waggle.sim.params import DT, HUMAN_RADIUS, HUMAN_WALK_SPEED, RobotKind

Floats = NDArray[np.float64]


def small_world() -> world.World:
    return world.parse_world(
        {
            "version": 1,
            "name": "box",
            "bounds": [0.0, 0.0, 20.0, 20.0],
            "walls": [[[9.0, 0.0], [10.0, 0.0], [10.0, 12.0], [9.0, 12.0]]],
            "racks": [[[2.0, 14.0], [8.0, 14.0], [8.0, 16.0], [2.0, 16.0]]],
            "zones": [{"id": "a", "kind": "aisle", "polygon": [[0, 0], [20, 0], [20, 3], [0, 3]]}],
        }
    )


def f64(sim: engine.Engine, name: str) -> Floats:
    return np.asarray(sim.state.arrays[name], dtype=np.float64)


def make(
    seed: int,
    plans: list[humans.HumanPlan],
    box: world.World | None = None,
    starts: list[tuple[float, float]] | None = None,
) -> engine.Engine:
    crowd = humans.Crowd(plans, box)
    arrays = crowd.initial_arrays(np.array(starts or [(5.0, 5.0)] * len(plans), dtype=np.float64))
    return engine.Engine(seed, arrays, [crowd.system()], {"humans": len(plans)})


# ---------------------------------------------------------------- scripted paths


PATH = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]


def test_path_position_is_exact_on_each_leg_and_stops_at_the_end() -> None:
    assert humans.path_position(PATH, 1.0, 0.0) == pytest.approx((0.0, 0.0))
    assert humans.path_position(PATH, 1.0, 5.0) == pytest.approx((5.0, 0.0))
    assert humans.path_position(PATH, 1.0, 10.0) == pytest.approx((10.0, 0.0))
    assert humans.path_position(PATH, 1.0, 14.0) == pytest.approx((10.0, 4.0))
    assert humans.path_position(PATH, 1.0, 500.0) == pytest.approx((10.0, 10.0))


def test_path_position_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        humans.path_position([(0.0, 0.0)], 1.0, 1.0)
    with pytest.raises(ValueError):
        humans.path_position(PATH, 0.0, 1.0)
    with pytest.raises(ValueError):
        humans.path_position(PATH, 1.0, -1.0)


def test_scripted_human_follows_the_path_and_reproduces_exactly() -> None:
    plan = humans.HumanPlan.scripted(PATH, speed=1.0, start_tick=40)
    hashes = []
    for _ in range(2):
        sim = make(3, [plan], starts=[(0.0, 0.0)])
        sim.run(40 + 200)
        assert f64(sim, "human_pos")[0].tolist() == pytest.approx([5.0, 0.0], abs=1e-9)
        hashes.append(sim.state_hash())
    assert hashes[0] == hashes[1]


def test_scripted_human_waits_until_its_start_tick() -> None:
    plan = humans.HumanPlan.scripted(PATH, speed=1.0, start_tick=100)
    sim = make(1, [plan], starts=[(0.0, 0.0)])
    sim.run(100)
    assert f64(sim, "human_pos")[0].tolist() == [0.0, 0.0]
    sim.run(40)
    assert f64(sim, "human_pos")[0, 0] == pytest.approx(1.0)


def test_scripted_humans_do_not_use_the_random_streams() -> None:
    plan = humans.HumanPlan.scripted(PATH, speed=1.0)
    a, b = make(1, [plan], starts=[(0.0, 0.0)]), make(999, [plan], starts=[(0.0, 0.0)])
    a.run(300)
    b.run(300)
    assert f64(a, "human_pos").tolist() == f64(b, "human_pos").tolist()


# ---------------------------------------------------------------- random walkers


def test_walkers_are_deterministic_by_seed_and_differ_across_seeds() -> None:
    plans = [humans.HumanPlan.walker(speed=1.2, turn_sigma=0.4) for _ in range(3)]
    a, b, c = make(5, plans), make(5, plans), make(6, plans)
    for sim in (a, b, c):
        sim.run(400)
    assert a.state_hash() == b.state_hash()
    assert a.state_hash() != c.state_hash()


def test_adding_a_walker_does_not_change_the_others() -> None:
    three = [humans.HumanPlan.walker(speed=1.2, turn_sigma=0.4) for _ in range(3)]
    four = [*three, humans.HumanPlan.walker(speed=1.2, turn_sigma=0.4)]
    a, b = make(8, three), make(8, four)
    a.run(300)
    b.run(300)
    assert f64(a, "human_pos").tolist() == f64(b, "human_pos")[:3].tolist()


def circle_hits(box: world.World, x: float, y: float, radius: float) -> bool:
    return humans.hits_obstacle(box, np.array([x, y]), radius)


def test_walkers_never_overlap_walls_racks_or_leave_the_bounds() -> None:
    box = small_world()
    plans = [humans.HumanPlan.walker(speed=1.4, turn_sigma=0.8) for _ in range(6)]
    starts = [(5.0, 5.0), (12.0, 5.0), (15.0, 15.0), (5.0, 11.0), (12.0, 17.0), (2.0, 2.0)]
    sim = make(21, plans, box, starts)
    for _ in range(3000):
        sim.step()
        for x, y in f64(sim, "human_pos"):
            assert x - HUMAN_RADIUS >= 0.0 and x + HUMAN_RADIUS <= 20.0
            assert y - HUMAN_RADIUS >= 0.0 and y + HUMAN_RADIUS <= 20.0
            assert not circle_hits(box, float(x), float(y), HUMAN_RADIUS)


def test_a_walker_moves_at_its_speed_when_free() -> None:
    sim = make(2, [humans.HumanPlan.walker(speed=1.0, turn_sigma=0.0)], small_world(), [(15, 15)])
    sim.run(40)
    moved = float(np.hypot(*(f64(sim, "human_pos")[0] - np.array([15.0, 15.0]))))
    assert moved == pytest.approx(1.0, abs=0.05)


def test_hits_obstacle_detects_walls_racks_and_bounds() -> None:
    box = small_world()
    assert circle_hits(box, 9.5, 5.0, HUMAN_RADIUS)  # inside the wall
    assert circle_hits(box, 8.8, 5.0, HUMAN_RADIUS)  # touches the wall
    assert circle_hits(box, 5.0, 15.0, HUMAN_RADIUS)  # inside the rack
    assert circle_hits(box, 0.1, 5.0, HUMAN_RADIUS)  # leaves the bounds
    assert not circle_hits(box, 5.0, 5.0, HUMAN_RADIUS)


# ---------------------------------------------------------------- adversarial timing


@pytest.mark.parametrize("kind", list(RobotKind))
def test_stop_distance_comes_from_the_declared_robot_parameters(kind: RobotKind) -> None:
    p = params.ROBOT_PARAMS[kind]
    expected = p.max_speed * p.delay_ticks * DT + p.max_speed**2 / (2 * p.decel)
    assert humans.max_speed_stop_distance(p) == pytest.approx(expected)


def test_fraction_is_drawn_from_the_seed_inside_the_documented_range() -> None:
    lo, hi = humans.ADVERSARIAL_FRACTION_RANGE
    drawn = [humans.draw_fraction(streams.make_streams(s, "scenario", 1)[0]) for s in range(30)]
    assert all(lo <= f <= hi for f in drawn)
    assert len(set(drawn)) > 20
    again = humans.draw_fraction(streams.make_streams(4, "scenario", 1)[0])
    assert again == drawn[4]


@pytest.mark.parametrize("kind", list(RobotKind))
@pytest.mark.parametrize("fraction", [0.4, 1.0, 1.3])
def test_adversarial_human_reaches_the_crossing_when_the_robot_is_at_the_set_distance(
    kind: RobotKind, fraction: float
) -> None:
    p = params.ROBOT_PARAMS[kind]
    crossing_distance = 30.0  # robot start to the crossing point, along +x
    human_start = (crossing_distance, -6.0)
    plan = humans.adversarial_crossing(
        p,
        fraction=fraction,
        crossing=(crossing_distance, 0.0),
        robot_start=(0.0, 0.0),
        human_start=human_start,
        human_speed=HUMAN_WALK_SPEED,
    )
    fleet = robots.RobotFleet([kind])
    crowd = humans.Crowd([plan], None)
    arrays = {
        **fleet.initial_arrays(np.zeros((1, 3)), np.array([p.max_speed])),
        **crowd.initial_arrays(np.array([human_start])),
    }
    sim = engine.Engine(1, arrays, [fleet.system(), crowd.system()], {"humans": 1})
    f64(sim, "robot_active")[0] = (p.max_speed, 0.0)
    reach_tick = None
    for _ in range(4000):
        sim.step()
        pos = f64(sim, "human_pos")[0]
        if reach_tick is None and pos[1] >= 0.0:
            reach_tick = sim.state.tick
            gap = crossing_distance - float(f64(sim, "robot_pose")[0, 0])
            target = fraction * humans.max_speed_stop_distance(p)
            assert abs(gap - target) <= p.max_speed * DT * 2 + 1e-6
    assert reach_tick is not None


def test_adversarial_plan_depends_only_on_robot_parameters() -> None:
    p = params.ROBOT_PARAMS[RobotKind.CARRIER]
    kwargs = {
        "fraction": 0.8,
        "crossing": (30.0, 0.0),
        "robot_start": (0.0, 0.0),
        "human_start": (30.0, -6.0),
        "human_speed": 1.4,
    }
    first = humans.adversarial_crossing(p, **kwargs)  # type: ignore[arg-type]
    second = humans.adversarial_crossing(p, **kwargs)  # type: ignore[arg-type]
    assert first == second


def test_adversarial_timing_that_would_start_in_the_past_is_rejected() -> None:
    p = params.ROBOT_PARAMS[RobotKind.FORKLIFT]
    with pytest.raises(ValueError, match="before the run starts"):
        humans.adversarial_crossing(
            p,
            fraction=1.0,
            crossing=(2.0, 0.0),
            robot_start=(0.0, 0.0),
            human_start=(2.0, -20.0),
            human_speed=1.4,
        )


def test_the_three_adversarial_kinds_build_scripted_plans() -> None:
    p = params.ROBOT_PARAMS[RobotKind.CARRIER]
    common = {
        "fraction": 0.9,
        "crossing": (30.0, 0.0),
        "robot_start": (0.0, 0.0),
        "human_start": (30.0, -6.0),
        "human_speed": 1.4,
    }
    corner = humans.adversarial_step_out(p, **common)  # type: ignore[arg-type]
    cross = humans.adversarial_crossing(p, **common)  # type: ignore[arg-type]
    stop = humans.adversarial_stop_in_aisle(p, **common)  # type: ignore[arg-type]
    for plan in (corner, cross, stop):
        assert plan.kind == "scripted"
    assert stop.path[-1] == (30.0, 0.0)
    assert cross.path[-1][1] > 0.0  # keeps walking across
    assert corner.path[-1][1] > 0.0


# ---------------------------------------------------------------- hidden human variants


REGION = world.Polygon.from_points([(20.0, 0.0), (30.0, 0.0), (30.0, 6.0), (20.0, 6.0)])


def robot_inputs() -> tuple[Floats, Floats, list[params.RobotParams]]:
    carrier = params.ROBOT_PARAMS[RobotKind.CARRIER]
    return np.array([[10.0, 3.0, 0.0]]), np.array([carrier.max_speed]), [carrier]


def test_sampling_is_deterministic_by_seed_and_inside_the_regions() -> None:
    poses, speeds, plist = robot_inputs()
    runs = []
    for _ in range(2):
        gens = streams.make_streams(5, "humans", 4)
        runs.append(humans.sample_hidden_humans(gens, [REGION], 3, poses, speeds, plist))
    for a, b in zip(runs[0], runs[1], strict=True):
        assert a.tolist() == b.tolist()
    for variant in runs[0]:
        assert variant.shape == (3, 2)
        for x, y in variant:
            assert 20.0 <= x <= 30.0 and 0.0 <= y <= 6.0


def test_variants_differ_from_each_other() -> None:
    poses, speeds, plist = robot_inputs()
    gens = streams.make_streams(5, "humans", 3)
    out = humans.sample_hidden_humans(gens, [REGION], 2, poses, speeds, plist)
    assert out[0].tolist() != out[1].tolist()


def test_variants_with_a_human_inside_the_stopping_distance_are_rejected_at_sampling() -> None:
    poses, speeds, plist = robot_inputs()
    carrier = plist[0]
    minimum = humans.min_stop_distance(carrier, float(speeds[0]))
    gens = streams.make_streams(11, "humans", 20)
    near = world.Polygon.from_points([(10.5, 0.0), (40.0, 0.0), (40.0, 6.0), (10.5, 6.0)])
    for variant in humans.sample_hidden_humans(gens, [near], 4, poses, speeds, plist):
        distances = np.hypot(variant[:, 0] - 10.0, variant[:, 1] - 3.0)
        assert np.all(distances > minimum)


def test_sampling_fails_when_the_whole_region_is_inside_the_stopping_distance() -> None:
    poses, speeds, plist = robot_inputs()
    tight = world.Polygon.from_points([(10.5, 2.5), (11.5, 2.5), (11.5, 3.5), (10.5, 3.5)])
    gens = streams.make_streams(2, "humans", 1)
    with pytest.raises(ValueError, match="no admissible"):
        humans.sample_hidden_humans(gens, [tight], 1, poses, speeds, plist, max_tries=200)


def test_min_stop_distance_uses_the_current_speed() -> None:
    p = params.ROBOT_PARAMS[RobotKind.CARRIER]
    assert humans.min_stop_distance(p, 0.0) == 0.0
    expected = 1.0 * p.delay_ticks * DT + 1.0 / (2 * p.decel)
    assert humans.min_stop_distance(p, 1.0) == pytest.approx(expected)
    assert math.isfinite(humans.min_stop_distance(p, p.max_speed))


# ---------------------------------------------------------------- state


def test_human_arrays_are_contiguous_and_forks_are_isolated() -> None:
    plans = [humans.HumanPlan.walker(speed=1.2, turn_sigma=0.4)]
    sim = make(3, plans)
    sim.run(20)
    for array in sim.snapshot().arrays.values():
        assert array.flags["C_CONTIGUOUS"]
    before = sim.state_hash()
    sim.fork().run(100)
    assert sim.state_hash() == before
