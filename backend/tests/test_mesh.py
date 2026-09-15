import struct

import numpy as np
from hypothesis import given, strategies as st

from app.exporter import binary_stl
from app.mesh import apply_border, build_plate, validate_mesh


@given(
    rows=st.integers(min_value=2, max_value=12),
    cols=st.integers(min_value=2, max_value=12),
    values=st.lists(st.floats(min_value=0.4, max_value=5, allow_nan=False, allow_infinity=False), min_size=144, max_size=144),
)
def test_generated_plate_is_watertight(rows, cols, values):
    heightmap = np.asarray(values[: rows * cols], dtype=np.float32).reshape(rows, cols)
    result = validate_mesh(build_plate(heightmap, 100, 80))
    assert result == {"watertight": True, "boundary_edges": 0, "degenerate_faces": 0, "winding_errors": 0, "positive_volume": True}


def test_binary_stl_length_and_count():
    mesh = build_plate(np.ones((2, 2), dtype=np.float32), 10, 10)
    stl = binary_stl(mesh)
    assert len(stl) == 84 + 50 * len(mesh.faces)
    assert struct.unpack("<I", stl[80:84])[0] == len(mesh.faces)


def test_face_normals_point_outward_on_flat_plate():
    mesh = build_plate(np.ones((2, 2), dtype=np.float32), 10, 8)
    tri = mesh.vertices[mesh.faces]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    assert np.all(normals[0:2, 2] > 0)
    assert np.all(normals[2:4, 2] < 0)
    assert np.all(normals[4:6, 1] < 0)
    assert np.all(normals[6:8, 1] > 0)
    assert np.all(normals[8:10, 0] < 0)
    assert np.all(normals[10:12, 0] > 0)


def test_border_expands_model_without_overwriting_photo():
    source = np.arange(20, dtype=np.float32).reshape(4, 5) + 1
    framed, width, height = apply_border(source, 100, 75, 5, 4)
    assert (width, height) == (110, 85)
    assert np.array_equal(framed[1:-1, 1:-1], source)
    assert np.all(framed[0] == 4)
