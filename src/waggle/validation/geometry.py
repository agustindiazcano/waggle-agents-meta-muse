"""Planar geometry for the static checks: segments against axis-aligned boxes, in metres."""

import math
from collections.abc import Sequence

Point = tuple[float, float]
Box = tuple[float, float, float, float]


def polygon_box(points: Sequence[Point]) -> Box:
    """Bounding box (x0, y0, x1, y1) of a polygon. It never shrinks the shape."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _hits(start: Point, end: Point, box: Box) -> bool:
    first, last = 0.0, 1.0
    for origin, target, lower, upper in (
        (start[0], end[0], box[0], box[2]),
        (start[1], end[1], box[1], box[3]),
    ):
        delta = target - origin
        if delta == 0:
            if not lower <= origin <= upper:
                return False
            continue
        near, far = sorted(((lower - origin) / delta, (upper - origin) / delta))
        first, last = max(first, near), min(last, far)
        if first > last:
            return False
    return True


def _point_box(point: Point, box: Box) -> float:
    dx = max(box[0] - point[0], 0.0, point[0] - box[2])
    dy = max(box[1] - point[1], 0.0, point[1] - box[3])
    return math.hypot(dx, dy)


def _point_segment(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    along = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    along = min(1.0, max(0.0, along))
    return math.hypot(point[0] - (start[0] + along * dx), point[1] - (start[1] + along * dy))


def segment_box_distance(start: Point, end: Point, box: Box) -> float:
    """Smallest distance between a closed segment and a closed box, 0 when they touch."""
    if _hits(start, end, box):
        return 0.0
    corners = ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3]))
    return min(
        _point_box(start, box),
        _point_box(end, box),
        *(_point_segment(corner, start, end) for corner in corners),
    )
