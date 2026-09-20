from collections.abc import Callable, Iterable

import numpy as np

from .mesh import Mesh


def _unique(values: Iterable[float]) -> list[float]:
    return sorted({round(float(value), 6) for value in values})


def _centered_intervals(start: float, end: float, count: int, width: float) -> list[tuple[float, float]]:
    span = end - start
    # Keep the mandatory two-per-edge layout usable for very small custom
    # housings without overlapping adjacent flexible features.
    effective_width = min(width, span / (count + 1) * 0.8)
    half = effective_width / 2
    return [
        (start + span * index / (count + 1) - half, start + span * index / (count + 1) + half)
        for index in range(1, count + 1)
    ]


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

    clip_y0 = pocket_y0 + params.panel_thickness_mm + params.panel_clip_clearance_mm
    clip_steps = 4
    clip_step_height = params.panel_clip_ramp_height_mm / clip_steps
    clip_ys = [clip_y0 + index * clip_step_height for index in range(clip_steps + 1)]
    clip_reaches = [params.panel_clip_reach_mm * index / clip_steps for index in range(1, clip_steps + 1)]

    vertical_clips = _centered_intervals(
        panel_z0, panel_z1, params.panel_vertical_clip_count, params.panel_clip_width_mm,
    )
    horizontal_clips = _centered_intervals(
        panel_x0, panel_x1, params.panel_horizontal_clip_count, params.panel_clip_width_mm,
    )

    back_horizontal_snaps = _centered_intervals(
        wall, width - wall, params.back_horizontal_snap_count, params.back_snap_width_mm,
    )
    back_vertical_snaps = _centered_intervals(
        wall, height - wall, params.back_vertical_snap_count, params.back_snap_width_mm,
    )
    snap_y0, snap_y1 = depth - 2.1, depth - 0.9
    snap_socket_depth = 0.25

    clip_xs = [value for interval in horizontal_clips for value in interval]
    clip_zs = [value for interval in vertical_clips for value in interval]
    reach_xs = [pocket_x0 + reach for reach in clip_reaches] + [pocket_x1 - reach for reach in clip_reaches]
    reach_zs = [pocket_z0 + reach for reach in clip_reaches] + [pocket_z1 - reach for reach in clip_reaches]
    flex = params.panel_clip_flex_thickness_mm
    relief = params.panel_clip_relief_mm
    flex_xs = [pocket_x0 - flex - relief, pocket_x0 - flex, pocket_x1 + flex, pocket_x1 + flex + relief]
    flex_zs = [pocket_z0 - flex - relief, pocket_z0 - flex, pocket_z1 + flex, pocket_z1 + flex + relief]

    snap_xs = [value for interval in back_horizontal_snaps for value in interval]
    snap_zs = [value for interval in back_vertical_snaps for value in interval]
    xs = [0, wall - snap_socket_depth, wall, pocket_x0, panel_x0, opening_x0, opening_x1, panel_x1, pocket_x1, width - wall, width - wall + snap_socket_depth, width, *clip_xs, *reach_xs, *flex_xs, *snap_xs]
    clip_release_y1 = clip_ys[-1] + params.panel_clip_end_relief_mm
    ys = [0, bezel_front, pocket_y1, clip_release_y1, depth, snap_y0, snap_y1, *clip_ys]
    zs = [0, wall - snap_socket_depth, wall, pocket_z0, panel_z0, opening_z0, opening_z1, panel_z1, pocket_z1, height - wall, height - wall + snap_socket_depth, height, *clip_zs, *reach_zs, *flex_zs, *snap_zs]

    def in_intervals(value: float, intervals: list[tuple[float, float]]) -> bool:
        return any(start < value < end for start, end in intervals)

    def clip_reach_at(y: float) -> float:
        if not clip_y0 < y < clip_ys[-1]:
            return 0.0
        # The hook is deepest nearest the panel, then retracts in four
        # 0.2 mm steps to form a support-free insertion ramp.
        step = min(int((y - clip_y0) / clip_step_height), clip_steps - 1)
        return params.panel_clip_reach_mm * (clip_steps - step) / clip_steps

    def solid(x: float, y: float, z: float) -> bool:
        material = x < wall or x > width - wall or z < wall or z > height - wall
        if y < bezel_front:
            opening = opening_x0 < x < opening_x1 and opening_z0 < z < opening_z1
            material = material or not opening
        if pocket_y0 < y < pocket_y1:
            pocket = pocket_x0 < x < pocket_x1 and pocket_z0 < z < pocket_z1
            material = material or not pocket
        clip_active = bezel_front < y < clip_ys[-1]
        side_span = in_intervals(z, vertical_clips)
        top_bottom_span = in_intervals(x, horizontal_clips)
        if clip_active:
            side_fin = side_span and (
                pocket_x0 - flex < x < pocket_x0 or pocket_x1 < x < pocket_x1 + flex
            )
            top_bottom_fin = top_bottom_span and (
                pocket_z0 - flex < z < pocket_z0 or pocket_z1 < z < pocket_z1 + flex
            )
            material = material or side_fin or top_bottom_fin

        reach = clip_reach_at(y)
        if reach:
            side_clip = side_span and (
                pocket_x0 < x < pocket_x0 + reach or pocket_x1 - reach < x < pocket_x1
            )
            top_bottom_clip = top_bottom_span and (
                pocket_z0 < z < pocket_z0 + reach or pocket_z1 - reach < z < pocket_z1
            )
            material = material or side_clip or top_bottom_clip

        if clip_active:
            side_relief = side_span and (
                pocket_x0 - flex - relief < x < pocket_x0 - flex
                or pocket_x1 + flex < x < pocket_x1 + flex + relief
            )
            top_bottom_relief = top_bottom_span and (
                pocket_z0 - flex - relief < z < pocket_z0 - flex
                or pocket_z1 + flex < z < pocket_z1 + flex + relief
            )
            if side_relief or top_bottom_relief:
                material = False
        if clip_ys[-1] < y < clip_release_y1:
            side_end_relief = side_span and (
                pocket_x0 - flex - relief < x < pocket_x0
                or pocket_x1 < x < pocket_x1 + flex + relief
            )
            top_bottom_end_relief = top_bottom_span and (
                pocket_z0 - flex - relief < z < pocket_z0
                or pocket_z1 < z < pocket_z1 + flex + relief
            )
            if side_end_relief or top_bottom_end_relief:
                material = False
        if snap_y0 < y < snap_y1:
            rear_snap_socket = (
                in_intervals(x, back_horizontal_snaps)
                and (wall - snap_socket_depth < z < wall or height - wall < z < height - wall + snap_socket_depth)
                or in_intervals(z, back_vertical_snaps)
                and (wall - snap_socket_depth < x < wall or width - wall < x < width - wall + snap_socket_depth)
            )
            if rear_snap_socket:
                material = False
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

    horizontal_snaps = _centered_intervals(
        x0, x1, params.back_horizontal_snap_count, params.back_snap_width_mm,
    )
    vertical_snaps = _centered_intervals(
        z0, z1, params.back_vertical_snap_count, params.back_snap_width_mm,
    )
    snap_y0, snap_y1 = thickness + 1.0, thickness + 2.0

    snap_xs = [value for interval in horizontal_snaps for value in interval]
    snap_zs = [value for interval in vertical_snaps for value in interval]
    xs = [0, x0 - params.back_snap_reach_mm, x0, x0 + lip, cable_x0, cable_x1, x1 - lip, x1, x1 + params.back_snap_reach_mm, width, *snap_xs]
    ys = [0, thickness, thickness + lip_depth, snap_y0, snap_y1]
    zs = [0, params.cable_height_mm, z0 - params.back_snap_reach_mm, z0, z0 + lip, z1 - lip, z1, z1 + params.back_snap_reach_mm, height, *snap_zs]

    def solid(x: float, y: float, z: float) -> bool:
        cable_notch = cable_x0 < x < cable_x1 and z < params.cable_height_mm
        plate = y < thickness and not cable_notch
        ring = (
            thickness < y < thickness + lip_depth
            and x0 < x < x1 and z0 < z < z1
            and (x < x0 + lip or x > x1 - lip or z < z0 + lip or z > z1 - lip)
            and not cable_notch
        )
        snap = (
            snap_y0 < y < snap_y1
            and (
                any(start < x < end for start, end in horizontal_snaps)
                and (x0 - params.back_snap_reach_mm < z < z0 + lip or z1 - lip < z < z1 + params.back_snap_reach_mm)
                or any(start < z < end for start, end in vertical_snaps)
                and (x0 - params.back_snap_reach_mm < x < x0 + lip or x1 - lip < x < x1 + params.back_snap_reach_mm)
            )
            and not cable_notch
        )
        return plate or ring or snap

    return _cell_mesh(xs, ys, zs, solid)


def orient_front_on_bed(mesh: Mesh) -> Mesh:
    """Rotate width/depth/height assembly axes to width/height/depth for STL."""
    vertices = mesh.vertices[:, [0, 2, 1]].copy()
    # Swapping axes changes handedness, so preserve outward triangle winding.
    faces = mesh.faces[:, [0, 2, 1]].copy()
    return Mesh(vertices.astype(np.float32), faces.astype(np.int32))
