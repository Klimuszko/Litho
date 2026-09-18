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


def _polygon_prism_x(x0: float, x1: float, yz: tuple[tuple[float, float], ...]) -> Mesh:
    """Extrude a convex, counter-clockwise Y/Z polygon between X coordinates."""
    point_count = len(yz)
    if point_count < 3:
        raise ValueError("A prism requires at least three Y/Z points")
    vertices = np.asarray(
        [(x0, y, z) for y, z in yz] + [(x1, y, z) for y, z in yz],
        dtype=np.float32,
    )
    faces: list[tuple[int, int, int]] = []
    for index in range(1, point_count - 1):
        faces.append((0, index + 1, index))
        faces.append((point_count, point_count + index, point_count + index + 1))
    for index in range(point_count):
        following = (index + 1) % point_count
        faces.append((index, following, point_count + following))
        faces.append((index, point_count + following, point_count + index))
    return Mesh(vertices, np.asarray(faces, dtype=np.int32))


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
    brace_height, extension, support_count = removable_support_dimensions(
        height_mm, front_depth_mm, width_mm
    )
    brace_width = min(10.0, width_mm / 8)
    margin = min(10.0, width_mm / 10)
    gap = removable_support_gap(line_width_mm)
    top_wall = max(0.80, 2 * line_width_mm)
    tab_width, tab_height, tab_overlap, pad_height = removable_support_connector_dimensions(line_width_mm)
    parts = [mesh]
    positions = [margin, width_mm - margin - brace_width]
    if support_count == 3:
        positions.insert(1, (width_mm - brace_width) / 2)
    for x0 in positions:
        x1 = x0 + brace_width
        # Keep the wide pads away from the model.  Only a narrow, one-layer
        # neck crosses underneath it, so the foot can snap away cleanly.
        parts.append(_box(x0, x1, -extension, -gap, 0, pad_height))
        parts.append(_box(x0, x1, front_depth_mm + gap, front_depth_mm + extension, 0, pad_height))
        tab_x0 = (x0 + x1 - tab_width) / 2
        tab_x1 = tab_x0 + tab_width
        parts.append(_box(tab_x0, tab_x1, -gap, front_depth_mm + gap, 0, pad_height))
        parts.append(_polygon_prism_x(x0, x1, (
            (-extension, 0), (-gap, 0),
            (-gap, brace_height), (-gap - top_wall, brace_height),
        )))
        parts.append(_polygon_prism_x(x0, x1, (
            (front_depth_mm + gap, 0), (front_depth_mm + extension, 0),
            (front_depth_mm + gap + top_wall, brace_height),
            (front_depth_mm + gap, brace_height),
        )))
        # Three small fuses connect the brace to the reliable flat rear face.
        # Their narrow X/Z section is intentionally much weaker than the old
        # full-width 10 x 2 mm bridges and overlaps the plate only minimally.
        for center_z in (3.0, brace_height * 0.50, brace_height - 3.0):
            z0 = max(pad_height, center_z - tab_height / 2)
            z1 = min(brace_height, center_z + tab_height / 2)
            if z1 > z0:
                parts.append(_box(tab_x0, tab_x1, -gap - 0.05, tab_overlap, z0, z1))
    return combine_meshes(*parts)


def removable_support_connector_dimensions(line_width_mm: float) -> tuple[float, float, float, float]:
    """Return X width, Z height, plate overlap and bottom-neck height."""
    # Slightly stronger than the original 1.76 x 0.40 mm fuse, while remaining
    # only 5% of the old 10 x 2 mm connector cross-section.
    tab_width = max(2.00, 4.5 * line_width_mm)
    tab_height = 0.50
    tab_overlap = 0.18
    pad_height = 0.50
    return tab_width, tab_height, tab_overlap, pad_height


def removable_support_gap(line_width_mm: float) -> float:
    """Clearance from both lithophane faces to the wide feet and braces."""
    return max(0.30, line_width_mm)


def removable_support_dimensions(
    height_mm: float,
    front_depth_mm: float = 3.2,
    width_mm: float | None = None,
) -> tuple[float, float, int]:
    """Compact production support sized for batch printing on a 256 mm bed."""
    # Scale standard formats by their longer side so that rotating the same
    # 150 x 200 mm product does not silently downgrade its support.  The
    # physical-height clamp avoids an oversized brace on unusually wide,
    # shallow custom models.
    reference_size = max(height_mm, width_mm or height_mm)
    desired_height = max(25.0, reference_size * 0.225)
    brace_height = min(45.0, desired_height, max(25.0, height_mm * 0.50))
    desired_extension = min(25.0, max(18.0, reference_size * 0.125))
    extension = min(desired_extension, max(0.0, (55.0 - front_depth_mm) / 2))
    support_count = 3 if reference_size >= 180 and height_mm >= 100 else 2
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
