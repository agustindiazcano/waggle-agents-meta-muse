"""Robot dynamics: actuation delay, limits, stopping distance bound, turning radius, footprints."""

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from waggle.sim import engine, params, robots, state
from waggle.sim.params import DT, RobotKind

KINDS = list(RobotKind)
EPS = 1e-9


def make_engine(
    kinds: list[RobotKind],
    speeds: list[float] | None = None,
    poses: list[tuple[float, float, float]] | None = None,
    raised: list[bool] | None = None,
) -> tuple[engine.Engine, robots.RobotFleet]:
    fleet = robots.RobotFleet(kinds, load_raised=raised)
    n = len(kinds)
    pose = np.array(poses or [(0.0, 0.0, 0.0)] * n, dtype=np.float64)
    arrays = fleet.initial_arrays(pose, np.array(speeds or [0.0] * n, dtype=np.float64))
    return engine.Engine(1, arrays, [fleet.system()], {}), fleet


def f64(sim: engine.Engine, name: str) -> NDArray[np.float64]:
    return np.asarray(sim.state.arrays[name], dtype=np.float64)


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


# ---------------------------------------------------------------- delay


@pytest.mark.parametrize("kind", KINDS)
def test_a_command_takes_effect_exactly_after_the_actuation_delay(kind: RobotKind) -> None:
    p = params.ROBOT_PARAMS[kind]
    sim, fleet = make_engine([kind])
    fleet.issue(sim.state, np.array([[p.max_speed, 0.0]]))
    speeds = []
    for _ in range(p.delay_ticks + 3):
        sim.step()
        speeds.append(float(f64(sim, "robot_speed")[0]))
    assert all(s == 0.0 for s in speeds[: p.delay_ticks])
    assert speeds[p.delay_ticks] > 0.0


def test_without_a_new_command_the_last_one_keeps_applying() -> None:
    sim, fleet = make_engine([RobotKind.CARRIER])
    fleet.issue(sim.state, np.array([[1.0, 0.0]]))
    sim.run(200)
    assert f64(sim, "robot_speed")[0] == pytest.approx(1.0)


# ---------------------------------------------------------------- stopping distance


def stopping_distance(kind: RobotKind, speed: float, turn: float, raised: bool = False) -> float:
    """Path length from the stop command to standstill, at constant steering ``turn``."""
    sim, fleet = make_engine([kind], speeds=[speed], raised=[raised])
    active = f64(sim, "robot_active")
    active[0] = (speed, turn)
    fleet.issue(sim.state, np.array([[0.0, turn]]))
    total = 0.0
    last = f64(sim, "robot_pose")[0, :2].copy()
    for _ in range(100_000):
        sim.step()
        now = f64(sim, "robot_pose")[0, :2]
        total += float(np.hypot(*(now - last)))
        last = now.copy()
        if f64(sim, "robot_speed")[0] == 0.0:
            return total
    raise AssertionError("the robot never stopped")


def stopping_bound(p: params.RobotParams, speed: float, decel: float) -> float:
    """Documented bound: v*dt/2 + a*dt^2/2 (ADR-021, explicit Euler position update)."""
    return speed * DT / 2 + decel * DT * DT / 2


@settings(max_examples=60, deadline=None)
@given(
    kind=st.sampled_from(KINDS),
    fraction=st.floats(0.05, 1.0),
    turn_fraction=st.floats(-1.0, 1.0),
)
def test_simulated_stopping_distance_matches_the_formula_within_the_bound(
    kind: RobotKind, fraction: float, turn_fraction: float
) -> None:
    p = params.ROBOT_PARAMS[kind]
    speed = fraction * p.max_speed
    limit = p.max_steer if p.kinematics == "bicycle" else p.max_angular_speed
    assert limit is not None
    simulated = stopping_distance(kind, speed, turn_fraction * limit)
    formula = speed * p.delay_ticks * DT + speed**2 / (2 * p.decel)
    assert abs(simulated - formula) <= stopping_bound(p, speed, p.decel) + EPS


@pytest.mark.parametrize("kind", KINDS)
def test_stopping_at_full_speed_in_a_full_turn_is_within_the_bound(kind: RobotKind) -> None:
    p = params.ROBOT_PARAMS[kind]
    limit = p.max_steer if p.kinematics == "bicycle" else p.max_angular_speed
    assert limit is not None
    simulated = stopping_distance(kind, p.max_speed, limit)
    formula = p.max_speed * p.delay_ticks * DT + p.max_speed**2 / (2 * p.decel)
    assert abs(simulated - formula) <= stopping_bound(p, p.max_speed, p.decel) + EPS


