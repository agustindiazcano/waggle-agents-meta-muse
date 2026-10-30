"""Batched exact gaps between swept footprints, the fast path of the detector (ADR-025).

The same quantity as ``detector.robot_human_gap`` and ``detector.robot_robot_gap`` (kept as the
slow reference in the tests), computed for many pairs and many pieces at once with numpy. A
piece is the convex hull of two footprints, given here as its 8 corner points. The hull edges
are the directed point pairs with every other point on their left, so no hull is built. A gap
is zero when no hull edge separates the two shapes (closed sets), and otherwise the smallest
vertex to edge distance. Pieces of one pair are padded by repeating the last piece, which does
not change a minimum.
"""

import math

import numpy as np
from numpy.typing import NDArray

Floats = NDArray[np.float64]
Bools = NDArray[np.bool_]
_EDGE_TOLERANCE = 1e-12
_MIN_EDGE = 1e-9
_I, _J = np.triu_indices(8, k=1)
"""Point pairs (i, j), i < j, that may be hull edges (the direction is decided per pair)."""


def corners(half_l: Floats, half_w: Floats, poses: Floats) -> Floats:
    """Corners (..., 4, 2) of oriented rectangles, counter-clockwise, as ``footprint_corners``."""
    c, s = np.cos(poses[..., 2]), np.sin(poses[..., 2])
    lx = np.stack([half_l, half_l, -half_l, -half_l], axis=-1)
    ly = np.stack([-half_w, half_w, half_w, -half_w], axis=-1)
    x = lx * c[..., None] - ly * s[..., None] + poses[..., 0:1]
    y = lx * s[..., None] + ly * c[..., None] + poses[..., 1:2]
    return np.stack([x, y], axis=-1)


def _cross(ax: Floats, ay: Floats, bx: Floats, by: Floats) -> Floats:
    return np.asarray(ax * by - ay * bx, dtype=np.float64)


def _edges(points: Floats) -> tuple[Floats, Floats, Bools]:
    """Counter-clockwise hull edges of point sets (B, 8, 2).

    Returns the edge start and vector (B, 28, 2) and a validity mask (B, 28).

    A pair is a hull edge when every point is on one side of it. A pair with every point on its
    right is stored reversed, so all valid edges run counter-clockwise.
    """
    start, end = points[:, _I], points[:, _J]
    vec = end - start
    rel = points[:, None, :, :] - start[:, :, None, :]  # (B, 28, 8, 2)
    side = _cross(vec[:, :, None, 0], vec[:, :, None, 1], rel[..., 0], rel[..., 1])
    length = np.hypot(vec[..., 0], vec[..., 1])
    left = np.all(side >= -_EDGE_TOLERANCE, axis=2)
    right = np.all(side <= _EDGE_TOLERANCE, axis=2) & ~left
    valid = (left | right) & (length > _MIN_EDGE)
    flip = right[..., None]
    return np.where(flip, end, start), np.where(flip, -vec, vec), valid


def _point_edge_distance(pts: Floats, start: Floats, vec: Floats, valid: Bools) -> Floats:
    """Smallest distance (B, K) from points (B, K, 2) to the valid edges (B, 56)."""
    rel = pts[:, :, None, :] - start[:, None, :, :]  # (B, K, 56, 2)
    denom = np.sum(vec * vec, axis=-1)[:, None, :]
    f = np.clip(np.sum(rel * vec[:, None, :, :], axis=-1) / np.where(denom > 0, denom, 1.0), 0, 1)
    off = rel - f[..., None] * vec[:, None, :, :]
    dist = np.hypot(off[..., 0], off[..., 1])
    return np.asarray(np.min(np.where(valid[:, None, :], dist, np.inf), axis=2), dtype=np.float64)


def _inside(pts: Floats, start: Floats, vec: Floats, valid: Bools) -> Bools:
    """Whether each point (B, K, 2) is inside or on the hull given by its valid edges."""
    rel = pts[:, :, None, :] - start[:, None, :, :]
    side = _cross(vec[:, None, :, 0], vec[:, None, :, 1], rel[..., 0], rel[..., 1])
    return np.asarray(np.all((side >= 0.0) | ~valid[:, None, :], axis=2), dtype=np.bool_)


