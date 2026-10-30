"""Exact collision and separation-violation detector on ground truth (ADR-021).

Independent of any control code. Sets are closed: an exact touch is contact, and contact is a
collision. Separation below the declared margin is a violation (strictly below).

Each tick is checked as a continuous interval, never at the end poses only, so a fast robot
that crosses a thin human between two ticks is still caught. The check runs in the frame of
the second body, where the relative translation is exact. The step is cut into pieces that
turn by at most ``MAX_ROTATION_PER_PIECE`` radians, and each piece is the convex hull of the
footprint at its two ends. A rotating corner follows an arc that bulges past the chord by at
most a sagitta, so each piece gap is reduced by the sagitta. The detector therefore never
reports a larger gap than the true one (no false negatives). The hull also fills the
concavity between the two end footprints, so the reported gap can be smaller than the true
one by at most ``half_diagonal * delta / 2 + 2 * sagitta + d * delta / 4``, with ``delta`` the
rotation of a piece and ``d`` the relative translation of the step. For the largest robot
(forklift, half diagonal 1.3 m) that is about 3 mm. Larger errors only make it more cautious.
"""

import itertools
import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from waggle.sim import robots, state
from waggle.sim.engine import System
from waggle.sim.params import HUMAN_RADIUS, RobotParams

Floats = NDArray[np.float64]
DEFAULT_HUMAN_RADIUS = HUMAN_RADIUS
MAX_ROTATION_PER_PIECE = 0.005
"""A step is cut so that no piece turns by more than this many radians."""
COUNT_NAMES = ("human_collisions", "robot_collisions", "separation_violations", "near_misses")
_CONTACT, _VIOLATION, _NEAR = 0, 1, 2


def is_contact(gap: float) -> bool:
    """Closed sets: a gap of exactly zero is contact."""
    return gap <= 0.0


def is_violation(gap: float, margin: float) -> bool:
    """Separation below the declared margin. A gap equal to the margin is not a violation."""
    return gap < margin


# ---------------------------------------------------------------- convex polygon distances


def _point_segment(p: Floats, a: Floats, b: Floats) -> float:
    ab = b - a
    denom = float(ab @ ab)
    f = 0.0 if denom == 0 else max(0.0, min(1.0, float((p - a) @ ab) / denom))
    return float(np.hypot(*(p - (a + f * ab))))


def _inside_convex(p: Floats, poly: Floats) -> bool:
    """Inside or on the edge of a counter-clockwise convex polygon."""
    for a, b in itertools.pairwise([*poly, poly[0]]):
        if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < 0.0:
            return False
    return True


def _orient(a: Floats, b: Floats, c: Floats) -> float:
    return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _on_segment(a: Floats, b: Floats, p: Floats) -> bool:
    in_x = min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
    in_y = min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    return bool(in_x and in_y)


def _segments_touch(a: Floats, b: Floats, c: Floats, d: Floats) -> bool:
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    return (
        (o1 == 0 and _on_segment(a, b, c))
        or (o2 == 0 and _on_segment(a, b, d))
        or (o3 == 0 and _on_segment(c, d, a))
        or (o4 == 0 and _on_segment(c, d, b))
    )


def point_polygon_distance(p: Floats, poly: Floats) -> float:
    """Distance from a point to a convex counter-clockwise polygon; zero inside or on it."""
    if _inside_convex(p, poly):
        return 0.0
    return min(_point_segment(p, a, b) for a, b in itertools.pairwise([*poly, poly[0]]))


def polygon_distance(first: Floats, second: Floats) -> float:
    """Distance between two convex counter-clockwise polygons; zero when they touch."""
    edges1 = list(itertools.pairwise([*first, first[0]]))
    edges2 = list(itertools.pairwise([*second, second[0]]))
    if any(_segments_touch(a, b, c, d) for a, b in edges1 for c, d in edges2):
        return 0.0
    if _inside_convex(first[0], second) or _inside_convex(second[0], first):
        return 0.0
    best = min(point_polygon_distance(v, second) for v in first)
    return min(best, min(point_polygon_distance(v, first) for v in second))


# ---------------------------------------------------------------- swept gaps


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _sagitta(p: RobotParams, turn: float) -> float:
    return math.hypot(p.length, p.width) / 2 * (1 - math.cos(abs(_wrap(turn)) / 2))


def _hull_of(p: RobotParams, first: Floats, second: Floats) -> Floats:
    both = np.vstack([robots.footprint_corners(p, *first), robots.footprint_corners(p, *second)])
    return robots.convex_hull(both)


def pieces_for(*turns: float) -> int:
    """Number of pieces a step is cut into so that each turns at most the maximum."""
    return max(1, math.ceil(max(abs(_wrap(t)) for t in turns) / MAX_ROTATION_PER_PIECE))


def _lerp(a: Floats, b: Floats, s: float, turn: float) -> Floats:
    return np.array([a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + turn * s])


def robot_human_gap(
    p: RobotParams, a: Floats, b: Floats, ha: Floats, hb: Floats, radius: float
) -> float:
    """Smallest gap between a robot footprint and a human disc over one step.

    ``a`` and ``b`` are the robot pose (x, y, theta) at the start and end of the step, ``ha``
    and ``hb`` the human position. Zero or negative means contact.
    """
    turn = _wrap(float(b[2] - a[2]))
    n = pieces_for(turn)
    shift = np.array([hb[0] - ha[0], hb[1] - ha[1], 0.0])
    end = b - shift
    best = math.inf
    for k in range(n):
        first = _lerp(a, end, k / n, turn)
        second = _lerp(a, end, (k + 1) / n, turn)
        human = np.asarray(ha, dtype=np.float64)
        hull = _hull_of(p, first, second)
        best = min(best, point_polygon_distance(human, hull) - radius - _sagitta(p, turn / n))
    return best


