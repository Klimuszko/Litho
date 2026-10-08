from collections.abc import Callable, Iterable

import numpy as np
import shapely
import shapely.affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

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


ICON_MARGIN_MM = 0.3


def _usb_icon():
    """USB trident, 14 mm long; the first axis runs along the housing depth."""
    stroke = 0.45
    parts = [
        LineString([(-6.0, 0), (4.8, 0)]).buffer(stroke),
        Point(-6.0, 0).buffer(1.25),
        Polygon([(4.6, -1.3), (7.0, 0), (4.6, 1.3)]),
        LineString([(-3.4, 0), (-1.1, 2.3), (1.9, 2.3)]).buffer(stroke),
        Point(2.1, 2.3).buffer(0.85),
        LineString([(-1.6, 0), (0.7, -2.3), (3.2, -2.3)]).buffer(stroke),
        box(3.0, -3.1, 4.6, -1.5),
    ]
    return unary_union(parts).simplify(0.01)


def _power_icon():
    """Power symbol, 8 mm across; the second axis points to the housing top."""
    arc = [
        (3.4 * np.cos(np.radians(angle)), 3.4 * np.sin(np.radians(angle)))
        for angle in range(130, 411, 5)
    ]
    parts = [LineString(arc).buffer(0.5), LineString([(0, 0.6), (0, 4.2)]).buffer(0.5)]
    return unary_union(parts).simplify(0.01)


