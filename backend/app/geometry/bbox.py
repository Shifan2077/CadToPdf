from __future__ import annotations

from typing import Iterable, Tuple


def bounding_box_for_points(points: Iterable[Tuple[float, float]]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) for the supplied points."""
    xs: list[float] = []
    ys: list[float] = []

    for x, y in points:
        xs.append(float(x))
        ys.append(float(y))

    if not xs or not ys:
        raise ValueError("At least one point is required to calculate a bounding box")

    return (min(xs), min(ys), max(xs), max(ys))
