"""Humans: scripted paths, seeded random walkers, adversarial timing, hidden-human sampling.

Ground truth. Control never imports this module. Humans are discs (ADR-021). A scripted human
follows a polyline at constant speed from its start tick. A walker keeps a heading that drifts
with its own seeded stream and turns away from walls and racks. Adversarial plans are scripted
plans whose start tick is computed from the declared robot parameters only.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from waggle.sim import state, world
from waggle.sim.engine import System
from waggle.sim.params import DT, HUMAN_RADIUS, RobotParams

Floats = NDArray[np.float64]
Point = tuple[float, float]

ADVERSARIAL_FRACTION_RANGE = (0.5, 1.5)
"""The human reaches the crossing when the robot is this fraction of its maximum-speed
stopping distance away. Below 1 the human appears inside that distance (assumption)."""

_WALKER_TURN_AWAY = math.pi / 2
_STEP_OUT_EXTENSION = 3.0


# ---------------------------------------------------------------- geometry


def path_position(path: Sequence[Point], speed: float, seconds: float) -> Point:
    """Position after ``seconds`` along a polyline at constant ``speed``; stops at the end."""
    if len(path) < 2:
        raise ValueError("a path needs at least two waypoints")
    if speed <= 0 or seconds < 0:
        raise ValueError("speed must be above zero and time must not be negative")
    remaining = speed * seconds
    for (x0, y0), (x1, y1) in itertools.pairwise(path):
        length = math.hypot(x1 - x0, y1 - y0)
        if remaining <= length and length > 0:
            f = remaining / length
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
        remaining -= length
    return path[-1]


def _inside(point: Floats, polygon: world.Polygon) -> bool:
    x, y = float(point[0]), float(point[1])
    inside = False
    pts = polygon.points
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def _edge_distance(point: Floats, polygon: world.Polygon) -> float:
    px, py = float(point[0]), float(point[1])
    best = math.inf
    pts = polygon.points
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
        dx, dy = x1 - x0, y1 - y0
        denom = dx * dx + dy * dy
        f = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / denom))
        best = min(best, math.hypot(px - (x0 + f * dx), py - (y0 + f * dy)))
    return best


def hits_obstacle(box: world.World, position: Floats, radius: float) -> bool:
    """True when a disc touches or overlaps a wall or a rack, or leaves the bounds."""
    x, y = float(position[0]), float(position[1])
    x0, y0, x1, y1 = box.bounds
    if x - radius < x0 or x + radius > x1 or y - radius < y0 or y + radius > y1:
        return True
    for polygon in (*box.walls, *box.racks):
        if _inside(position, polygon) or _edge_distance(position, polygon) <= radius:
            return True
    return False


# ---------------------------------------------------------------- plans and crowd


@dataclass(frozen=True)
class HumanPlan:
    """How one human moves. ``kind`` is ``scripted`` or ``walker``."""

    kind: str
    speed: float
    path: tuple[Point, ...] = ()
    start_tick: int = 0
    turn_sigma: float = 0.0

    @classmethod
    def scripted(cls, path: Sequence[Point], speed: float, start_tick: int = 0) -> "HumanPlan":
        """Follow ``path`` at ``speed`` from ``start_tick``, then stand at the last point."""
        if len(path) < 2 or speed <= 0 or start_tick < 0:
            raise ValueError("a scripted plan needs two waypoints, a speed and a start tick")
        return cls("scripted", speed, tuple((float(x), float(y)) for x, y in path), start_tick)

    @classmethod
    def walker(cls, speed: float, turn_sigma: float) -> "HumanPlan":
        """Random walker: heading drifts by ``turn_sigma`` rad per sqrt(second)."""
        if speed <= 0 or turn_sigma < 0:
            raise ValueError("a walker needs a speed above zero and a non-negative turn sigma")
        return cls("walker", speed, turn_sigma=turn_sigma)


class Crowd:
    """The humans of a run: their plans and the system that moves them."""

    def __init__(self, plans: Sequence[HumanPlan], box: world.World | None) -> None:
        self.plans = list(plans)
        self.world = box

    def initial_arrays(self, starts: Floats) -> dict[str, state.Array]:
        """State arrays. ``starts`` is (M, 2) in meters."""
        pos = np.ascontiguousarray(starts, dtype=np.float64)
        if pos.shape != (len(self.plans), 2):
            raise ValueError(f"starts must have shape ({len(self.plans)}, 2)")
        return {"human_pos": pos, "human_heading": np.zeros(len(self.plans))}

    def system(self) -> System:
        """The per-tick movement as an engine system."""

        def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
            pos = np.asarray(sim.arrays["human_pos"], dtype=np.float64)
            heading = np.asarray(sim.arrays["human_heading"], dtype=np.float64)
            for i, plan in enumerate(self.plans):
                if plan.kind == "scripted":
                    elapsed = (sim.tick + 1 - plan.start_tick) * DT
                    if elapsed > 0:
                        pos[i] = path_position(plan.path, plan.speed, elapsed)
                else:
                    self._walk(i, plan, pos, heading, rngs[f"humans/{i}"])

        return step

    def _walk(
        self,
        i: int,
        plan: HumanPlan,
        pos: Floats,
        heading: Floats,
        rng: np.random.Generator,
    ) -> None:
        heading[i] += plan.turn_sigma * math.sqrt(DT) * rng.normal()
        step = plan.speed * DT
        proposed = pos[i] + step * np.array([math.cos(heading[i]), math.sin(heading[i])])
        if self.world is not None and hits_obstacle(self.world, proposed, HUMAN_RADIUS):
            heading[i] += _WALKER_TURN_AWAY
        else:
            pos[i] = proposed


# ---------------------------------------------------------------- adversarial timing


def min_stop_distance(p: RobotParams, speed: float) -> float:
    """``v*t_r + v^2/(2a)`` for a robot class at ``speed``, from its declared parameters."""
    return speed * p.delay_ticks * DT + speed**2 / (2 * p.decel)


def max_speed_stop_distance(p: RobotParams) -> float:
    """Stopping distance at the declared maximum speed."""
    return min_stop_distance(p, p.max_speed)


def draw_fraction(rng: np.random.Generator) -> float:
    """A fraction drawn from the seed inside ``ADVERSARIAL_FRACTION_RANGE``."""
    lo, hi = ADVERSARIAL_FRACTION_RANGE
    return float(lo + (hi - lo) * rng.random())


def _start_tick(
    p: RobotParams,
    fraction: float,
    crossing: Point,
    robot_start: Point,
    human_start: Point,
    human_speed: float,
) -> int:
    """Tick at which the human must start so that it reaches the crossing when the robot,
    cruising at its declared maximum speed, is ``fraction`` of its stopping distance away."""
    robot_gap = math.hypot(crossing[0] - robot_start[0], crossing[1] - robot_start[1])
    arrive = (robot_gap - fraction * max_speed_stop_distance(p)) / p.max_speed
    walk = math.hypot(crossing[0] - human_start[0], crossing[1] - human_start[1]) / human_speed
    start = arrive - walk
    if arrive < 0 or start < 0:
        raise ValueError("the human would have to start before the run starts")
    return round(start / DT)


def _beyond(human_start: Point, crossing: Point, extra: float) -> Point:
    dx, dy = crossing[0] - human_start[0], crossing[1] - human_start[1]
    norm = math.hypot(dx, dy)
    return (crossing[0] + dx / norm * extra, crossing[1] + dy / norm * extra)


def adversarial_crossing(
    p: RobotParams,
    *,
    fraction: float,
    crossing: Point,
    robot_start: Point,
    human_start: Point,
    human_speed: float,
) -> HumanPlan:
    """Cross the robot's path at the worst moment and keep walking to the far side."""
    tick = _start_tick(p, fraction, crossing, robot_start, human_start, human_speed)
    dx, dy = crossing[0] - human_start[0], crossing[1] - human_start[1]
    far = (crossing[0] + dx, crossing[1] + dy)
    return HumanPlan.scripted([human_start, crossing, far], human_speed, tick)


