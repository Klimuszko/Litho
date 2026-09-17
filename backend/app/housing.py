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
    slot_y0, slot_y1 = params.slot_y0_mm, params.slot_y1_mm
    groove, bezel_front = params.groove_capture_mm, params.front_thickness_mm

    xs = [0, wall, panel_x0, panel_x0 + groove, panel_x1 - groove, panel_x1, width - wall, width]
    ys = [0, bezel_front, slot_y0, slot_y1, slot_y1 + groove, depth]
    zs = [0, wall, panel_z0, panel_z0 + groove, panel_z1 - groove, panel_z1, height - wall, height]

    def solid(x: float, y: float, z: float) -> bool:
        material = x < wall or x > width - wall or z < wall or z > height - wall
        if params.kind == "frame" and y < bezel_front:
            opening = (
                panel_x0 + params.bezel_overlap_mm < x < panel_x1 - params.bezel_overlap_mm
                and panel_z0 + params.bezel_overlap_mm < z < panel_z1 - params.bezel_overlap_mm
            )
            material = material or not opening

        in_panel_y = slot_y0 < y < slot_y1
        side_channel = (
            (panel_x0 < x < panel_x0 + groove or panel_x1 - groove < x < panel_x1)
            and panel_z0 < z < height
        )
        bottom_channel = panel_x0 < x < panel_x1 and panel_z0 < z < panel_z0 + groove
        top_entry = panel_x0 < x < panel_x1 and panel_z1 < z < height
        if in_panel_y and (side_channel or bottom_channel or top_entry):
            material = False

        in_rear_guide = slot_y1 < y < slot_y1 + groove
        guide = (
            (x < panel_x0 + groove or x > panel_x1 - groove)
            and panel_z0 < z < panel_z1
        ) or (panel_x0 < x < panel_x1 and z < panel_z0 + groove)
        return material or (in_rear_guide and guide)

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
