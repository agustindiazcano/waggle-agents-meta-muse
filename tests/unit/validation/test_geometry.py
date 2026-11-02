"""Exact distance from a straight segment to an axis-aligned rectangle."""

import math

import pytest

from waggle.validation.geometry import polygon_box, segment_box_distance

BOX = (0.0, 0.0, 2.0, 2.0)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ((-3.0, 1.0), (-1.0, 1.0), 1.0),
        ((-3.0, 5.0), (5.0, 5.0), 3.0),
        ((-1.0, -1.0), (-1.0, 4.0), 1.0),
        ((3.0, 3.0), (3.0, 3.0), math.sqrt(2.0)),
        ((-2.0, 1.0), (4.0, 1.0), 0.0),
        ((1.0, 1.0), (1.5, 1.5), 0.0),
        ((2.0, 5.0), (2.0, 3.0), 1.0),
        ((-1.0, 3.0), (3.0, -1.0), 0.0),
        ((-2.0, 0.0), (0.0, -2.0), math.sqrt(2.0)),
    ],
)
def test_distance_matches_hand_computed_values(
    start: tuple[float, float], end: tuple[float, float], expected: float
) -> None:
    assert segment_box_distance(start, end, BOX) == pytest.approx(expected)
    assert segment_box_distance(end, start, BOX) == pytest.approx(expected)


def test_a_segment_that_only_touches_the_boundary_has_zero_distance() -> None:
    assert segment_box_distance((2.0, -1.0), (2.0, 5.0), BOX) == 0.0


def test_polygon_box_is_the_bounding_box() -> None:
    assert polygon_box(((1.0, 4.0), (3.0, 4.0), (3.0, 9.0), (1.0, 9.0))) == (1.0, 4.0, 3.0, 9.0)
