"""Belief state and hidden human prior sampler (Stage D of the plan validator, ADR-023).

The belief state models what the fleet may know at t = 0: the static map, declared regions,
and K human variants sampled from a versioned scenario density prior. The sampler is pure,
deterministic, and rejects samples that place a human inside the minimum stopping distance
of any robot at t = 0.
"""

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from waggle.sim import params, world
from waggle.sim.humans import hits_obstacle
from waggle.validation.path_compiler import StaticMap

_MAX_DENSITY = 1.0


class SamplingError(ValueError):
    """The human prior sampler cannot produce an admissible variant within the attempt cap."""


def _inside_polygon(point: tuple[float, float], polygon: world.Polygon) -> bool:
    x, y = point
    inside = False
    pts = polygon.points
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


@dataclass(frozen=True)
class HumanPrior:
    """Declared human spawn density per region, with id and version (ADR-023)."""

    prior_id: str
    version: str
    region_densities: Mapping[str, float]

    def __post_init__(self) -> None:
        """Validate all prior fields fail closed."""
        if not self.prior_id or not isinstance(self.prior_id, str):
            raise ValueError("prior_id must be a non-empty string")
        if not self.version or not isinstance(self.version, str):
            raise ValueError("version must be a non-empty string")
        if not self.region_densities:
            raise ValueError("region_densities must contain at least one declared region")
        for region_id, density in self.region_densities.items():
            if not region_id or not isinstance(region_id, str):
                raise ValueError("region id must be a non-empty string")
            if isinstance(density, bool) or not isinstance(density, int | float):
                raise ValueError(f"density for {region_id} must be a number")
            val = float(density)
            if not math.isfinite(val):
                raise ValueError(f"density for {region_id} must be finite")
            if val < 0.0:
                raise ValueError(f"density for {region_id} must not be negative")
            if val > _MAX_DENSITY:
                raise ValueError(f"density for {region_id} must not exceed {_MAX_DENSITY}")


@dataclass(frozen=True)
class HumanState:
    """Position and velocity of one human at t = 0."""

    position: tuple[float, float]
    velocity: tuple[float, float]


@dataclass(frozen=True)
class SamplerOutcome:
    """Sampled humans and the count of rejected attempts (ADR-023)."""

    humans: tuple[HumanState, ...]
    rejected_count: int


def variant_seeds(scenario_seed: int, snapshot_rng_state: int | str, k: int) -> tuple[int, ...]:
    """Derive K deterministic variant seeds via SHA-256 (ADR-023, design section 5).

    ``snapshot_rng_state`` is an int or a string that already identifies the state. Any other
    type is refused: ``str()`` of an array is cut with ``...`` and would not tell states apart.
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueError("k must be a non-negative integer")
    if isinstance(snapshot_rng_state, bool) or not isinstance(snapshot_rng_state, int | str):
        raise TypeError("snapshot_rng_state must be an int or a string")
    if k == 0:
        return ()
    snap_str = str(snapshot_rng_state)
    seeds: list[int] = []
    for i in range(k):
        payload = f"{scenario_seed}:{snap_str}:{i}".encode()
        digest = hashlib.sha256(payload).digest()
        seed = int.from_bytes(digest[:4], byteorder="big")
        seeds.append(seed)
    return tuple(seeds)


def _resolve_robot_positions(
    static: StaticMap,
    robot_starts: Mapping[str, str]
    | Mapping[str, tuple[float, float]]
    | Sequence[tuple[float, float]]
    | None,
) -> list[tuple[float, float]]:
    starts = robot_starts if robot_starts is not None else static.robot_start
    at = {n.node_id: (n.x_m, n.y_m) for n in static.graph.nodes}
    positions: list[tuple[float, float]] = []
    if isinstance(starts, Mapping):
        for val in starts.values():
            if isinstance(val, str):
                if val not in at:
                    raise ValueError(f"unknown robot start node {val}")
                positions.append(at[val])
            elif isinstance(val, tuple) and len(val) == 2:
                positions.append((float(val[0]), float(val[1])))
            else:
                raise ValueError("robot start must be a node id or (x, y) coordinates")
    elif isinstance(starts, Sequence):
        for val in starts:
            if isinstance(val, tuple) and len(val) == 2:
                positions.append((float(val[0]), float(val[1])))
            else:
                raise ValueError("robot start must be an (x, y) coordinate pair")
    return positions


def sample_humans(
    prior: HumanPrior,
    static: StaticMap,
    robot_starts: Mapping[str, str]
    | Mapping[str, tuple[float, float]]
    | Sequence[tuple[float, float]]
    | None,
    variant_seed: int,
    *,
    min_stop_distance_m: float,
    max_attempts: int,
    walk_speed_mps: float = params.HUMAN_WALK_SPEED,
) -> SamplerOutcome:
    """Sample humans for one variant seed according to the prior.

    Rejects candidate positions inside ``min_stop_distance_m`` of any robot at t = 0. The
    distance and the attempt cap have no defaults: the caller chooses them. Each region gets
    ``round(area * density)`` humans, and at least one when its density is above zero (an
    assumption to calibrate). Raises SamplingError when ``max_attempts`` is exceeded for one
    human, and ValueError when there is no robot position to measure against.
    """
    cap = max_attempts
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise ValueError("max_attempts must be a positive integer")
    if not math.isfinite(min_stop_distance_m) or min_stop_distance_m < 0:
        raise ValueError("min_stop_distance_m must be finite and not negative")

    robot_pos = _resolve_robot_positions(static, robot_starts)
    if not robot_pos:
        raise ValueError("no robot position: the stopping distance rule cannot be applied")
    zones = {z.id: z for z in static.world.zones}
    for region_id in prior.region_densities:
        if region_id not in zones:
            raise ValueError(f"unknown region {region_id!r} not declared in map")

    # Pure, seeded numpy generator built exclusively from variant_seed
    rng = np.random.default_rng(np.random.SeedSequence(variant_seed))

    placed: list[HumanState] = []
    rejected_count = 0

    for region_id, density in sorted(prior.region_densities.items()):
        zone = zones[region_id]
        poly = zone.polygon
        area = poly.area()
        human_count = round(area * density)
        if human_count <= 0 and density > 0.0:
            human_count = 1

        xs = [pt[0] for pt in poly.points]
        ys = [pt[1] for pt in poly.points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        for _ in range(human_count):
            attempts = 0
            success = False
            while attempts < cap:
                attempts += 1
                cand_x = float(rng.uniform(min_x, max_x))
                cand_y = float(rng.uniform(min_y, max_y))
                cand = (cand_x, cand_y)

                if not _inside_polygon(cand, poly):
                    continue

                cand_arr = np.array(cand, dtype=np.float64)
                if hits_obstacle(static.world, cand_arr, params.HUMAN_RADIUS):
                    continue

                # Rejection rule: inside minimum stopping distance of any robot at t=0
                inside_stopping = any(
                    math.hypot(cand_x - rx, cand_y - ry) <= min_stop_distance_m
                    for rx, ry in robot_pos
                )
                if inside_stopping:
                    rejected_count += 1
                    continue

                heading = float(rng.uniform(-math.pi, math.pi))
                vx = walk_speed_mps * math.cos(heading)
                vy = walk_speed_mps * math.sin(heading)
                placed.append(HumanState(cand, (vx, vy)))
                success = True
                break

            if not success:
                raise SamplingError(
                    f"attempt cap {cap} exceeded: could not place human in {region_id}"
                )

    return SamplerOutcome(tuple(placed), rejected_count)
