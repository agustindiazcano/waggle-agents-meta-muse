"""Fast lidar for rollouts: cached static ranges plus exact dynamic hits (ADR-025 deviation).

The exact lidar in ``waggle.sim.sensors`` stays the one used in execution and is the reference
in the tests. A rollout may use this module instead. It scans every robot of a tick at once.

Static map. The range to the walls and racks depends only on the origin and the ray direction.
The origin is snapped to the centre of a square cell of side ``cell`` and the direction to a
world-frame grid of ``world_rays`` rays, and the static range vector of a cell is computed once
with the exact segment test and kept in a cache. A scan is then a rotation of the cached vector
by the heading. The cache is keyed by cell only, so the result never depends on what was
scanned before and a run is reproducible. Quantization bounds: the origin moves by at most
``cell * sqrt(2) / 2`` and the heading by at most ``pi / world_rays``. For a ray that meets a
surface at incidence angle ``a`` (to the surface normal) the range moves by at most
``(origin shift + t * heading shift) / cos(a)``, so grazing rays and rays at a rack corner can
change by more, and by one ray at most per corner. The tests measure the distribution.

Dynamic entities (human discs and other robots' rectangles) are resolved per scan with exact
ray-disc and ray-segment tests, only for the rays inside the angular window that the entity's
bounding circle covers, and combined with the static ranges by taking the minimum. A ray
outside a window cannot meet the entity, so this part equals the reference.
"""

import math
from collections.abc import Callable, Sequence

import numpy as np
from numpy.typing import NDArray

from waggle.sim import hullgap, sensors, state
from waggle.sim.engine import System
from waggle.sim.observations import LidarScan
from waggle.sim.params import HUMAN_RADIUS, RobotParams

Floats = NDArray[np.float64]
Bools = NDArray[np.bool_]
_PARALLEL = 1e-12
_WINDOW_MARGIN_RAYS = 1.5
DEFAULT_CELL = 0.05
"""Side of a position cell in meters."""
DEFAULT_WORLD_FACTOR = 2
"""World-frame rays per scan ray."""
MAX_CELLS = 20000


class StaticScanCache:
    """Static range vectors on a world-frame ray grid, one per position cell."""

    def __init__(
        self,
        static: Floats,
        config: sensors.LidarConfig,
        cell: float = DEFAULT_CELL,
        world_factor: int = DEFAULT_WORLD_FACTOR,
    ) -> None:
        if cell <= 0 or world_factor < 1:
            raise ValueError("cell must be positive and world_factor at least 1")
        self.static = np.asarray(static, dtype=np.float64).reshape(-1, 4)
        self.config = config
        self.cell = cell
        self.factor = world_factor
        self.world_rays = config.n_rays * world_factor
        angles = -math.pi + 2 * math.pi / self.world_rays * np.arange(self.world_rays)
        self._dirs = np.stack([np.cos(angles), np.sin(angles)], axis=1)
        self._rows: dict[tuple[int, int], Floats] = {}

    def __len__(self) -> int:
        return len(self._rows)

    def _row(self, key: tuple[int, int]) -> Floats:
        row = self._rows.get(key)
        if row is None:
            if len(self._rows) >= MAX_CELLS:
                self._rows.clear()
            origin = np.array([key[0] * self.cell, key[1] * self.cell])
            row = sensors.segment_hits(origin, self._dirs, self.static)
            self._rows[key] = row
        return row

    def static_ranges(self, poses: Floats) -> Floats:
        """First-hit distance (R, n_rays) to the static map for each pose, infinity for none."""
        n = self.config.n_rays
        out = np.empty((len(poses), n))
        step = 2 * math.pi / self.world_rays
        local = np.arange(n) * self.factor
        for r, pose in enumerate(poses):
            key = (round(float(pose[0]) / self.cell), round(float(pose[1]) / self.cell))
            heading = round(float(pose[2]) / step)
            out[r] = self._row(key)[(heading + local) % self.world_rays]
        return out