def adversarial_step_out(
    p: RobotParams,
    *,
    fraction: float,
    crossing: Point,
    robot_start: Point,
    human_start: Point,
    human_speed: float,
) -> HumanPlan:
    """Wait hidden at ``human_start`` (for example behind a rack), then step out at the corner."""
    tick = _start_tick(p, fraction, crossing, robot_start, human_start, human_speed)
    end = _beyond(human_start, crossing, _STEP_OUT_EXTENSION)
    return HumanPlan.scripted([human_start, crossing, end], human_speed, tick)


def adversarial_stop_in_aisle(
    p: RobotParams,
    *,
    fraction: float,
    crossing: Point,
    robot_start: Point,
    human_start: Point,
    human_speed: float,
) -> HumanPlan:
    """Walk into the aisle and stop at ``crossing`` when the robot is at the set distance."""
    tick = _start_tick(p, fraction, crossing, robot_start, human_start, human_speed)
    return HumanPlan.scripted([human_start, crossing], human_speed, tick)


# ---------------------------------------------------------------- hidden human variants


def sample_hidden_humans(
    generators: Sequence[np.random.Generator],
    regions: Sequence[world.Polygon],
    count: int,
    robot_poses: Floats,
    robot_speeds: Floats,
    robot_params: Sequence[RobotParams],
    max_tries: int = 1000,
) -> list[Floats]:
    """One variant per generator: ``count`` humans placed uniformly in the occluded regions.

    A sampled human is rejected when it lies inside the minimum stopping distance of any robot
    at t = 0 (plus the robot half length and the human radius), because no plan can fix that
    (ADR-023). Raises ValueError when no admissible position is found in ``max_tries``.
    """
    if not regions or count < 0:
        raise ValueError("sampling needs at least one region and a non-negative count")
    limits = [
        min_stop_distance(p, float(v)) + p.length / 2 + HUMAN_RADIUS
        for p, v in zip(robot_params, robot_speeds, strict=True)
    ]
    variants: list[Floats] = []
    for rng in generators:
        placed = np.zeros((count, 2))
        for j in range(count):
            placed[j] = _sample_one(rng, regions, robot_poses, limits, max_tries)
        variants.append(placed)
    return variants


def _sample_one(
    rng: np.random.Generator,
    regions: Sequence[world.Polygon],
    robot_poses: Floats,
    limits: Sequence[float],
    max_tries: int,
) -> Floats:
    for _ in range(max_tries):
        region = regions[int(rng.integers(len(regions)))]
        xs = [pt[0] for pt in region.points]
        ys = [pt[1] for pt in region.points]
        candidate = np.array([rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))])
        if not _inside(candidate, region):
            continue
        gaps = np.hypot(robot_poses[:, 0] - candidate[0], robot_poses[:, 1] - candidate[1])
        if all(float(g) > limit for g, limit in zip(gaps, limits, strict=True)):
            return candidate
    raise ValueError("no admissible hidden human position: the regions lie inside stopping range")
