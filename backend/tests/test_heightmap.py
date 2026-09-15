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
