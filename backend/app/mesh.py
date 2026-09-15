from dataclasses import dataclass
from collections import Counter

import numpy as np


@dataclass(frozen=True)
class Mesh:
    vertices: np.ndarray
    faces: np.ndarray


def build_plate(heightmap: np.ndarray, width_mm: float, height_mm: float) -> Mesh:
    rows, cols = heightmap.shape
    if rows < 2 or cols < 2:
        raise ValueError("Heightmap must contain at least 2x2 samples")
    xs = np.linspace(0, width_mm, cols, dtype=np.float32)
    ys = np.linspace(0, height_mm, rows, dtype=np.float32)
    xx, zz = np.meshgrid(xs, ys)
    # Export the lithophane standing upright: X=width, Y=thickness, Z=height.
    # Image rows grow downwards, therefore the heightmap is flipped along Z.
    thickness = np.flipud(heightmap).ravel()
    front = np.column_stack((xx.ravel(), thickness, zz.ravel()))
    back = np.column_stack((xx.ravel(), np.zeros(rows * cols, dtype=np.float32), zz.ravel()))
    vertices = np.vstack((front, back)).astype(np.float32)
    n = rows * cols
    faces: list[tuple[int, int, int]] = []

    def t(i: int, j: int) -> int: return i * cols + j
    def b(i: int, j: int) -> int: return n + i * cols + j

    for i in range(rows - 1):
        for j in range(cols - 1):
            v00, v01, v10, v11 = t(i, j), t(i, j + 1), t(i + 1, j), t(i + 1, j + 1)
            faces.extend(((v00, v11, v10), (v00, v01, v11)))
            b00, b01, b10, b11 = b(i, j), b(i, j + 1), b(i + 1, j), b(i + 1, j + 1)
            faces.extend(((b00, b10, b11), (b00, b11, b01)))

    # Bottom (-Z), top (+Z), left (-X), right (+X).
    for j in range(cols - 1):
        faces.extend(((t(0, j), b(0, j + 1), t(0, j + 1)), (t(0, j), b(0, j), b(0, j + 1))))
        faces.extend(((t(rows - 1, j), t(rows - 1, j + 1), b(rows - 1, j + 1)), (t(rows - 1, j), b(rows - 1, j + 1), b(rows - 1, j))))
    for i in range(rows - 1):
        faces.extend(((t(i, 0), t(i + 1, 0), b(i + 1, 0)), (t(i, 0), b(i + 1, 0), b(i, 0))))
        faces.extend(((t(i, cols - 1), b(i + 1, cols - 1), t(i + 1, cols - 1)), (t(i, cols - 1), b(i, cols - 1), b(i + 1, cols - 1))))
    # Swapping the former Y/Z axes changes handedness, so reverse every triangle
    # to keep outward normals and a positive signed volume.
    face_array = np.asarray(faces, dtype=np.int32)[:, [0, 2, 1]]
    return Mesh(vertices, face_array)


def apply_border(heightmap: np.ndarray, width_mm: float, height_mm: float, border_width_mm: float, border_height_mm: float) -> tuple[np.ndarray, float, float]:
    if border_width_mm <= 0:
        return heightmap, width_mm, height_mm
    rows, cols = heightmap.shape
    dx = width_mm / (cols - 1)
    dy = height_mm / (rows - 1)
    x_cells = max(1, int(np.ceil(border_width_mm / dx)))
    y_cells = max(1, int(np.ceil(border_width_mm / dy)))
    framed = np.pad(heightmap, ((y_cells, y_cells), (x_cells, x_cells)), constant_values=border_height_mm)
    # The requested photo dimensions stay intact; the border increases the model footprint.
    return framed.astype(np.float32), width_mm + 2 * border_width_mm, height_mm + 2 * border_width_mm


def validate_mesh(mesh: Mesh) -> dict[str, int | bool]:
    faces = mesh.faces
    edges = Counter(tuple(sorted(edge)) for face in faces for edge in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])))
    directed = Counter(edge for face in faces for edge in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])))
    tri = mesh.vertices[faces]
    areas2 = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    winding_errors = sum(
        directed[(a, b)] != directed[(b, a)] for a, b in edges if a < b
    )
    signed_volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
    return {
        "watertight": bool(edges and all(count == 2 for count in edges.values())),
        "boundary_edges": sum(count != 2 for count in edges.values()),
        "degenerate_faces": int(np.count_nonzero(areas2 <= 1e-8)),
        "winding_errors": winding_errors,
        "positive_volume": signed_volume > 0,
    }
