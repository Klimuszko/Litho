import math

import numpy as np


# Quality-first ceiling for the photographic area: the 200x150 mm preset can
# use a full 1201x901 grid before an optional border is added. High-resolution
# exports intentionally trade RAM and generation time for surface detail.
MAX_GRID_POINTS = 1_100_000


def grid_resolution(width_mm: float, height_mm: float, longest_edge_points: int) -> tuple[int, int]:
    scale = longest_edge_points / max(width_mm, height_mm)
    cols = max(2, round(width_mm * scale) + 1)
    rows = max(2, round(height_mm * scale) + 1)
    points = rows * cols
    if points > MAX_GRID_POINTS:
        factor = math.sqrt(MAX_GRID_POINTS / points)
        cols = max(2, int(cols * factor))
        rows = max(2, int(rows * factor))
    return cols, rows


def luminance_to_thickness(
    luminance: np.ndarray,
    min_thickness_mm: float,
    max_thickness_mm: float,
    gamma: float,
    invert: bool = False,
) -> np.ndarray:
    light = np.clip(luminance, 0.0, 1.0)
    if invert:
        light = 1.0 - light
    thickness = min_thickness_mm + np.power(1.0 - light, gamma) * (
        max_thickness_mm - min_thickness_mm
    )
    return thickness.astype(np.float32)