def test_load_raised_lowers_max_speed_and_decel_and_lengthens_the_stop() -> None:
    base = params.ROBOT_PARAMS[RobotKind.FORKLIFT]
    assert params.LOAD_RAISED_SPEED_FACTOR < 1.0 and params.LOAD_RAISED_DECEL_FACTOR < 1.0
    sim, fleet = make_engine([RobotKind.FORKLIFT], raised=[True])
    fleet.issue(sim.state, np.array([[base.max_speed, 0.0]]))
    sim.run(2000)
    assert f64(sim, "robot_speed")[0] == pytest.approx(base.max_speed * 0.6)
    speed = base.max_speed * params.LOAD_RAISED_SPEED_FACTOR
    raised = stopping_distance(RobotKind.FORKLIFT, speed, 0.0, raised=True)
    expected = speed * base.delay_ticks * DT + speed**2 / (2 * base.decel * 0.7)
    assert abs(raised - expected) <= stopping_bound(base, speed, base.decel * 0.7) + EPS
    assert raised > stopping_distance(RobotKind.FORKLIFT, speed, 0.0, raised=False)


def test_load_raised_is_only_for_the_forklift() -> None:
    with pytest.raises(ValueError, match="forklift"):
        robots.RobotFleet([RobotKind.CARRIER], load_raised=[True])


# ---------------------------------------------------------------- limits


commands = st.lists(st.tuples(st.floats(-5.0, 5.0), st.floats(-5.0, 5.0)), min_size=1, max_size=60)


@settings(max_examples=40, deadline=None)
@given(kind=st.sampled_from(KINDS), script=commands)
def test_speed_decel_angular_and_turning_limits_are_never_exceeded(
    kind: RobotKind, script: list[tuple[float, float]]
) -> None:
    p = params.ROBOT_PARAMS[kind]
    sim, fleet = make_engine([kind])
    previous_speed = 0.0
    previous_theta = 0.0
    for v_cmd, turn_cmd in script:
        fleet.issue(sim.state, np.array([[v_cmd, turn_cmd]]))
        for _ in range(8):
            before_speed = previous_speed
            sim.step()
            speed = float(f64(sim, "robot_speed")[0])
            theta = float(f64(sim, "robot_pose")[0, 2])
            assert -EPS <= speed <= p.max_speed + EPS
            assert abs(speed - before_speed) <= p.decel * DT + EPS
            omega = wrap(theta - previous_theta) / DT
            if p.kinematics == "differential":
                assert p.max_angular_speed is not None
                assert abs(omega) <= p.max_angular_speed + 1e-6
            else:
                assert abs(omega) <= before_speed / p.min_turn_radius + 1e-6
            previous_speed, previous_theta = speed, theta


@settings(max_examples=30, deadline=None)
@given(script=commands)
def test_a_forklift_cannot_follow_a_curve_tighter_than_its_turning_radius(
    script: list[tuple[float, float]],
) -> None:
    p = params.ROBOT_PARAMS[RobotKind.FORKLIFT]
    sim, fleet = make_engine([RobotKind.FORKLIFT], speeds=[p.max_speed])
    f64(sim, "robot_active")[0] = (p.max_speed, 0.0)
    last = f64(sim, "robot_pose")[0].copy()
    for v_cmd, turn_cmd in script:
        fleet.issue(sim.state, np.array([[abs(v_cmd), turn_cmd]]))
        for _ in range(6):
            sim.step()
            now = f64(sim, "robot_pose")[0]
            ds = float(np.hypot(*(now[:2] - last[:2])))
            if ds > 1e-9:
                curvature = abs(wrap(float(now[2] - last[2]))) / ds
                assert curvature <= 1.0 / p.min_turn_radius + 1e-6
            last = now.copy()


# ---------------------------------------------------------------- blind corner


def sharpest_left_turn(kind: RobotKind, speed: float) -> float:
    """Largest distance from the 90 degree corner point reached by the robot's reference point
    while it makes the sharpest left turn it can, starting along +x at ``speed``."""
    p = params.ROBOT_PARAMS[kind]
    sim, fleet = make_engine([kind], speeds=[speed])
    f64(sim, "robot_active")[0] = (speed, 0.0)
    turn = p.max_steer if p.kinematics == "bicycle" else p.max_angular_speed
    assert turn is not None
    fleet.issue(sim.state, np.array([[speed, turn]]))
    path = [f64(sim, "robot_pose")[0].copy()]
    while path[-1][2] < math.pi / 2 and len(path) < 100_000:
        sim.step()
        path.append(f64(sim, "robot_pose")[0].copy())
    start = np.array([path[p.delay_ticks][0], path[p.delay_ticks][1]])  # turn begins here
    end_x = path[-1][0]
    corner = np.array([end_x, start[1]])  # where the entry line meets the exit line
    leg = [pt for pt in path[p.delay_ticks :]]
    deviations = []
    for pt in leg:
        to_entry = abs(pt[1] - corner[1]) if pt[0] <= corner[0] else math.inf
        to_exit = abs(pt[0] - corner[0]) if pt[1] >= corner[1] else math.inf
        deviations.append(min(to_entry, to_exit))
    return max(deviations)


