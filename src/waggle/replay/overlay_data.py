"""Real viewer overlay geometry derived from simulator state (ADR-093).

Envelopes reuse ``waggle.control.envelope.stop_distance`` with the robot class
parameters and the existing lateral margin; no threshold is introduced or
changed here. Lidar shadows are wedges behind sampled exact lidar hits on the
static map and other robots, using the existing occlusion jump threshold.
Ghost paths are one deterministic fork of the live engine per frame: the fork
is stepped for ``GHOST_HORIZON_S`` and never advances the source engine, and a
ghost passes when the fork records no new detector episode. This module only
reads ground truth for display; it never feeds a control decision.
"""

import itertools
import math

import numpy as np
from numpy.typing import NDArray

from waggle.control import envelope
from waggle.control.params import ControlParams, OcclusionParams
from waggle.sim import frame, params, sensors
from waggle.sim.engine import Engine
from waggle.sim.scenarios import Scenario
from waggle.sim.world import World

Floats = NDArray[np.float64]

SHADOW_SAMPLE_STRIDE = 4
SHADOW_MAX_PER_ROBOT = 8
GHOST_HORIZON_S = 0.5
GHOST_SAMPLE_TICKS = 4
GHOST_K = 1


def _array(sim: Engine, name: str, width: int) -> Floats:
    raw = sim.state.arrays.get(name)
    if raw is None:
        return np.zeros((0, width), dtype=np.float64)
    return np.asarray(raw, dtype=np.float64).reshape(-1, width)


def _corners(
    x: float, y: float, heading: float, length: float, width: float
) -> list[tuple[float, float]]:
    cos_h, sin_h = math.cos(heading), math.sin(heading)
    out: list[tuple[float, float]] = []
    for lx, ly in (
        (-length / 2, -width / 2),
        (length / 2, -width / 2),
        (length / 2, width / 2),
        (-length / 2, width / 2),
    ):
        out.append((x + lx * cos_h - ly * sin_h, y + lx * sin_h + ly * cos_h))
    return out


def _to_world(
    x: float, y: float, heading: float, local: tuple[float, float]
) -> tuple[float, float]:
    cos_h, sin_h = math.cos(heading), math.sin(heading)
    return (x + local[0] * cos_h - local[1] * sin_h, y + local[0] * sin_h + local[1] * cos_h)


def _envelopes(
    sim: Engine, scenario: Scenario, poses: Floats, speeds: Floats
) -> list[frame.EnvelopeOverlay]:
    cp = ControlParams()
    humans = _array(sim, "human_pos", 2)
    out: list[frame.EnvelopeOverlay] = []
    for i, spec in enumerate(scenario.robots):
        p = params.ROBOT_PARAMS[spec.kind]
        x, y, heading = float(poses[i, 0]), float(poses[i, 1]), float(poses[i, 2])
        speed = abs(float(speeds[i])) if i < len(speeds) else 0.0
        front = p.length / 2.0 + envelope.stop_distance(p, speed)
        half_w = p.width / 2.0 + cp.lateral_margin
        polygon = tuple(
            _to_world(x, y, heading, pt)
            for pt in (
                (-p.length / 2.0, -half_w),
                (front, -half_w),
                (front, half_w),
                (-p.length / 2.0, half_w),
            )
        )
        circ = math.hypot(p.length, p.width) / 2.0
        best_gap, nearest = math.inf, None
        for j in range(len(humans)):
            gap = float(np.hypot(humans[j, 0] - x, humans[j, 1] - y)) - circ - params.HUMAN_RADIUS
            if gap < best_gap:
                best_gap, nearest = gap, f"human_{j}"
        for j, other in enumerate(scenario.robots):
            if j == i:
                continue
            op = params.ROBOT_PARAMS[other.kind]
            gap = (
                float(np.hypot(poses[j, 0] - x, poses[j, 1] - y))
                - circ
                - math.hypot(op.length, op.width) / 2.0
            )
            if gap < best_gap:
                best_gap, nearest = gap, f"robot_{j}"
        margin = max(best_gap, 0.0) if nearest is not None else scenario.separation_margin
        out.append(frame.EnvelopeOverlay(f"robot_{i}", polygon, float(margin), nearest))
    return out


def _segments(points: list[tuple[float, float]]) -> list[list[float]]:
    closed = [*points, points[0]]
    return [[a[0], a[1], b[0], b[1]] for a, b in itertools.pairwise(closed)]


