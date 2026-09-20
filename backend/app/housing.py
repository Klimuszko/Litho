from collections.abc import Callable, Iterable

import numpy as np

from .mesh import Mesh


def _unique(values: Iterable[float]) -> list[float]:
    return sorted({round(float(value), 6) for value in values})


def _circle_breaks(center: float, radius: float, segments: int = 20) -> list[float]:
    """Axis breakpoints for a fine, deterministic FDM-friendly circle approximation."""
    angles = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    return [center - radius, center + radius, *(center + radius * np.cos(angles))]


def _centered_intervals(start: float, end: float, count: int, width: float) -> list[tuple[float, float]]:
    half = width / 2
    span = end - start
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

    back_horizontal_snaps = _centered_intervals(wall, width - wall, 2, params.back_snap_width_mm)
    back_vertical_snaps = _centered_intervals(wall, height - wall, 1, params.back_snap_width_mm)
    snap_y0, snap_y1 = depth - 2.1, depth - 0.9
    snap_socket_depth = 0.25
    magnet_contact_y = depth - (params.magnet_pocket_depth_mm + 0.6)
    magnet_post_y0 = magnet_contact_y - 6.0
    magnet_pocket_y0 = magnet_contact_y - params.magnet_pocket_depth_mm
    magnet_centers = [
        (params.magnet_center_inset_mm, params.magnet_center_inset_mm),
        (width - params.magnet_center_inset_mm, params.magnet_center_inset_mm),
        (params.magnet_center_inset_mm, height - params.magnet_center_inset_mm),
        (width - params.magnet_center_inset_mm, height - params.magnet_center_inset_mm),
    ]

    clip_xs = [value for interval in horizontal_clips for value in interval]
    clip_zs = [value for interval in vertical_clips for value in interval]
    reach_xs = [pocket_x0 + reach for reach in clip_reaches] + [pocket_x1 - reach for reach in clip_reaches]
    reach_zs = [pocket_z0 + reach for reach in clip_reaches] + [pocket_z1 - reach for reach in clip_reaches]
    flex = params.panel_clip_flex_thickness_mm
    relief = params.panel_clip_relief_mm
    flex_xs = [pocket_x0 - flex - relief, pocket_x0 - flex, pocket_x1 + flex, pocket_x1 + flex + relief]
    flex_zs = [pocket_z0 - flex - relief, pocket_z0 - flex, pocket_z1 + flex, pocket_z1 + flex + relief]

    magnet_xs = [value for cx, _ in magnet_centers for value in _circle_breaks(cx, params.magnet_boss_radius_mm)]
    magnet_zs = [value for _, cz in magnet_centers for value in _circle_breaks(cz, params.magnet_boss_radius_mm)]
    magnet_hole_xs = [value for cx, _ in magnet_centers for value in _circle_breaks(cx, params.magnet_pocket_diameter_mm / 2)]
    magnet_hole_zs = [value for _, cz in magnet_centers for value in _circle_breaks(cz, params.magnet_pocket_diameter_mm / 2)]
    bridge_xs = [value for cx, _ in magnet_centers for value in (cx - 2.0, cx, cx + 2.0)]
    bridge_zs = [value for _, cz in magnet_centers for value in (cz - 2.0, cz, cz + 2.0)]
    snap_xs = [value for interval in back_horizontal_snaps for value in interval]
    snap_zs = [value for interval in back_vertical_snaps for value in interval]
    xs = [0, wall - snap_socket_depth, wall, pocket_x0, panel_x0, opening_x0, opening_x1, panel_x1, pocket_x1, width - wall, width - wall + snap_socket_depth, width, *clip_xs, *reach_xs, *flex_xs, *snap_xs, *magnet_xs, *magnet_hole_xs, *bridge_xs]
    clip_release_y1 = clip_ys[-1] + params.panel_clip_end_relief_mm
    ys = [0, bezel_front, pocket_y1, clip_release_y1, depth, snap_y0, snap_y1, magnet_post_y0, magnet_pocket_y0, magnet_contact_y, *clip_ys]
    zs = [0, wall - snap_socket_depth, wall, pocket_z0, panel_z0, opening_z0, opening_z1, panel_z1, pocket_z1, height - wall, height - wall + snap_socket_depth, height, *clip_zs, *reach_zs, *flex_zs, *snap_zs, *magnet_zs, *magnet_hole_zs, *bridge_zs]

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
        if params.magnets:
            in_boss = any((x - cx) ** 2 + (z - cz) ** 2 < params.magnet_boss_radius_mm ** 2 for cx, cz in magnet_centers)
            in_pocket = any((x - cx) ** 2 + (z - cz) ** 2 < (params.magnet_pocket_diameter_mm / 2) ** 2 for cx, cz in magnet_centers)
            bridge_half_width = 2.0
            in_bridge = any(
                (
                    (wall < x < cx if cx < width / 2 else cx < x < width - wall)
                    and cz - bridge_half_width < z < cz + bridge_half_width
                    or (wall < z < cz if cz < height / 2 else cz < z < height - wall)
                    and cx - bridge_half_width < x < cx + bridge_half_width
                )
                for cx, cz in magnet_centers
            )
            if magnet_post_y0 < y < magnet_contact_y and in_boss:
                material = True
            if magnet_post_y0 < y < depth - params.back_lip_depth_mm and in_bridge:
                material = True
            if magnet_pocket_y0 < y < magnet_contact_y and in_pocket:
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

    horizontal_snaps = _centered_intervals(x0, x1, 2, params.back_snap_width_mm)
    vertical_snaps = _centered_intervals(z0, z1, 1, params.back_snap_width_mm)
    snap_y0, snap_y1 = thickness + 1.0, thickness + 2.0
    magnet_boss_depth = params.magnet_pocket_depth_mm + 0.6
    magnet_centers = [
        (params.magnet_center_inset_mm, params.magnet_center_inset_mm),
        (width - params.magnet_center_inset_mm, params.magnet_center_inset_mm),
        (params.magnet_center_inset_mm, height - params.magnet_center_inset_mm),
        (width - params.magnet_center_inset_mm, height - params.magnet_center_inset_mm),
    ]

    snap_xs = [value for interval in horizontal_snaps for value in interval]
    snap_zs = [value for interval in vertical_snaps for value in interval]
    magnet_xs = [value for cx, _ in magnet_centers for value in _circle_breaks(cx, params.magnet_boss_radius_mm)]
    magnet_zs = [value for _, cz in magnet_centers for value in _circle_breaks(cz, params.magnet_boss_radius_mm)]
    hole_xs = [value for cx, _ in magnet_centers for value in _circle_breaks(cx, params.magnet_pocket_diameter_mm / 2)]
    hole_zs = [value for _, cz in magnet_centers for value in _circle_breaks(cz, params.magnet_pocket_diameter_mm / 2)]
    xs = [0, x0 - params.back_snap_reach_mm, x0, x0 + lip, cable_x0, cable_x1, x1 - lip, x1, x1 + params.back_snap_reach_mm, width, *snap_xs, *magnet_xs, *hole_xs]
    ys = [0, thickness, thickness + lip_depth, snap_y0, snap_y1, thickness + 0.6, thickness + magnet_boss_depth]
    zs = [0, params.cable_height_mm, z0 - params.back_snap_reach_mm, z0, z0 + lip, z1 - lip, z1, z1 + params.back_snap_reach_mm, height, *snap_zs, *magnet_zs, *hole_zs]

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
        material = plate or ring or snap
        if params.magnets:
            in_boss = any((x - cx) ** 2 + (z - cz) ** 2 < params.magnet_boss_radius_mm ** 2 for cx, cz in magnet_centers)
            in_pocket = any((x - cx) ** 2 + (z - cz) ** 2 < (params.magnet_pocket_diameter_mm / 2) ** 2 for cx, cz in magnet_centers)
            if thickness < y < thickness + magnet_boss_depth and in_boss:
                material = True
            if thickness + 0.6 < y < thickness + magnet_boss_depth and in_pocket:
                material = False
        return material

    return _cell_mesh(xs, ys, zs, solid)


def orient_front_on_bed(mesh: Mesh) -> Mesh:
    """Rotate width/depth/height assembly axes to width/height/depth for STL."""
    vertices = mesh.vertices[:, [0, 2, 1]].copy()
    # Swapping axes changes handedness, so preserve outward triangle winding.
    faces = mesh.faces[:, [0, 2, 1]].copy()
    return Mesh(vertices.astype(np.float32), faces.astype(np.int32))
