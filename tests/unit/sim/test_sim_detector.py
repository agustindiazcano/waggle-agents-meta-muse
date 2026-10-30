"""Exact detector: hand-built cases and a property test against a brute-force fine-substep check."""

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray

from waggle.sim import detector, engine, state
from waggle.sim.params import HUMAN_RADIUS, RobotKind, RobotParams

Floats = NDArray[np.float64]


def rect(length: float, width: float) -> RobotParams:
    return RobotParams(
        RobotKind.CARRIER, 2.0, 2.0, 0.10, length, width, "differential", max_angular_speed=1.5
    )


UNIT = rect(1.0, 1.0)
EPS = 1e-9


def gap(
    p: RobotParams,
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    ha: tuple[float, float],
    hb: tuple[float, float],
    radius: float = 0.25,
) -> float:
    return detector.robot_human_gap(p, np.array(a), np.array(b), np.array(ha), np.array(hb), radius)


# ---------------------------------------------------------------- hand-built cases


def test_collision_when_the_robot_drives_into_a_standing_human() -> None:
    g = gap(UNIT, (-2, 0, 0), (0.3, 0, 0), (1.0, 0), (1.0, 0))
    assert g <= 0.0


def test_no_contact_and_a_known_gap_for_a_clear_pass() -> None:
    g = gap(UNIT, (-2, 0, 0), (2, 0, 0), (0.0, 1.0), (0.0, 1.0))
    assert g == pytest.approx(1.0 - 0.5 - 0.25, abs=1e-9)


def test_exact_touch_counts_as_contact() -> None:
    g = gap(UNIT, (0, 0, 0), (0, 0, 0), (0.75, 0.0), (0.75, 0.0))
    assert g == 0.0
    assert detector.is_contact(g)


def test_a_hair_further_is_not_contact() -> None:
    g = gap(UNIT, (0, 0, 0), (0, 0, 0), (0.7500001, 0.0), (0.7500001, 0.0))
    assert g > 0.0 and not detector.is_contact(g)


def test_a_fast_robot_crossing_a_thin_human_between_ticks_is_detected() -> None:
    """The robot moves 4 m in one step. Neither end pose touches the human."""
    thin = 0.05
    assert gap(UNIT, (-2, 0, 0), (-2, 0, 0), (0.0, 0.0), (0.0, 0.0), thin) > 0
    assert gap(UNIT, (2, 0, 0), (2, 0, 0), (0.0, 0.0), (0.0, 0.0), thin) > 0
    swept = gap(UNIT, (-2, 0, 0), (2, 0, 0), (0.0, 0.0), (0.0, 0.0), thin)
    assert detector.is_contact(swept)


def test_a_human_crossing_a_standing_robot_between_ticks_is_detected() -> None:
    g = gap(UNIT, (0, 0, 0), (0, 0, 0), (-3.0, 0.0), (3.0, 0.0), 0.05)
    assert detector.is_contact(g)


def test_relative_motion_not_independent_sweeps() -> None:
    """Robot passes the crossing point early and the human arrives late: no contact."""
    g = gap(UNIT, (-1, 0, 0), (1, 0, 0), (0.0, -3.0), (0.0, -1.0), 0.25)
    assert g > 0.0


def test_a_rotating_footprint_sweeps_through_a_point_it_never_covers_at_the_ends() -> None:
    bar = rect(4.0, 0.2)
    ends_a = gap(bar, (0, 0, 0), (0, 0, 0), (1.0, 1.0), (1.0, 1.0), 0.05)
    ends_b = gap(bar, (0, 0, math.pi / 2), (0, 0, math.pi / 2), (1.0, 1.0), (1.0, 1.0), 0.05)
    swept = gap(bar, (0, 0, 0), (0, 0, math.pi / 2), (1.0, 1.0), (1.0, 1.0), 0.05)
    assert ends_a > 0 and ends_b > 0
    assert detector.is_contact(swept)


def test_a_curved_path_step_is_covered() -> None:
    forklift = rect(2.4, 1.1)
    g = gap(forklift, (0, 0, 0), (0.5, 0.05, 0.04), (1.4, 0.7), (1.4, 0.7), 0.3)
    assert g < 0.3


def test_separation_violation_is_strictly_below_the_margin() -> None:
    g = gap(UNIT, (0, 0, 0), (0, 0, 0), (1.15, 0.0), (1.15, 0.0))  # gap 0.4
    assert g == pytest.approx(0.4)
    assert detector.is_violation(g, 0.5)
    assert not detector.is_violation(g, 0.3)
    assert not detector.is_violation(0.5, 0.5)
    assert detector.is_violation(0.0, 0.5)


def test_robot_robot_head_on_collision_and_parallel_pass() -> None:
    a0, a1 = np.array([-2.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0])
    b0, b1 = np.array([2.0, 0.0, math.pi]), np.array([0.2, 0.0, math.pi])
    assert detector.is_contact(detector.robot_robot_gap(UNIT, a0, a1, UNIT, b0, b1))
    c0, c1 = np.array([2.0, 2.0, math.pi]), np.array([-2.0, 2.0, math.pi])
    clear = detector.robot_robot_gap(UNIT, a0, np.array([2.0, 0.0, 0.0]), UNIT, c0, c1)
    assert clear == pytest.approx(1.0, abs=1e-9)


def test_robot_robot_touching_corners_count_as_contact() -> None:
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([1.0, 1.0, 0.0])  # corner of one meets corner of the other
    assert detector.is_contact(detector.robot_robot_gap(UNIT, a, a, UNIT, b, b))


