import math

import numpy as np


# Quality-first ceiling for the photographic area: a 0.2 mm nozzle can use a
# full 2001x1501 grid before an optional border is added. High-resolution
# exports intentionally trade RAM and generation time for surface detail.
MAX_GRID_POINTS = 3_100_000


def grid_resolution(width_mm: float, height_mm: float, longest_edge_points: int, border_width_mm: float = 0) -> tuple[int, int]:
    scale = longest_edge_points / max(width_mm, height_mm)
    for _ in range(8):
        cols = max(2, round(width_mm * scale) + 1)
        rows = max(2, round(height_mm * scale) + 1)
        dx = width_mm / (cols - 1)
        dy = height_mm / (rows - 1)
        x_border = max(0, math.ceil(border_width_mm / dx))
        y_border = max(0, math.ceil(border_width_mm / dy))
        total_points = (cols + 2 * x_border) * (rows + 2 * y_border)
        if total_points <= MAX_GRID_POINTS:
            return cols, rows
        scale *= math.sqrt(MAX_GRID_POINTS / total_points) * 0.999
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
