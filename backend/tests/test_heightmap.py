import numpy as np

from app.heightmap import grid_resolution, luminance_to_thickness


def test_mapping_endpoints_and_gamma():
    lum = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
    result = luminance_to_thickness(lum, 0.8, 3.2, 2.0)
    assert np.allclose(result, [[3.2, 1.4, 0.8]])


def test_invert_swaps_endpoints():
    result = luminance_to_thickness(np.array([[0.0, 1.0]]), 1, 4, 1, True)
    assert np.allclose(result, [[1, 4]])


def test_grid_preserves_physical_aspect():
    cols, rows = grid_resolution(100, 50, 200)
    assert (cols, rows) == (201, 101)


def test_maximum_quality_keeps_full_resolution_for_largest_preset():
    cols, rows = grid_resolution(200, 150, 1200)
    assert (cols, rows) == (1201, 901)


def test_point_two_nozzle_can_use_full_maximum_grid():
    cols, rows = grid_resolution(200, 150, 2000)
    assert (cols, rows) == (2001, 1501)


def test_border_is_included_in_global_point_budget():
    cols, rows = grid_resolution(200, 150, 2000, border_width_mm=20)
    dx = 200 / (cols - 1)
    dy = 150 / (rows - 1)
    x_border = int(np.ceil(20 / dx))
    y_border = int(np.ceil(20 / dy))
    assert (cols + 2 * x_border) * (rows + 2 * y_border) <= 3_100_000


def test_asymmetric_borders_are_included_in_global_point_budget():
    borders = (3, 17, 11, 5)
    cols, rows = grid_resolution(178, 136, 2000, border_widths_mm=borders)
    dx = 178 / (cols - 1)
    dy = 136 / (rows - 1)
    top, right, bottom, left = borders
    total_cols = cols + int(np.ceil(left / dx)) + int(np.ceil(right / dx))
    total_rows = rows + int(np.ceil(top / dy)) + int(np.ceil(bottom / dy))
    assert total_cols * total_rows <= 3_100_000