# ---------------------------------------------------------------- brute force comparison


def brute_gap(
    p: RobotParams,
    a: Floats,
    b: Floats,
    ha: Floats,
    hb: Floats,
    radius: float,
    steps: int = 400,
) -> float:
    best = math.inf
    for k in range(steps + 1):
        s = k / steps
        x = a[0] + (b[0] - a[0]) * s
        y = a[1] + (b[1] - a[1]) * s
        th = a[2] + (b[2] - a[2]) * s
        hx = ha[0] + (hb[0] - ha[0]) * s
        hy = ha[1] + (hb[1] - ha[1]) * s
        c, sn = math.cos(th), math.sin(th)
        lx = c * (hx - x) + sn * (hy - y)
        ly = -sn * (hx - x) + c * (hy - y)
        dx = max(abs(lx) - p.length / 2, 0.0)
        dy = max(abs(ly) - p.width / 2, 0.0)
        best = min(best, math.hypot(dx, dy) - radius)
    return best


coord = st.floats(-4.0, 4.0)
move = st.floats(-0.7, 0.7)


@settings(max_examples=150, deadline=None)
@given(
    x=coord,
    y=coord,
    th=st.floats(-math.pi, math.pi),
    dx=move,
    dy=move,
    dth=st.floats(-0.05, 0.05),
    hx=coord,
    hy=coord,
    hdx=st.floats(-0.1, 0.1),
    hdy=st.floats(-0.1, 0.1),
    length=st.floats(0.5, 2.5),
    width=st.floats(0.4, 1.2),
    radius=st.floats(0.05, 0.4),
)
def test_exact_detector_against_a_brute_force_fine_substep_check(
    x: float,
    y: float,
    th: float,
    dx: float,
    dy: float,
    dth: float,
    hx: float,
    hy: float,
    hdx: float,
    hdy: float,
    length: float,
    width: float,
    radius: float,
) -> None:
    p = rect(length, width)
    a, b = np.array([x, y, th]), np.array([x + dx, y + dy, th + dth])
    ha, hb = np.array([hx, hy]), np.array([hx + hdx, hy + hdy])
    exact = detector.robot_human_gap(p, a, b, ha, hb, radius)
    fine = brute_gap(p, a, b, ha, hb, radius)
    diagonal = math.hypot(length, width) / 2
    delta = abs(dth) / detector.pieces_for(dth)
    sagitta = diagonal * (1 - math.cos(delta / 2))
    relative = math.hypot(dx - hdx, dy - hdy)
    travel = math.hypot(dx, dy) + math.hypot(hdx, hdy) + diagonal * abs(dth)
    tolerance = diagonal * delta / 2 + 2 * sagitta + relative * delta / 4 + travel / 400
    assert exact <= fine + EPS, "no false negatives: the exact gap never exceeds the fine one"
    assert fine - exact <= tolerance + EPS, "exact detections are confirmed within the tolerance"
    if fine <= 0.0:
        assert detector.is_contact(exact)


# ---------------------------------------------------------------- as a system


def build(
    robot_path: list[tuple[float, float]], human: tuple[float, float], margin: float = 0.5
) -> tuple[engine.Engine, detector.Detector]:
    det = detector.Detector([UNIT], separation_margin=margin, near_miss_margin=0.8)
    arrays = det.initial_arrays(np.array([[*robot_path[0], 0.0]]), np.array([human]))

    def mover(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        index = min(sim.tick + 1, len(robot_path) - 1)
        np.asarray(sim.arrays["robot_pose"], dtype=np.float64)[0, :2] = robot_path[index]

    arrays["robot_pose"] = np.array([[*robot_path[0], 0.0]])
    arrays["human_pos"] = np.array([human])
    return engine.Engine(1, arrays, [mover, det.system()], {}), det


def test_system_counts_episodes_not_ticks() -> None:
    path = [(-3.0 + 0.5 * k, 0.0) for k in range(13)]
    sim, det = build(path, (0.0, 0.0))
    sim.run(len(path))
    counts = det.counts(sim.state)
    assert counts["human_collisions"] == 1
    assert counts["separation_violations"] >= 1
    assert counts["robot_collisions"] == 0


def test_system_counts_a_tunneling_step_as_a_collision() -> None:
    sim, det = build([(-5.0, 0.0), (5.0, 0.0)], (0.0, 0.0))
    sim.run(1)
    assert det.counts(sim.state)["human_collisions"] == 1


def test_system_reports_a_near_miss_without_a_collision() -> None:
    path = [(-3.0 + 0.5 * k, 0.0) for k in range(13)]
    sim, det = build(path, (0.0, 1.0), margin=0.2)
    sim.run(len(path))
    counts = det.counts(sim.state)
    assert counts["human_collisions"] == 0
    assert counts["near_misses"] == 1
    assert counts["separation_violations"] == 0


def test_system_is_deterministic_and_fork_safe() -> None:
    path = [(-3.0 + 0.5 * k, 0.0) for k in range(13)]
    a, _ = build(path, (0.0, 0.0))
    b, _ = build(path, (0.0, 0.0))
    a.run(13)
    b.run(13)
    assert a.state_hash() == b.state_hash()
    fork = a.fork()
    before = a.state_hash()
    fork.run(5)
    assert a.state_hash() == before


def test_default_human_radius_is_the_documented_disc() -> None:
    assert detector.DEFAULT_HUMAN_RADIUS == HUMAN_RADIUS
