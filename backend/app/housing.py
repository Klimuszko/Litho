from collections.abc import Callable, Iterable

import numpy as np

from .mesh import Mesh


def _unique(values: Iterable[float]) -> list[float]:
    return sorted({round(float(value), 6) for value in values})


def _cell_mesh(
    xs: Iterable[float], ys: Iterable[float], zs: Iterable[float],
    solid_at: Callable[[float, float, float], bool],
) -> Mesh:
    """Build an exact watertight boundary from axis-aligned CSG cells."""
    xv, yv, zv = _unique(xs), _unique(ys), _unique(zs)
    nx, ny, nz = len(xv) - 1, len(yv) - 1, len(zv) - 1
    occupied = np.zeros((nx, ny, nz), dtype=bool)
    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                occupied[ix, iy, iz] = solid_at(
                    (xv[ix] + xv[ix + 1]) / 2,
                    (yv[iy] + yv[iy + 1]) / 2,
                    (zv[iz] + zv[iz + 1]) / 2,
                )

    vertices: list[tuple[float, float, float]] = []
    vertex_ids: dict[tuple[float, float, float], int] = {}
    faces: list[tuple[int, int, int]] = []

    def vertex(point: tuple[float, float, float]) -> int:
        if point not in vertex_ids:
            vertex_ids[point] = len(vertices)
            vertices.append(point)
        return vertex_ids[point]

    def quad(points: tuple[tuple[float, float, float], ...]) -> None:
        a, b, c, d = (vertex(point) for point in points)
        faces.extend(((a, b, c), (a, c, d)))

    for ix, iy, iz in np.argwhere(occupied):
        x0, x1 = xv[ix], xv[ix + 1]
        y0, y1 = yv[iy], yv[iy + 1]
        z0, z1 = zv[iz], zv[iz + 1]
        if ix == 0 or not occupied[ix - 1, iy, iz]:
            quad(((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)))
        if ix == nx - 1 or not occupied[ix + 1, iy, iz]:
            quad(((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)))
        if iy == 0 or not occupied[ix, iy - 1, iz]:
            quad(((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)))
        if iy == ny - 1 or not occupied[ix, iy + 1, iz]:
            quad(((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)))
        if iz == 0 or not occupied[ix, iy, iz - 1]:
            quad(((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)))
        if iz == nz - 1 or not occupied[ix, iy, iz + 1]:
            quad(((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)))

    return Mesh(np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32))


def build_housing_body(params) -> Mesh:
    width, height, depth = params.outer_width_mm, params.outer_height_mm, params.body_depth_mm
    wall = params.wall_mm
    panel_x0, panel_x1 = params.panel_x0_mm, params.panel_x1_mm
    panel_z0, panel_z1 = params.panel_z0_mm, params.panel_z1_mm
    pocket_y0 = params.front_thickness_mm
    pocket_y1 = pocket_y0 + params.panel_pocket_depth_mm
    bezel_front = params.front_thickness_mm
    pocket_x0 = panel_x0 - params.clearance_mm / 2
    pocket_x1 = panel_x1 + params.clearance_mm / 2
    pocket_z0 = panel_z0 - params.clearance_mm / 2
    pocket_z1 = panel_z1 + params.clearance_mm / 2
    opening_x0 = panel_x0 + params.effective_bezel_overlap_mm
    opening_x1 = panel_x1 - params.effective_bezel_overlap_mm
    opening_z0 = panel_z0 + params.effective_bezel_overlap_mm
    opening_z1 = panel_z1 - params.effective_bezel_overlap_mm

    xs = [0, wall, pocket_x0, panel_x0, opening_x0, opening_x1, panel_x1, pocket_x1, width - wall, width]
    ys = [0, bezel_front, pocket_y1, depth]
    zs = [0, wall, pocket_z0, panel_z0, opening_z0, opening_z1, panel_z1, pocket_z1, height - wall, height]

    def solid(x: float, y: float, z: float) -> bool:
        material = x < wall or x > width - wall or z < wall or z > height - wall
        if y < bezel_front:
            opening = opening_x0 < x < opening_x1 and opening_z0 < z < opening_z1
            material = material or not opening
        if pocket_y0 < y < pocket_y1:
            pocket = pocket_x0 < x < pocket_x1 and pocket_z0 < z < pocket_z1
            material = material or not pocket
        return material

    return _cell_mesh(xs, ys, zs, solid)


def build_housing_back(params) -> Mesh:
    width, height = params.outer_width_mm, params.outer_height_mm
    thickness = params.back_thickness_mm
    lip_depth, lip = params.back_lip_depth_mm, params.back_lip_mm
    inset = params.wall_mm + params.back_clearance_mm
    x0, x1, z0, z1 = inset, width - inset, inset, height - inset
    cable_x0 = (width - params.cable_width_mm) / 2
    cable_x1 = cable_x0 + params.cable_width_mm

    xs = [0, x0, x0 + lip, cable_x0, cable_x1, x1 - lip, x1, width]
    ys = [0, thickness, thickness + lip_depth]
    zs = [0, params.cable_height_mm, z0, z0 + lip, z1 - lip, z1, height]

    def solid(x: float, y: float, z: float) -> bool:
        cable_notch = cable_x0 < x < cable_x1 and z < params.cable_height_mm
        plate = y < thickness and not cable_notch
        ring = (
            thickness < y < thickness + lip_depth
            and x0 < x < x1 and z0 < z < z1
            and (x < x0 + lip or x > x1 - lip or z < z0 + lip or z > z1 - lip)
            and not cable_notch
        )
        return plate or ring

    return _cell_mesh(xs, ys, zs, solid)


def orient_front_on_bed(mesh: Mesh) -> Mesh:
    """Rotate width/depth/height assembly axes to width/height/depth for STL."""
    vertices = mesh.vertices[:, [0, 2, 1]].copy()
    # Swapping axes changes handedness, so preserve outward triangle winding.
    faces = mesh.faces[:, [0, 2, 1]].copy()
    return Mesh(vertices.astype(np.float32), faces.astype(np.int32))