def test_a_forklift_at_full_speed_cannot_clear_a_corner_a_carrier_can() -> None:
    """A 90 degree corner of an aisle 2.4 m wide: the reference point may stray from the aisle
    centerline by (aisle width - robot width) / 2."""
    aisle = 2.4
    forklift = params.ROBOT_PARAMS[RobotKind.FORKLIFT]
    carrier = params.ROBOT_PARAMS[RobotKind.CARRIER]
    f_dev = sharpest_left_turn(RobotKind.FORKLIFT, forklift.max_speed)
    c_dev = sharpest_left_turn(RobotKind.CARRIER, carrier.max_speed)
    assert f_dev > (aisle - forklift.width) / 2
    assert c_dev <= (aisle - carrier.width) / 2
    assert f_dev > c_dev


# ---------------------------------------------------------------- footprints


def test_footprint_corners_follow_the_pose() -> None:
    p = params.ROBOT_PARAMS[RobotKind.CARRIER]
    corners = robots.footprint_corners(p, 1.0, 2.0, 0.0)
    xs, ys = corners[:, 0], corners[:, 1]
    assert (xs.min(), xs.max()) == pytest.approx((1.0 - p.length / 2, 1.0 + p.length / 2))
    assert (ys.min(), ys.max()) == pytest.approx((2.0 - p.width / 2, 2.0 + p.width / 2))
    turned = robots.footprint_corners(p, 0.0, 0.0, math.pi / 2)
    assert (turned[:, 0].max() - turned[:, 0].min()) == pytest.approx(p.width)


def polygon_area(points: NDArray[np.float64]) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def test_swept_footprint_of_a_straight_path_is_the_swept_rectangle() -> None:
    p = params.ROBOT_PARAMS[RobotKind.CARRIER]
    poses = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    pieces = robots.swept_footprint(p, poses)
    assert len(pieces) == 2
    assert polygon_area(pieces[0]) == pytest.approx((p.length + 1.0) * p.width)


def test_swept_footprint_covers_both_end_footprints_on_a_curve() -> None:
    p = params.ROBOT_PARAMS[RobotKind.FORKLIFT]
    poses = np.array([[0.0, 0.0, 0.0], [0.5, 0.1, 0.2]])
    piece = robots.swept_footprint(p, poses)[0]
    for pose in poses:
        for corner in robots.footprint_corners(p, *pose):
            assert polygon_contains_or_on(piece, corner)


def polygon_contains_or_on(poly: NDArray[np.float64], point: NDArray[np.float64]) -> bool:
    """True when ``point`` is inside a convex counter-clockwise polygon, or on its edge."""
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if cross < -1e-9:
            return False
    return True


def test_swept_footprint_needs_at_least_two_poses() -> None:
    p = params.ROBOT_PARAMS[RobotKind.CARRIER]
    with pytest.raises(ValueError):
        robots.swept_footprint(p, np.zeros((1, 3)))


# ---------------------------------------------------------------- state and determinism


def test_robot_arrays_are_contiguous_and_forks_are_isolated() -> None:
    sim, fleet = make_engine([RobotKind.CARRIER, RobotKind.FORKLIFT])
    fleet.issue(sim.state, np.array([[1.0, 0.1], [1.0, 0.1]]))
    sim.run(10)
    snap = sim.snapshot()
    for array in snap.arrays.values():
        assert array.flags["C_CONTIGUOUS"]
    fork = sim.fork()
    before = sim.state_hash()
    fork.run(50)
    assert sim.state_hash() == before


@settings(max_examples=20, deadline=None)
@given(script=commands)
def test_two_runs_with_the_same_commands_have_the_same_hash(
    script: list[tuple[float, float]],
) -> None:
    hashes = []
    for _ in range(2):
        sim, fleet = make_engine([RobotKind.CARRIER, RobotKind.FORKLIFT])
        for v_cmd, turn_cmd in script:
            fleet.issue(sim.state, np.array([[v_cmd, turn_cmd], [v_cmd, turn_cmd]]))
            sim.run(4)
        hashes.append(sim.state_hash())
    assert hashes[0] == hashes[1]


def test_state_is_the_same_type_for_every_class() -> None:
    sim, _ = make_engine(KINDS)
    assert isinstance(sim.state, state.SimState)
    assert f64(sim, "robot_pose").shape == (4, 3)
