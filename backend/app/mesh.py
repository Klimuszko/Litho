from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Mesh:
    vertices: np.ndarray
    faces: np.ndarray


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Mesh:
    vertices = np.asarray([
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ], dtype=np.float32)
    faces = np.asarray([
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
        (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5),
    ], dtype=np.int32)
    return Mesh(vertices, faces)


def combine_meshes(*meshes: Mesh) -> Mesh:
    vertices: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0
    for mesh in meshes:
        vertices.append(mesh.vertices)
        faces.append(mesh.faces + offset)
        offset += len(mesh.vertices)
    return Mesh(np.vstack(vertices).astype(np.float32), np.vstack(faces).astype(np.int32))


def _triangular_prism_x(x0: float, x1: float, yz: tuple[tuple[float, float], ...]) -> Mesh:
    """Extrude a counter-clockwise Y/Z triangle between two X coordinates."""
    if len(yz) != 3:
        raise ValueError("A triangular prism requires exactly three Y/Z points")
    vertices = np.asarray(
        [(x0, y, z) for y, z in yz] + [(x1, y, z) for y, z in yz],
        dtype=np.float32,
    )
    faces = np.asarray([
        (0, 2, 1), (3, 4, 5),
        (0, 1, 4), (0, 4, 3),
        (1, 2, 5), (1, 5, 4),
        (2, 0, 3), (2, 3, 5),
    ], dtype=np.int32)
    return Mesh(vertices, faces)


def add_removable_support(
    mesh: Mesh,
    width_mm: float,
    height_mm: float,
    front_depth_mm: float,
    line_width_mm: float,
) -> Mesh:
    """Add two breakaway A-frame braces for an upright lithophane.

    The brace dimensions scale with model height. Small tabs rather than a
    continuous wall connect each brace to the model, making removal practical.
    """
    brace_height, extension, support_count = removable_support_dimensions(height_mm, front_depth_mm)
    brace_width = min(10.0, width_mm / 8)
    margin = min(10.0, width_mm / 10)
    gap = max(0.30, line_width_mm)
    tab_depth = 2 * line_width_mm
    pad_height = 0.40
    parts = [mesh]
    positions = [margin, width_mm - margin - brace_width]
    if support_count == 3:
        positions.insert(1, (width_mm - brace_width) / 2)
    for x0 in positions:
        x1 = x0 + brace_width
        # A thin local pad joins the front and rear braces at bed level.
        parts.append(_box(x0, x1, -extension, front_depth_mm + extension, 0, pad_height))
        parts.append(_triangular_prism_x(x0, x1, ((-extension, 0), (-gap, 0), (-gap, brace_height))))
        parts.append(_triangular_prism_x(x0, x1, ((front_depth_mm + gap, 0), (front_depth_mm + extension, 0), (front_depth_mm + gap, brace_height))))
        # Three short bridges form a perforated break line on the reliable flat
        # rear surface. They are limited to two extrusion lines in depth.
        for center_z in (3.0, brace_height * 0.50, brace_height - 3.0):
            z0 = max(pad_height, center_z - 1.0)
            z1 = min(brace_height, center_z + 1.0)
            if z1 > z0:
                parts.append(_box(x0, x1, -gap - 0.05, tab_depth, z0, z1))
    return combine_meshes(*parts)


def removable_support_dimensions(height_mm: float, front_depth_mm: float = 3.2) -> tuple[float, float, int]:
    """Compact production support sized for batch printing on a 256 mm bed."""
    brace_height = min(45.0, max(25.0, height_mm * 0.225))
    desired_extension = min(25.0, max(18.0, height_mm * 0.125))
    extension = min(desired_extension, max(0.0, (55.0 - front_depth_mm) / 2))
    support_count = 3 if height_mm >= 180 else 2
    return brace_height, extension, support_count


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
    raw_edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    low = np.minimum(raw_edges[:, 0], raw_edges[:, 1]).astype(np.uint64)
    high = np.maximum(raw_edges[:, 0], raw_edges[:, 1]).astype(np.uint64)
    records = np.empty(len(raw_edges), dtype=[("key", "<u8"), ("forward", "?")])
    records["key"] = (low << np.uint64(32)) | high
    records["forward"] = raw_edges[:, 0] == low
    del raw_edges, low, high
    records.sort(order="key")
    keys = records["key"]
    starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    counts = np.diff(np.r_[starts, len(keys)])
    boundary_edges = int(np.count_nonzero(counts != 2))
    paired = counts == 2
    pair_starts = starts[paired]
    winding_errors = int(np.count_nonzero(records["forward"][pair_starts] == records["forward"][pair_starts + 1]))

    degenerate_faces = 0
    signed_volume = 0.0
    chunk_size = 200_000
    for offset in range(0, len(faces), chunk_size):
        tri = mesh.vertices[faces[offset:offset + chunk_size]]
        cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        degenerate_faces += int(np.count_nonzero(np.einsum("ij,ij->i", cross, cross) <= 1e-16))
        signed_volume += float(np.einsum("ij,ij->i", tri[:, 0], cross).sum() / 6.0)
    return {
        "watertight": bool(len(keys) and boundary_edges == 0),
        "boundary_edges": boundary_edges,
        "degenerate_faces": degenerate_faces,
        "winding_errors": winding_errors,
        "positive_volume": signed_volume > 0,
    }