def robot_robot_gap(
    p1: RobotParams, a1: Floats, b1: Floats, p2: RobotParams, a2: Floats, b2: Floats
) -> float:
    """Smallest gap between two robot footprints over one step. Zero or negative is contact."""
    turn1, turn2 = _wrap(float(b1[2] - a1[2])), _wrap(float(b2[2] - a2[2]))
    n = pieces_for(turn1, turn2)
    shift = np.array([b2[0] - a2[0], b2[1] - a2[1], 0.0])
    end1 = b1 - shift
    still = np.array([a2[0], a2[1], a2[2]])
    best = math.inf
    for k in range(n):
        f1, s1 = _lerp(a1, end1, k / n, turn1), _lerp(a1, end1, (k + 1) / n, turn1)
        f2, s2 = _lerp(still, still, k / n, turn2), _lerp(still, still, (k + 1) / n, turn2)
        gap = polygon_distance(_hull_of(p1, f1, s1), _hull_of(p2, f2, s2))
        best = min(best, gap - _sagitta(p1, turn1 / n) - _sagitta(p2, turn2 / n))
    return best


# ---------------------------------------------------------------- the system


class Detector:
    """Counts collisions, separation violations and near misses as episodes during a run.

    An episode starts on the first tick a pair is in that condition and ends when it is not,
    so a long contact counts once. The margins are declared by the caller. All bookkeeping
    lives in state arrays, so a fork and a replay count the same.
    """

    def __init__(
        self,
        robot_params: Sequence[RobotParams],
        *,
        separation_margin: float,
        near_miss_margin: float,
        human_radius: float = DEFAULT_HUMAN_RADIUS,
    ) -> None:
        if separation_margin < 0 or near_miss_margin < 0 or human_radius <= 0:
            raise ValueError("margins must not be negative and the human radius must be positive")
        self.params = list(robot_params)
        self.margin = separation_margin
        self.near_margin = near_miss_margin
        self.radius = human_radius

    def initial_arrays(self, robot_pose: Floats, human_pos: Floats) -> dict[str, state.Array]:
        """Bookkeeping arrays, starting from the initial poses."""
        n, m = len(self.params), len(human_pos)
        if robot_pose.shape != (n, 3):
            raise ValueError(f"robot_pose must have shape ({n}, 3)")
        return {
            "det_prev_robot_pose": np.ascontiguousarray(robot_pose, dtype=np.float64),
            "det_prev_human_pos": np.ascontiguousarray(human_pos, dtype=np.float64).reshape(m, 2),
            "det_flags": np.zeros((n, m + n, 3), dtype=np.int64),
            "det_counts": np.zeros(len(COUNT_NAMES), dtype=np.int64),
        }

    @staticmethod
    def counts(sim: state.SimState) -> dict[str, int]:
        """Episode counts so far."""
        values = np.asarray(sim.arrays["det_counts"], dtype=np.int64)
        return {name: int(v) for name, v in zip(COUNT_NAMES, values, strict=True)}

    def system(self) -> System:
        """Run last in the tick list: it compares the new poses with the previous ones."""

        def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
            self._check(sim)

        return step

    def _bump(
        self,
        flags: NDArray[np.int64],
        counts: NDArray[np.int64],
        key: tuple[int, int],
        kind: int,
        now: bool,
        counter: int,
    ) -> None:
        i, j = key
        if now and flags[i, j, kind] == 0:
            counts[counter] += 1
        flags[i, j, kind] = 1 if now else 0

    def _check(self, sim: state.SimState) -> None:
        pose = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        humans = np.asarray(sim.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
        prev_pose = np.asarray(sim.arrays["det_prev_robot_pose"], dtype=np.float64)
        prev_h = np.asarray(sim.arrays["det_prev_human_pos"], dtype=np.float64).reshape(-1, 2)
        flags = np.asarray(sim.arrays["det_flags"], dtype=np.int64)
        counts = np.asarray(sim.arrays["det_counts"], dtype=np.int64)
        n, m = len(self.params), len(humans)
        reach_margin = max(self.margin, self.near_margin)
        for i, p in enumerate(self.params):
            diag = math.hypot(p.length, p.width) / 2
            move_i = float(np.hypot(*(pose[i, :2] - prev_pose[i, :2])))
            for j in range(m):
                move_h = float(np.hypot(*(humans[j] - prev_h[j])))
                near = float(np.hypot(*(prev_h[j] - prev_pose[i, :2])))
                if near > diag + self.radius + move_i + move_h + reach_margin + 1e-6:
                    gap = math.inf
                else:
                    gap = robot_human_gap(
                        p, prev_pose[i], pose[i], prev_h[j], humans[j], self.radius
                    )
                hit = is_contact(gap)
                self._bump(flags, counts, (i, j), _CONTACT, hit, 0)
                self._bump(flags, counts, (i, j), _VIOLATION, is_violation(gap, self.margin), 2)
                self._bump(flags, counts, (i, j), _NEAR, (not hit) and gap < self.near_margin, 3)
            for k in range(i + 1, n):
                q = self.params[k]
                far = float(np.hypot(*(prev_pose[k, :2] - prev_pose[i, :2])))
                move_k = float(np.hypot(*(pose[k, :2] - prev_pose[k, :2])))
                reach = diag + math.hypot(q.length, q.width) / 2 + move_i + move_k
                if far > reach + 1e-6:
                    hit = False
                else:
                    gap = robot_robot_gap(p, prev_pose[i], pose[i], q, prev_pose[k], pose[k])
                    hit = is_contact(gap)
                self._bump(flags, counts, (i, m + k), _CONTACT, hit, 1)
        prev_pose[:] = pose
        prev_h[:] = humans