def _shadows(
    sim: Engine, scenario: Scenario, world: World, poses: Floats
) -> list[frame.LidarShadowOverlay]:
    config = sensors.LidarConfig()
    jump_min = OcclusionParams().jump_min
    static = sensors.static_segments(world)
    per_robot_segments: list[list[list[float]]] = []
    for i, spec in enumerate(scenario.robots):
        p = params.ROBOT_PARAMS[spec.kind]
        per_robot_segments.append(
            _segments(
                _corners(
                    float(poses[i, 0]), float(poses[i, 1]), float(poses[i, 2]), p.length, p.width
                )
            )
        )
    sampled = np.arange(0, config.n_rays, SHADOW_SAMPLE_STRIDE)
    local_angles = -math.pi + (2 * math.pi / config.n_rays) * sampled
    out: list[frame.LidarShadowOverlay] = []
    for i in range(len(poses)):
        others = [seg for j, segs in enumerate(per_robot_segments) if j != i for seg in segs]
        all_segments = (
            np.vstack([static, np.array(others, dtype=np.float64).reshape(-1, 4)])
            if others
            else static
        )
        x, y, heading = float(poses[i, 0]), float(poses[i, 1]), float(poses[i, 2])
        angles = local_angles + heading
        dirs = np.column_stack([np.cos(angles), np.sin(angles)])
        ranges = sensors.segment_hits(np.array([x, y]), dirs, all_segments)
        wedges: list[tuple[float, tuple[tuple[float, float], ...]]] = []
        for idx in range(len(sampled)):
            nxt = (idx + 1) % len(sampled)
            near_r, far_r = float(ranges[idx]), float(ranges[nxt])
            if not math.isfinite(near_r) or near_r >= config.max_range:
                continue
            if abs(far_r - near_r) < jump_min or far_r <= near_r:
                continue
            near_pt = (x + near_r * float(dirs[idx, 0]), y + near_r * float(dirs[idx, 1]))
            ext_near = (
                x + config.max_range * float(dirs[idx, 0]),
                y + config.max_range * float(dirs[idx, 1]),
            )
            ext_far = (
                x + config.max_range * float(dirs[nxt, 0]),
                y + config.max_range * float(dirs[nxt, 1]),
            )
            wedges.append((near_r, ((x, y), near_pt, ext_near, ext_far)))
        wedges.sort(key=lambda item: item[0])
        for _near, polygon in wedges[:SHADOW_MAX_PER_ROBOT]:
            out.append(frame.LidarShadowOverlay(f"robot_{i}", polygon, SHADOW_SAMPLE_STRIDE))
    return out


def _ghosts(sim: Engine, poses: Floats) -> list[frame.GhostPathOverlay]:
    ticks = round(GHOST_HORIZON_S / params.DT)
    counts_before = (
        int(np.sum(_array(sim, "det_counts", 4))) if "det_counts" in sim.state.arrays else 0
    )
    snapshot_hash = sim.state_hash()
    fork = sim.fork()
    trails: list[list[tuple[float, float]]] = [
        [(float(poses[i, 0]), float(poses[i, 1]))] for i in range(len(poses))
    ]
    for step in range(1, ticks + 1):
        fork.step()
        if step % GHOST_SAMPLE_TICKS == 0 or step == ticks:
            fork_poses = _array(fork, "robot_pose", 3)
            for i in range(len(trails)):
                trails[i].append((float(fork_poses[i, 0]), float(fork_poses[i, 1])))
    counts_after = (
        int(np.sum(_array(fork, "det_counts", 4))) if "det_counts" in fork.state.arrays else 0
    )
    passed = counts_after == counts_before
    return [
        frame.GhostPathOverlay(
            0, f"robot_{i}", passed, tuple(trail), GHOST_K, GHOST_HORIZON_S, snapshot_hash
        )
        for i, trail in enumerate(trails)
        if len(trail) >= 2
    ]


def build_overlays(sim: Engine, scenario: Scenario, world: World) -> frame.FrameOverlays:
    """Envelopes, lidar shadows and ghost paths for the engine at its current tick."""
    poses = _array(sim, "robot_pose", 3)
    if len(poses) == 0 or not scenario.robots:
        return frame.FrameOverlays()
    speeds = _array(sim, "robot_speed", 1).reshape(-1)
    if len(speeds) != len(poses):
        active = _array(sim, "robot_active", 2)
        speeds = active[:, 0] if len(active) else np.zeros(len(poses))
    return frame.FrameOverlays(
        envelopes=tuple(_envelopes(sim, scenario, poses, speeds)),
        lidar_shadows=tuple(_shadows(sim, scenario, world, poses)),
        ghost_paths=tuple(_ghosts(sim, poses)),
    )