def _candidates(
    poses: Floats, centers: Floats, radii: Floats, max_range: float, skip_self: bool
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Robot and entity indices of the pairs whose bounding circle is inside the lidar range."""
    delta = centers[None, :, :] - poses[:, None, :2]
    dist = np.hypot(delta[..., 0], delta[..., 1])
    mask = dist - radii[None, :] < max_range
    if skip_self:
        np.fill_diagonal(mask, False)
    rows, cols = np.nonzero(mask)
    return rows.astype(np.int64), cols.astype(np.int64)


def _windows(
    poses: Floats,
    centers: Floats,
    radii: Floats,
    rows: NDArray[np.int64],
    cols: NDArray[np.int64],
    n_rays: int,
) -> tuple[NDArray[np.int64], NDArray[np.int64], Floats]:
    """Ragged ray windows: for each (pair, ray) the pair index, the ray index and its angle."""
    step = 2 * math.pi / n_rays
    delta = centers[cols] - poses[rows, :2]
    dist = np.hypot(delta[:, 0], delta[:, 1])
    rad = radii[cols]
    inside = dist <= rad
    safe = np.where(inside, 1.0, dist)
    arc = np.arcsin(np.minimum(1.0, rad / safe)) / step + _WINDOW_MARGIN_RAYS
    half = np.where(inside, float(n_rays), arc)
    center = (np.arctan2(delta[:, 1], delta[:, 0]) - poses[rows, 2] + math.pi) / step
    count = np.minimum(n_rays, np.floor(2 * half).astype(np.int64) + 1)
    first = np.floor(center - half).astype(np.int64)
    pair = np.repeat(np.arange(len(rows)), count)
    offset = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
    ray = (first[pair] + offset) % n_rays
    angle = poses[rows[pair], 2] - math.pi + ray * step
    return pair, ray, angle


def _disc_distances(
    poses: Floats, discs: Floats, rows: NDArray[np.int64], cols: NDArray[np.int64],
    pair: NDArray[np.int64], angle: Floats,
) -> Floats:  # fmt: skip
    """Distance along each ray to its disc, infinity for a miss (as the reference)."""
    dirs = np.stack([np.cos(angle), np.sin(angle)], axis=1)
    rel = poses[rows[pair], :2] - discs[cols[pair], :2]
    b = np.sum(dirs * rel, axis=1)
    c = np.sum(rel * rel, axis=1) - discs[cols[pair], 2] ** 2
    disc = b * b - c
    t = -b - np.sqrt(np.where(disc >= 0.0, disc, np.nan))
    return np.where((disc >= 0.0) & (t >= 0.0), t, np.inf)


def _box_distances(
    poses: Floats, corners: Floats, rows: NDArray[np.int64], cols: NDArray[np.int64],
    pair: NDArray[np.int64], angle: Floats,
) -> Floats:  # fmt: skip
    """Distance along each ray to its rectangle's edges, infinity for a miss."""
    dirs = np.stack([np.cos(angle), np.sin(angle)], axis=1)[:, None, :]  # (T, 1, 2)
    box = corners[cols[pair]]  # (T, 4, 2)
    start, edge = box, np.roll(box, -1, axis=1) - box
    to_start = start - poses[rows[pair], None, :2]
    denom = dirs[..., 0] * edge[..., 1] - dirs[..., 1] * edge[..., 0]
    safe = np.where(np.abs(denom) < _PARALLEL, np.nan, denom)
    t = (to_start[..., 0] * edge[..., 1] - to_start[..., 1] * edge[..., 0]) / safe
    u = (to_start[..., 0] * dirs[..., 1] - to_start[..., 1] * dirs[..., 0]) / safe
    valid = (t >= 0.0) & (u >= 0.0) & (u <= 1.0)
    return np.asarray(np.min(np.where(valid, t, np.inf), axis=1), dtype=np.float64)


def fleet_scans(
    cache: StaticScanCache,
    poses: Floats,
    discs: Floats,
    corners: Floats,
    rngs: Sequence[np.random.Generator],
    tick: int = 0,
) -> list[LidarScan]:
    """One scan for every robot. ``poses`` (R, 3), ``discs`` (M, 3), ``corners`` (R, 4, 2).

    ``corners`` holds the footprint corners of every robot. A robot does not see its own.
    ``rngs[r]`` is the noise stream of robot ``r``. The draws match ``sensors.lidar_scan``.
    """
    config = cache.config
    nearest = cache.static_ranges(poses)
    flat = nearest.reshape(-1)
    n = config.n_rays
    if len(discs):
        rows, cols = _candidates(poses, discs[:, :2], discs[:, 2], config.max_range, False)
        if len(rows):
            pair, ray, angle = _windows(poses, discs[:, :2], discs[:, 2], rows, cols, n)
            t = _disc_distances(poses, discs, rows, cols, pair, angle)
            np.minimum.at(flat, rows[pair] * n + ray, t)
    if len(corners) > 1:
        centers = corners.mean(axis=1)
        offsets = corners - centers[:, None, :]
        radii = np.asarray(
            np.max(np.hypot(offsets[..., 0], offsets[..., 1]), axis=1), dtype=np.float64
        )
        rows, cols = _candidates(poses, centers, radii, config.max_range, True)
        if len(rows):
            pair, ray, angle = _windows(poses, centers, radii, rows, cols, n)
            t = _box_distances(poses, corners, rows, cols, pair, angle)
            np.minimum.at(flat, rows[pair] * n + ray, t)
    return [sensors.finish_scan(nearest[r], config, rngs[r], tick, r) for r in range(len(poses))]


def rollout_system(
    cache: StaticScanCache,
    robot_params: Sequence[RobotParams],
    consume: Callable[[Sequence[LidarScan]], None],
) -> System:
    """Engine system: on each lidar tick, scan every robot and pass the scans to ``consume``.

    Reads ground truth, so it belongs to the simulator side (a validator rollout), never to
    control. Robot ``i`` draws its noise from the stream ``lidar/i``.
    """
    half_l = np.array([p.length / 2 for p in robot_params])[:, None]
    half_w = np.array([p.width / 2 for p in robot_params])[:, None]

    def step(sim: state.SimState, rngs: dict[str, np.random.Generator]) -> None:
        if not sensors.lidar_due(sim.tick):
            return
        poses = np.asarray(sim.arrays["robot_pose"], dtype=np.float64)
        people = np.asarray(sim.arrays["human_pos"], dtype=np.float64).reshape(-1, 2)
        discs = np.hstack([people, np.full((len(people), 1), HUMAN_RADIUS)])
        corners = hullgap.corners(half_l, half_w, poses[:, None, :])[:, 0]
        generators = [rngs[f"lidar/{i}"] for i in range(len(poses))]
        consume(fleet_scans(cache, poses, discs, corners, generators, sim.tick))

    return step