def hull_point_gap(hull: Floats, point: Floats) -> Floats:
    """Distance (B,) from points (B, 2) to the hull of point sets (B, 8, 2); zero inside."""
    start, vec, valid = _edges(hull)
    pts = point[:, None, :]
    inside = _inside(pts, start, vec, valid)[:, 0]
    return np.where(inside, 0.0, _point_edge_distance(pts, start, vec, valid)[:, 0])


def _clearance(start: Floats, vec: Floats, valid: Bools, other: Floats) -> Floats:
    """Largest distance (B,) by which one valid edge keeps every point of ``other`` on its right.

    Negative or zero when no edge separates them. This is a lower bound on the hull gap.
    """
    rel = other[:, None, :, :] - start[:, :, None, :]
    side = _cross(vec[:, :, None, 0], vec[:, :, None, 1], rel[..., 0], rel[..., 1])
    length = np.hypot(vec[..., 0], vec[..., 1])
    right = -np.max(side, axis=2) / np.where(length > 0, length, 1.0)
    return np.asarray(np.max(np.where(valid, right, -np.inf), axis=1), dtype=np.float64)


def hull_hull_gap(first: Floats, second: Floats, reduce: Floats | None = None) -> Floats:
    """Distance (B,) between the hulls of two point sets (B, 8, 2); zero when they touch.

    With ``reduce`` (B,), a set pair whose gap is certainly above ``reduce`` is returned as
    that edge clearance (a lower bound above ``reduce``) without the exact distance, which is
    all a caller needs to decide whether ``gap - reduce <= 0``.
    """
    count = len(first)
    both = np.concatenate([first, second])
    start, vec, valid = _edges(both)
    clear = _clearance(start, vec, valid, np.concatenate([second, first]))
    clear = np.maximum(clear[:count], clear[count:])
    out = np.where(clear > 0.0, clear, 0.0)
    need = clear > 0.0 if reduce is None else (clear > 0.0) & (clear <= reduce)
    if np.any(need):
        idx = np.nonzero(need)[0]
        e1 = (start[idx], vec[idx], valid[idx])
        e2 = (start[idx + count], vec[idx + count], valid[idx + count])
        near = np.minimum(
            _point_edge_distance(first[idx], *e2).min(axis=1),
            _point_edge_distance(second[idx], *e1).min(axis=1),
        )
        out[idx] = near
    return out


def pieces_needed(turns: Floats, max_rotation: float) -> NDArray[np.int64]:
    """Pieces per step, as ``detector.pieces_for``, for an array of largest turns."""
    return np.maximum(1, np.ceil(np.abs(turns) / max_rotation)).astype(np.int64)


def ragged_pieces(
    n: NDArray[np.int64],
) -> tuple[NDArray[np.int64], Floats, Floats, NDArray[np.int64]]:
    """Flat piece list for steps cut into ``n`` pieces each (no padding).

    Returns the step index of every piece, its start and end fractions, and the offset of each
    step's first piece, so ``np.minimum.reduceat(values, offsets)`` takes the minimum per step.
    """
    offsets = np.cumsum(n) - n
    step = np.repeat(np.arange(len(n)), n)
    k = np.arange(int(n.sum())) - offsets[step]
    return step, k / n[step], (k + 1) / n[step], offsets


def sagitta(half_diag: Floats, piece_turn: Floats) -> Floats:
    """Rotation sagitta bound (B,) for a piece that turns ``piece_turn``."""
    return np.asarray(half_diag * (1.0 - np.cos(np.abs(piece_turn) / 2.0)), dtype=np.float64)


def wrap(angle: Floats) -> Floats:
    """Wrap angles to [-pi, pi)."""
    return np.asarray((angle + math.pi) % (2 * math.pi) - math.pi, dtype=np.float64)
