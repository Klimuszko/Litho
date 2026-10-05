from dataclasses import dataclass
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
    # Build the regular grid in NumPy. A Python tuple per triangle becomes
    # prohibitively expensive at the quality-first 1200-point setting.
    base = np.arange((rows - 1) * (cols - 1), dtype=np.int32)
    row = base // (cols - 1)
    col = base % (cols - 1)
    v00 = row * cols + col
    v01 = v00 + 1
    v10 = v00 + cols
    v11 = v10 + 1
    top_faces = np.stack((
        np.stack((v00, v11, v10), axis=1),
        np.stack((v00, v01, v11), axis=1),
    ), axis=1)
    bottom_faces = np.stack((
        np.stack((n + v00, n + v10, n + v11), axis=1),
        np.stack((n + v00, n + v11, n + v01), axis=1),
    ), axis=1)
    grid_faces = np.concatenate((top_faces, bottom_faces), axis=1).reshape(-1, 3)
    sides: list[tuple[int, int, int]] = []

    def t(i: int, j: int) -> int: return i * cols + j
    def b(i: int, j: int) -> int: return n + i * cols + j

    # Bottom (-Z), top (+Z), left (-X), right (+X).
    for j in range(cols - 1):
        sides.extend(((t(0, j), b(0, j + 1), t(0, j + 1)), (t(0, j), b(0, j), b(0, j + 1))))
        sides.extend(((t(rows - 1, j), t(rows - 1, j + 1), b(rows - 1, j + 1)), (t(rows - 1, j), b(rows - 1, j + 1), b(rows - 1, j))))
    for i in range(rows - 1):
        sides.extend(((t(i, 0), t(i + 1, 0), b(i + 1, 0)), (t(i, 0), b(i + 1, 0), b(i, 0))))
        sides.extend(((t(i, cols - 1), b(i + 1, cols - 1), t(i + 1, cols - 1)), (t(i, cols - 1), b(i, cols - 1), b(i + 1, cols - 1))))
    # Swapping the former Y/Z axes changes handedness, so reverse every triangle
    # to keep outward normals and a positive signed volume.
    face_array = np.vstack((grid_faces, np.asarray(sides, dtype=np.int32)))[:, [0, 2, 1]]
    return Mesh(vertices, face_array)


def apply_border(
    heightmap: np.ndarray,
    width_mm: float,
    height_mm: float,
    border_width_mm: float,
    border_height_mm: float,
    border_widths_mm: tuple[float, float, float, float] | None = None,
) -> tuple[np.ndarray, float, float]:
    top, right, bottom, left = border_widths_mm or (border_width_mm,) * 4
    if not any(value > 0 for value in (top, right, bottom, left)):
        return heightmap, width_mm, height_mm
    rows, cols = heightmap.shape
    dx = width_mm / (cols - 1)
    dy = height_mm / (rows - 1)
    left_cells = int(np.ceil(left / dx)) if left > 0 else 0
    right_cells = int(np.ceil(right / dx)) if right > 0 else 0
    top_cells = int(np.ceil(top / dy)) if top > 0 else 0
    bottom_cells = int(np.ceil(bottom / dy)) if bottom > 0 else 0
    framed = np.pad(heightmap, ((top_cells, bottom_cells), (left_cells, right_cells)), constant_values=border_height_mm)
    # The caller passes the inner image dimensions; adding the border restores
    # the selected final model dimensions.
    return framed.astype(np.float32), width_mm + left + right, height_mm + top + bottom


def validate_mesh(mesh: Mesh) -> dict[str, int | bool]:
    faces = mesh.faces
    # Encode the undirected edge and its direction into one uint64. Vertex IDs
    # stay below 2**31 (MAX_GRID_POINTS is ~6.2M), leaving the top bit free for
    # the direction flag after packing two 32-bit IDs. Sorting a plain numeric
    # array is much faster than NumPy structured-record sorting
    # and reduces peak memory for multi-million-triangle production meshes.
    encoded = np.empty(len(faces) * 3, dtype=np.uint64)
    for edge_index, (left_index, right_index) in enumerate(((0, 1), (1, 2), (2, 0))):
        left = faces[:, left_index]
        right = faces[:, right_index]
        low = np.minimum(left, right).astype(np.uint64)
        high = np.maximum(left, right).astype(np.uint64)
        key = (low << np.uint64(32)) | high
        start = edge_index * len(faces)
        encoded[start:start + len(faces)] = (key << np.uint64(1)) | (left == low)
    encoded.sort()
    same_edge = (encoded[1:] >> np.uint64(1)) == (encoded[:-1] >> np.uint64(1))
    starts = np.flatnonzero(np.r_[True, ~same_edge])
    counts = np.diff(np.r_[starts, len(encoded)])
    boundary_edges = int(np.count_nonzero(counts != 2))
    paired = counts == 2
    pair_starts = starts[paired]
    winding_errors = int(np.count_nonzero(
        (encoded[pair_starts] & np.uint64(1)) == (encoded[pair_starts + 1] & np.uint64(1))
    ))

    degenerate_faces = 0
    signed_volume = 0.0
    chunk_size = 200_000
    for offset in range(0, len(faces), chunk_size):
        tri = mesh.vertices[faces[offset:offset + chunk_size]]
        cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        degenerate_faces += int(np.count_nonzero(np.einsum("ij,ij->i", cross, cross) <= 1e-16))
        signed_volume += float(np.einsum("ij,ij->i", tri[:, 0], cross).sum() / 6.0)
    return {
        "watertight": bool(len(encoded) and boundary_edges == 0),
        "boundary_edges": boundary_edges,
        "degenerate_faces": degenerate_faces,
        "winding_errors": winding_errors,
        "positive_volume": signed_volume > 0,
    }