def _engrave_icon(mesh: Mesh, plane_x: float, floor_x: float, icon, bounds: tuple[float, float, float, float]) -> Mesh:
    """Recess a smooth outline into the flat outer side wall.

    The cell faces inside ``bounds`` are replaced by a triangulated plate
    with the icon cut out, vertical recess walls, and the recess floor.
    """
    y0, y1, z0, z1 = bounds
    eps = 1e-4
    vertices = [tuple(map(float, vertex)) for vertex in mesh.vertices]
    corners = mesh.vertices[mesh.faces]
    on_plane = (abs(corners[:, :, 0] - plane_x) < eps).all(axis=1)
    inside = (
        (corners[:, :, 1] > y0 - eps) & (corners[:, :, 1] < y1 + eps)
        & (corners[:, :, 2] > z0 - eps) & (corners[:, :, 2] < z1 + eps)
    ).all(axis=1)
    replaced = on_plane & inside
    edges_y = corners[replaced][:, [1, 2, 0], 1] - corners[replaced][:, [0, 1, 2], 1]
    edges_z = corners[replaced][:, [1, 2, 0], 2] - corners[replaced][:, [0, 1, 2], 2]
    area = abs(edges_y[:, 0] * edges_z[:, 1] - edges_z[:, 0] * edges_y[:, 1]).sum() / 2
    if abs(area - (y1 - y0) * (z1 - z0)) > 1e-2:
        raise ValueError("Icon does not fit on a flat part of the side wall")

    outward = np.array([1.0 if plane_x > floor_x else -1.0, 0.0, 0.0])
    faces: list[tuple[int, int, int]] = []
    index_at: dict[tuple[float, float, float], int] = {}

    def vertex(x: float, y: float, z: float) -> int:
        key = (round(x, 5), round(y, 5), round(z, 5))
        if key not in index_at:
            index_at[key] = len(vertices)
            vertices.append((x, y, z))
        return index_at[key]

    def triangle(a: int, b: int, c: int, normal: np.ndarray) -> None:
        pa, pb, pc = (np.asarray(vertices[index]) for index in (a, b, c))
        faces.append((a, b, c) if np.dot(np.cross(pb - pa, pc - pa), normal) > 0 else (a, c, b))

    # Frame: reuse the existing vertices on the patch outline so the new
    # surface stays edge-to-edge with the surrounding cell faces.
    rim = sorted({int(index) for index in mesh.faces[replaced].ravel()})
    inner = (y0 + ICON_MARGIN_MM, y1 - ICON_MARGIN_MM, z0 + ICON_MARGIN_MM, z1 - ICON_MARGIN_MM)
    sides = (
        (lambda v: abs(v[2] - z0) < eps, lambda v: v[1], (inner[0], inner[2]), (inner[1], inner[2])),
        (lambda v: abs(v[1] - y1) < eps, lambda v: v[2], (inner[1], inner[2]), (inner[1], inner[3])),
        (lambda v: abs(v[2] - z1) < eps, lambda v: -v[1], (inner[1], inner[3]), (inner[0], inner[3])),
        (lambda v: abs(v[1] - y0) < eps, lambda v: -v[2], (inner[0], inner[3]), (inner[0], inner[2])),
    )
    for on_side, along, start, end in sides:
        outline = sorted((index for index in rim if on_side(vertices[index])), key=lambda index: along(vertices[index]))
        a, b = vertex(plane_x, *start), vertex(plane_x, *end)
        for first, second in zip(outline, outline[1:]):
            triangle(first, second, a, outward)
        triangle(a, outline[-1], b, outward)

    icon = orient(icon, 1) if icon.geom_type == "Polygon" else shapely.MultiPolygon([orient(part, 1) for part in icon.geoms])
    plate = box(inner[0], inner[2], inner[1], inner[3]).difference(icon)
    for surface, x in ((plate, plane_x), (icon, floor_x)):
        for part in shapely.constrained_delaunay_triangles(surface).geoms:
            a, b, c = (vertex(x, y, z) for y, z in part.exterior.coords[:3])
            triangle(a, b, c, outward)
    for part in getattr(icon, "geoms", [icon]):
        for ring in (part.exterior, *part.interiors):
            points = list(ring.coords)
            for (ay, az), (by, bz) in zip(points, points[1:]):
                # The recess lies to the left of every oriented outline edge.
                normal = np.array([0.0, az - bz, by - ay])
                top_a, top_b = vertex(plane_x, ay, az), vertex(plane_x, by, bz)
                floor_a, floor_b = vertex(floor_x, ay, az), vertex(floor_x, by, bz)
                triangle(top_a, top_b, floor_b, normal)
                triangle(top_a, floor_b, floor_a, normal)

    all_faces = np.vstack((mesh.faces[~replaced], np.asarray(faces, dtype=np.int32)))
    used = np.unique(all_faces)
    remap = np.full(len(vertices), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    return Mesh(np.asarray(vertices, dtype=np.float32)[used], remap[all_faces])


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
    # Litho Mount V2 adds its mounting flange outside the requested visible
    # image. The front face masks the complete flange, so panel wedges and
    # clips can never cast a visible silhouette through the image area.
    opening_x0 = panel_x0 + params.panel_mask_mm
    opening_x1 = panel_x1 - params.panel_mask_mm
    opening_z0 = panel_z0 + params.panel_mask_mm
    opening_z1 = panel_z1 - params.panel_mask_mm

    clip_y0 = pocket_y0 + params.panel_thickness_mm + params.panel_clip_clearance_mm
    clip_steps = 4
    clip_step_height = params.panel_clip_ramp_height_mm / clip_steps
    clip_ys = [clip_y0 + index * clip_step_height for index in range(clip_steps + 1)]
    clip_reaches = [params.panel_clip_reach_mm * index / clip_steps for index in range(1, clip_steps + 1)]

    vertical_clip_half = params.panel_edge_clip_width_mm(params.panel_outer_height_mm, params.panel_vertical_clip_count) / 2
    horizontal_clip_half = params.panel_edge_clip_width_mm(params.panel_outer_width_mm, params.panel_horizontal_clip_count) / 2
    vertical_clips = [
        (center - vertical_clip_half, center + vertical_clip_half) for center in params.panel_vertical_clip_centers_mm
    ]
    horizontal_clips = [
        (center - horizontal_clip_half, center + horizontal_clip_half) for center in params.panel_horizontal_clip_centers_mm
    ]

    # Rear cover screws enter blind bosses on the top and bottom walls. This
    # keeps every fixing away from the side-mounted USB-C and touch controller.
    back_screw_xs = params.back_screw_centers_x_mm
    back_screw_boss_half = params.back_screw_boss_width_mm / 2
    back_screw_boss_half_z = params.back_screw_boss_reach_mm / 2
    back_screw_zs = (
        wall + back_screw_boss_half_z,
        height - wall - back_screw_boss_half_z,
    )
    back_screw_pilot_half = params.back_screw_pilot_mm / 2
    back_screw_boss_y0 = depth - params.back_screw_boss_depth_mm
    back_screw_pilot_y0 = depth - params.back_screw_pilot_depth_mm

    # The flat side-wall segment before this rib is an uninterrupted 8.5 mm
    # path for an 8 mm COB strip. The rib then grows inward at 45 degrees in
    # 0.4 mm steps. With the front face on the print bed every new step is
    # supported by the previous one, unlike the old horizontal collar.
    stiffener_y0 = params.led_channel_y1_mm
    stiffener_y1 = params.stiffener_y1_mm
    stiffener_reach = params.stiffener_reach_mm
    stiffener_step = params.stiffener_step_mm
    stiffener_steps = int(np.ceil(stiffener_reach / stiffener_step))
    stiffener_reaches = [min(stiffener_reach, index * stiffener_step) for index in range(1, stiffener_steps + 1)]
    stiffener_ys = [stiffener_y0 + reach for reach in stiffener_reaches]

    # The UI names the side as seen from the finished display front. This
    # mesh is assembled from the open rear, so its horizontal axis is mirrored.
    electronics_min_x = params.electronics_on_min_x_wall
    usb_center_y = params.usb_mount_center_y_mm
    usb_center_z = params.usb_mount_center_z_mm
    usb_clearance = params.usb_fit_clearance_mm
    usb_shell_half_y = (params.usb_shell_width_mm + 2 * usb_clearance) / 2
    usb_half_z = params.usb_pocket_half_height_mm
    usb_wall = params.usb_pocket_wall_mm
    usb_aperture_half_y = params.usb_aperture_width_mm / 2
    usb_aperture_half_z = params.usb_aperture_height_mm / 2
    usb_bezel = params.usb_bezel_mm
    # Distances are measured from the inner face of the side wall; the
    # connector nose sits inside the wall, directly behind the bezel.
    usb_front_d = usb_bezel - wall
    usb_shell_end_d = usb_front_d + params.usb_shell_length_mm
    usb_stop_d = usb_front_d + params.usb_total_length_mm + 0.3
    mount_reach = usb_stop_d + 2.0

    # Both pockets are open towards the rear cover: the parts are pushed
    # straight in, and nothing overhangs once the body is printed face down.
    pocket_floor_y = params.electronics_pocket_floor_y_mm
    usb_seat_y = usb_center_y - usb_shell_half_y
    usb_top_y = usb_center_y + usb_shell_half_y
    keepout_y = params.electronics_keepout_y_mm
    gusset_step = 0.4
    gusset_steps = int(np.ceil(mount_reach / gusset_step))

    dimmer_half_y = (params.dimmer_board_width_mm + 2 * usb_clearance) / 2
    dimmer_z0 = params.dimmer_mount_bottom_mm
    dimmer_z1 = params.dimmer_mount_top_mm
    dimmer_end_wall = params.dimmer_end_wall_mm
    # Wide rear stops: each one also houses the tunnel for a locking wedge.
    dimmer_grip = params.wedge_slot_width_mm + 1.2
    dimmer_lip = 0.7
    dimmer_lip_height = 3.0
    dimmer_seat_y = usb_center_y - dimmer_half_y
    dimmer_top_y = usb_center_y + dimmer_half_y
    # The antenna spring presses the board against the rear stop, so the
    # stop alone sets the preload; the front lip only keeps the board upright.
    dimmer_slot_d0 = params.dimmer_board_face_offset_mm - 0.4
    dimmer_slot_d1 = params.dimmer_board_face_offset_mm + params.dimmer_board_thickness_mm
    dimmer_lip_d0 = dimmer_slot_d0 - 1.2
    dimmer_cable_center_d = (dimmer_slot_d0 + dimmer_slot_d1) / 2
    dimmer_cable_d0 = dimmer_cable_center_d - params.dimmer_cable_notch_width_mm / 2
    dimmer_cable_d1 = dimmer_cable_center_d + params.dimmer_cable_notch_width_mm / 2
    dimmer_cable_y0 = dimmer_top_y - params.dimmer_cable_notch_depth_mm

    # The side rib is interrupted only where the electronics occupy the
    # wall. The top, bottom and opposite-side ribs remain continuous, while
    # the USB and dimmer mounts themselves stiffen this short open section.
    electronics_rib_gap_z0 = min(
        usb_center_z - usb_half_z - usb_wall,
        dimmer_z0 - dimmer_end_wall,
    ) - 1.0
    electronics_rib_gap_z1 = max(
        usb_center_z + usb_half_z + usb_wall,
        dimmer_z1 + dimmer_end_wall,
    ) + 1.0

    # Wedge slots sit just above each part; the drop lets the taper bear on
    # the part itself instead of leaving it loose in the pocket.
    wedge_drop = 0.3
    wedge_cap = 3.5
    usb_wedge_half_z = params.usb_wedge_slot_width_mm / 2
    # The USB-C grooves reach below the top of the seated shell, so the wedge
    # rides on the metal and jams against the groove roof about 4.5 mm in.
    usb_shell_top_y = usb_seat_y + params.usb_shell_width_mm
    usb_wedge_y0 = usb_shell_top_y - 0.3
    usb_wedge_y1 = usb_shell_top_y + 1.8
    dimmer_wedge_y0 = dimmer_top_y - wedge_drop
    dimmer_wedge_y1 = dimmer_wedge_y0 + params.wedge_slot_height_mm
    usb_stop_height = 3.0

    icon_plane_x = 0.0 if electronics_min_x else width
    icon_floor_x = params.icon_engrave_depth_mm if electronics_min_x else width - params.icon_engrave_depth_mm
    # (outline, patch bounds as y0, y1, z0, z1) on the outer side wall.
    icons = []
    for outline, center_z, half_y, half_z in (
        (_usb_icon(), params.usb_icon_center_z_mm, 7.9, 3.6),
        (_power_icon(), params.touch_icon_center_z_mm, 5.2, 5.2),
    ):
        icons.append((
            shapely.affinity.translate(outline, usb_center_y, center_z),
            (usb_center_y - half_y, usb_center_y + half_y, center_z - half_z, center_z + half_z),
        ))
    icon_ys = [value for _, bounds in icons for value in bounds[:2]]
    icon_zs = [value for _, bounds in icons for value in bounds[2:]]

    def side_x(distance_from_inner_wall: float) -> float:
        return wall + distance_from_inner_wall if electronics_min_x else width - wall - distance_from_inner_wall

    gusset_ds = [mount_reach - index * gusset_step for index in range(1, gusset_steps)]
    gusset_ys = [pocket_floor_y - index * gusset_step for index in range(1, gusset_steps)]
    usb_xs = [side_x(distance) for distance in (
        usb_front_d, usb_shell_end_d, usb_stop_d, mount_reach, *gusset_ds,
    )]
    usb_ys = [
        keepout_y, pocket_floor_y, usb_seat_y, usb_seat_y + usb_stop_height, usb_top_y,
        usb_wedge_y0, usb_wedge_y1, usb_top_y + wedge_cap,
        usb_center_y - usb_aperture_half_y, usb_center_y + usb_aperture_half_y,
        *(value for value in gusset_ys if value > keepout_y),
    ]
    usb_zs = [
        usb_center_z - usb_half_z - usb_wall, usb_center_z - usb_half_z,
        usb_center_z - usb_aperture_half_z, usb_center_z + usb_aperture_half_z,
        usb_center_z + usb_half_z, usb_center_z + usb_half_z + usb_wall,
        usb_center_z - usb_wedge_half_z, usb_center_z + usb_wedge_half_z,
    ]

    dimmer_xs = [side_x(distance) for distance in (
        dimmer_lip_d0, dimmer_slot_d0, dimmer_slot_d1,
        dimmer_cable_d0, dimmer_cable_d1,
    )]
    dimmer_ys = [
        dimmer_seat_y, dimmer_seat_y + dimmer_lip_height, dimmer_top_y,
        dimmer_wedge_y0, dimmer_wedge_y1, dimmer_top_y + wedge_cap,
        dimmer_cable_y0,
    ]
    dimmer_zs = [
        dimmer_z0 - dimmer_end_wall, dimmer_z0, dimmer_z0 + dimmer_lip, dimmer_z0 + dimmer_grip,
        dimmer_z1 - dimmer_grip, dimmer_z1 - dimmer_lip, dimmer_z1, dimmer_z1 + dimmer_end_wall,
        dimmer_z0 + params.wedge_slot_width_mm, dimmer_z1 - params.wedge_slot_width_mm,
    ]

    clip_xs = [value for interval in horizontal_clips for value in interval]
    clip_zs = [value for interval in vertical_clips for value in interval]
    reach_xs = [pocket_x0 + reach for reach in clip_reaches] + [pocket_x1 - reach for reach in clip_reaches]
    reach_zs = [pocket_z0 + reach for reach in clip_reaches] + [pocket_z1 - reach for reach in clip_reaches]
    flex = params.panel_clip_flex_thickness_mm
    relief = params.panel_clip_relief_mm
    flex_xs = [pocket_x0 - flex - relief, pocket_x0 - flex, pocket_x1 + flex, pocket_x1 + flex + relief]
    flex_zs = [pocket_z0 - flex - relief, pocket_z0 - flex, pocket_z1 + flex, pocket_z1 + flex + relief]

    back_screw_body_xs = [
        center + offset
        for center in back_screw_xs
        for offset in (-back_screw_boss_half, -back_screw_pilot_half, back_screw_pilot_half, back_screw_boss_half)
    ]
    back_screw_body_zs = [
        center + offset
        for center in back_screw_zs
        for offset in (-back_screw_boss_half_z, -back_screw_pilot_half, back_screw_pilot_half, back_screw_boss_half_z)
    ]
    stiffener_xs = [wall + reach for reach in stiffener_reaches] + [width - wall - reach for reach in stiffener_reaches]
    stiffener_zs = [wall + reach for reach in stiffener_reaches] + [height - wall - reach for reach in stiffener_reaches]
    xs = [0, wall, pocket_x0, panel_x0, opening_x0, opening_x1, panel_x1, pocket_x1, width - wall, width, *stiffener_xs, *clip_xs, *reach_xs, *flex_xs, *back_screw_body_xs, *usb_xs, *dimmer_xs]
    clip_release_y1 = clip_ys[-1] + params.panel_clip_end_relief_mm
    ys = [0, bezel_front, pocket_y1, clip_release_y1, params.led_channel_y0_mm, stiffener_y0, stiffener_y1, back_screw_boss_y0, back_screw_pilot_y0, depth, *stiffener_ys, *clip_ys, *usb_ys, *dimmer_ys, *icon_ys]
    zs = [0, wall, pocket_z0, panel_z0, opening_z0, opening_z1, panel_z1, pocket_z1, height - wall, height, *stiffener_zs, *clip_zs, *reach_zs, *flex_zs, *back_screw_body_zs, *usb_zs, *dimmer_zs, *icon_zs]

    lock_xs_centers = params.panel_horizontal_lock_centers_mm
    lock_zs_centers = params.panel_vertical_lock_centers_mm
    lock_depth = params.panel_lock_depth_mm
    lock_block = params.panel_lock_shelf_mm
    lock_half = params.wedge_slot_width_mm / 2
    lock_outer_half = lock_half + params.panel_lock_pier_mm
    # The socket floor sits just above the seated panel, slightly below the
    # shelf, so the wedge tail stops the panel without clamping it.
    lock_y0 = pocket_y0 + params.panel_thickness_mm + params.panel_lock_gap_mm
    lock_y1 = lock_y0 + params.wedge_slot_height_mm
    lock_top_y = lock_y1 + 1.6
    if lock_xs_centers or lock_zs_centers:
        lock_offsets = (-lock_outer_half, -lock_half, lock_half, lock_outer_half)
        xs += [center + offset for center in lock_xs_centers for offset in lock_offsets]
        zs += [center + offset for center in lock_zs_centers for offset in lock_offsets]
        xs += [pocket_x0 - lock_depth, pocket_x0 - lock_block, pocket_x1 + lock_depth, pocket_x1 + lock_block]
        zs += [pocket_z0 - lock_depth, pocket_z0 - lock_block, pocket_z1 + lock_depth, pocket_z1 + lock_block]
        ys += [lock_y0, lock_y1, lock_top_y]

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
        if stiffener_y0 < y < stiffener_y1:
            step = min(int((y - stiffener_y0) / stiffener_step) + 1, stiffener_steps)
            rib_reach = min(stiffener_reach, step * stiffener_step)
            left_rib = x < wall + rib_reach
            right_rib = x > width - wall - rib_reach
            top_bottom_rib = z < wall + rib_reach or z > height - wall - rib_reach
            if electronics_rib_gap_z0 < z < electronics_rib_gap_z1:
                if electronics_min_x:
                    left_rib = False
                    if x < wall + stiffener_reach:
                        top_bottom_rib = False
                else:
                    right_rib = False
                    if x > width - wall - stiffener_reach:
                        top_bottom_rib = False
            perimeter_rib = left_rib or right_rib or top_bottom_rib
            material = material or perimeter_rib
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
        for screw_x in back_screw_xs:
            for screw_z in back_screw_zs:
                in_screw_boss = (
                    abs(x - screw_x) < back_screw_boss_half
                    and abs(z - screw_z) < back_screw_boss_half_z
                    and back_screw_boss_y0 < y < depth
                )
                material = material or in_screw_boss
                if (
                    in_screw_boss
                    and abs(x - screw_x) < back_screw_pilot_half
                    and abs(z - screw_z) < back_screw_pilot_half
                    and back_screw_pilot_y0 < y < depth
                ):
                    material = False

        outer_d = x if electronics_min_x else width - x
        inner_d = x - wall if electronics_min_x else width - wall - x
        usb_z = abs(z - usb_center_z)

        # The side-wall opening is smaller than the measured 8.85 x 3.12 mm
        # metal shell, so the bezel in front of it carries unplugging load.
        in_outer_aperture = (
            0 < outer_d < usb_bezel
            and abs(y - usb_center_y) < usb_aperture_half_y
            and usb_z < usb_aperture_half_z
        )
        # Open to the rear edge so the connector nose can slide down the wall.
        in_shell_slot = usb_bezel < outer_d < wall and usb_z < usb_half_z and y > usb_seat_y
        if in_outer_aperture or in_shell_slot:
            material = False

        if 0 < inner_d < mount_reach:
            # Distance into the board from its nearest end; negative values
            # are the end walls that tie each dimmer channel to the side wall.
            dimmer_end = min(z - dimmer_z0, dimmer_z1 - z)
            in_usb_block = usb_z < usb_half_z + usb_wall
            in_dimmer_block = -dimmer_end_wall < dimmer_end < dimmer_grip

            if in_usb_block and pocket_floor_y < y < usb_top_y:
                usb_floor = y < usb_seat_y
                # The lower wall backs the whole module; the upper one stops
                # at the connector shell so the solder pads stay accessible.
                usb_lower_wall = z < usb_center_z - usb_half_z
                usb_upper_wall = z > usb_center_z + usb_half_z and inner_d < usb_shell_end_d
                # Low stop: soldered wires leave straight back over it.
                usb_end_stop = inner_d > usb_stop_d and y < usb_seat_y + usb_stop_height
                material = material or usb_floor or usb_lower_wall or usb_upper_wall or usb_end_stop

            if in_dimmer_block and pocket_floor_y < y < dimmer_top_y:
                dimmer_end_plate = dimmer_end < 0
                dimmer_floor = y < dimmer_seat_y
                dimmer_rear_stop = inner_d > dimmer_slot_d1
                dimmer_front_lip = (
                    dimmer_end < dimmer_lip
                    and dimmer_lip_d0 < inner_d < dimmer_slot_d0
                    and y < dimmer_seat_y + dimmer_lip_height
                )
                material = material or dimmer_end_plate or dimmer_floor or dimmer_rear_stop or dimmer_front_lip
                # Open U-shaped notches at both board ends let the wires pass
                # through after the PCB is pressed into place. Their lower
                # edge remains solid, so the end walls keep supporting it.
                dimmer_cable_notch = (
                    dimmer_end_plate
                    and dimmer_cable_d0 < inner_d < dimmer_cable_d1
                    and dimmer_cable_y0 < y
                )
                if dimmer_cable_notch:
                    material = False

            # Wedge guides: grooves in both USB-C walls above the shell,
            # and a tunnel through each dimmer rear stop above the board.
            usb_wedge_guide = in_usb_block and usb_z > usb_half_z and inner_d < usb_shell_end_d
            if usb_wedge_guide and usb_top_y <= y < usb_top_y + wedge_cap:
                material = True
            if usb_wedge_guide and usb_wedge_y0 < y < usb_wedge_y1 and usb_z < usb_wedge_half_z:
                material = False
            dimmer_wedge_guide = in_dimmer_block and inner_d > dimmer_slot_d1
            if dimmer_wedge_guide and dimmer_top_y <= y < dimmer_top_y + wedge_cap:
                material = True
            if dimmer_wedge_guide and dimmer_wedge_y0 < y < dimmer_wedge_y1 and 0 < dimmer_end < params.wedge_slot_width_mm:
                material = False

            if (in_usb_block or in_dimmer_block) and keepout_y < y < pocket_floor_y:
                # 45 degree stepped gusset: prints without supports and
                # carries the pockets on the full height of the side wall.
                step = int((pocket_floor_y - y) / gusset_step) + 1
                material = material or inner_d < mount_reach - step * gusset_step

        # Panel wedge sockets: (distance outward from the pocket edge,
        # position along that edge, socket centres on that edge).
        for outward, along, centers in (
            (pocket_x0 - x, z, lock_zs_centers), (x - pocket_x1, z, lock_zs_centers),
            (pocket_z0 - z, x, lock_xs_centers), (z - pocket_z1, x, lock_xs_centers),
        ):
            if not 0 < outward < lock_block:
                continue
            offset = min((abs(along - center) for center in centers), default=lock_outer_half)
            if offset < lock_outer_half and pocket_y1 <= y < lock_top_y:
                material = True
            if offset < lock_half and outward < lock_depth and lock_y0 < y < lock_y1:
                material = False
        return material

    mesh = _cell_mesh(xs, ys, zs, solid)
    for outline, bounds in icons:
        mesh = _engrave_icon(mesh, icon_plane_x, icon_floor_x, outline, bounds)
    return mesh


def build_housing_back(params) -> Mesh:
    width, height = params.outer_width_mm, params.outer_height_mm
    thickness = params.back_thickness_mm
    lip_depth, lip = params.back_lip_depth_mm, params.back_lip_mm
    inset = params.wall_mm + params.back_clearance_mm
    x0, x1, z0, z1 = inset, width - inset, inset, height - inset
    screw_xs = params.back_screw_centers_x_mm
    screw_zs = (
        params.wall_mm + params.back_screw_boss_reach_mm / 2,
        height - params.wall_mm - params.back_screw_boss_reach_mm / 2,
    )
    screw_hole_half = params.back_screw_clearance_mm / 2
    screw_relief_half_x = params.back_screw_boss_width_mm / 2 + params.back_clearance_mm
    screw_relief_half_z = params.back_screw_boss_reach_mm / 2 + params.back_clearance_mm

    rib_margin = params.back_rib_margin_mm
    rib_x0, rib_x1 = rib_margin, width - rib_margin
    rib_z0, rib_z1 = rib_margin, height - rib_margin
    rib_half = params.back_rib_width_mm / 2

    def rib_centers(start: float, end: float) -> list[float]:
        span = end - start
        if span <= 2 * params.back_rib_width_mm:
            return []
        sections = max(1, int(np.ceil(span / params.back_rib_max_spacing_mm)))
        return [start + span * index / sections for index in range(1, sections)]

    vertical_ribs = rib_centers(rib_x0, rib_x1)
    horizontal_ribs = rib_centers(rib_z0, rib_z1)
    screw_grid_xs = [
        center + offset
        for center in screw_xs
        for offset in (-screw_relief_half_x, -screw_hole_half, screw_hole_half, screw_relief_half_x)
    ]
    screw_grid_zs = [
        center + offset
        for center in screw_zs
        for offset in (-screw_relief_half_z, -screw_hole_half, screw_hole_half, screw_relief_half_z)
    ]
    rib_grid_xs = [value for center in vertical_ribs for value in (center - rib_half, center + rib_half)]
    rib_grid_zs = [value for center in horizontal_ribs for value in (center - rib_half, center + rib_half)]
    xs = [0, x0, x0 + lip, x1 - lip, x1, width, rib_x0, rib_x1, *screw_grid_xs, *rib_grid_xs]
    ys = [0, thickness, thickness + params.back_rib_height_mm, thickness + lip_depth]
    zs = [0, z0, z0 + lip, z1 - lip, z1, height, rib_z0, rib_z1, *screw_grid_zs, *rib_grid_zs]

    def solid(x: float, y: float, z: float) -> bool:
        screw_hole = any(
            abs(x - screw_x) < screw_hole_half and abs(z - screw_z) < screw_hole_half
            for screw_x in screw_xs for screw_z in screw_zs
        )
        screw_relief = any(
            abs(x - screw_x) < screw_relief_half_x and abs(z - screw_z) < screw_relief_half_z
            for screw_x in screw_xs for screw_z in screw_zs
        )
        plate = y < thickness and not screw_hole
        ring = (
            thickness < y < thickness + lip_depth
            and x0 < x < x1 and z0 < z < z1
            and (x < x0 + lip or x > x1 - lip or z < z0 + lip or z > z1 - lip)
            and not screw_relief
        )
        rib = (
            thickness < y < thickness + params.back_rib_height_mm
            and rib_x0 < x < rib_x1 and rib_z0 < z < rib_z1
            and (
                any(abs(x - center) < rib_half for center in vertical_ribs)
                or any(abs(z - center) < rib_half for center in horizontal_ribs)
            )
        )
        return plate or ring or rib

    return _cell_mesh(xs, ys, zs, solid)


def build_housing_wedges(params) -> Mesh:
    """Tapered locking wedges, laid flat on the bed side by side."""
    return _wedge_row(
        params.wedge_length_mm, params.wedge_width_mm,
        params.wedge_tip_thickness_mm, params.wedge_head_thickness_mm, params.wedge_count,
    )


def build_housing_panel_wedges(params) -> Mesh:
    """Shorter wedges that lock the Litho panel into the frame sockets."""
    return _wedge_row(
        params.panel_wedge_length_mm, params.wedge_width_mm,
        params.panel_wedge_tip_thickness_mm, params.panel_wedge_head_thickness_mm, params.panel_wedge_count,
    )


def _wedge_row(length: float, width: float, tip: float, head: float, count: int) -> Mesh:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    box = (
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
        (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    )
    for index in range(count):
        y0 = index * (width + 4.0)
        y1 = y0 + width
        base = len(vertices)
        vertices.extend((
            (0, y0, 0), (length, y0, 0), (length, y1, 0), (0, y1, 0),
            (0, y0, tip), (length, y0, head), (length, y1, head), (0, y1, tip),
        ))
        faces.extend((base + a, base + b, base + c) for a, b, c in box)
    return Mesh(np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32))


def orient_front_on_bed(mesh: Mesh) -> Mesh:
    """Rotate width/depth/height assembly axes to width/height/depth for STL."""
    vertices = mesh.vertices[:, [0, 2, 1]].copy()
    # Swapping axes changes handedness, so preserve outward triangle winding.
    faces = mesh.faces[:, [0, 2, 1]].copy()
    return Mesh(vertices.astype(np.float32), faces.astype(np.int32))
