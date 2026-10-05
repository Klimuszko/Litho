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

    electronics_left = params.usb_side == "left"
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

    # Wedge slots sit just above each part; the drop lets the taper bear on
    # the part itself instead of leaving it loose in the pocket.
    wedge_drop = 0.3
    wedge_cap = 3.5
    wedge_half_z = params.wedge_slot_width_mm / 2
    usb_wedge_y0 = usb_top_y - wedge_drop
    usb_wedge_y1 = usb_wedge_y0 + params.wedge_slot_height_mm
    dimmer_wedge_y0 = dimmer_top_y - wedge_drop
    dimmer_wedge_y1 = dimmer_wedge_y0 + params.wedge_slot_height_mm
    usb_stop_height = 3.0

    def side_x(distance_from_inner_wall: float) -> float:
        return wall + distance_from_inner_wall if electronics_left else width - wall - distance_from_inner_wall

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
        usb_center_z - wedge_half_z, usb_center_z + wedge_half_z,
    ]

    dimmer_xs = [side_x(distance) for distance in (dimmer_lip_d0, dimmer_slot_d0, dimmer_slot_d1)]
    dimmer_ys = [
        dimmer_seat_y, dimmer_seat_y + dimmer_lip_height, dimmer_top_y,
        dimmer_wedge_y0, dimmer_wedge_y1, dimmer_top_y + wedge_cap,
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

    snap_xs = [value for interval in back_horizontal_snaps for value in interval]
    snap_zs = [value for interval in back_vertical_snaps for value in interval]
    xs = [0, wall - snap_socket_depth, wall, pocket_x0, panel_x0, opening_x0, opening_x1, panel_x1, pocket_x1, width - wall, width - wall + snap_socket_depth, width, *clip_xs, *reach_xs, *flex_xs, *snap_xs, *usb_xs, *dimmer_xs]
    clip_release_y1 = clip_ys[-1] + params.panel_clip_end_relief_mm
    ys = [0, bezel_front, pocket_y1, clip_release_y1, depth, snap_y0, snap_y1, *clip_ys, *usb_ys, *dimmer_ys]
    zs = [0, wall - snap_socket_depth, wall, pocket_z0, panel_z0, opening_z0, opening_z1, panel_z1, pocket_z1, height - wall, height - wall + snap_socket_depth, height, *clip_zs, *reach_zs, *flex_zs, *snap_zs, *usb_zs, *dimmer_zs]

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

        outer_d = x if electronics_left else width - x
        inner_d = x - wall if electronics_left else width - wall - x
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

            # Wedge guides: grooves in both USB-C walls above the shell,
            # and a tunnel through each dimmer rear stop above the board.
            usb_wedge_guide = in_usb_block and usb_z > usb_half_z and inner_d < usb_shell_end_d
            if usb_wedge_guide and usb_top_y <= y < usb_top_y + wedge_cap:
                material = True
            if usb_wedge_guide and usb_wedge_y0 < y < usb_wedge_y1 and usb_z < wedge_half_z:
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
        return material

    return _cell_mesh(xs, ys, zs, solid)


def build_housing_back(params) -> Mesh:
    width, height = params.outer_width_mm, params.outer_height_mm
    thickness = params.back_thickness_mm
    lip_depth, lip = params.back_lip_depth_mm, params.back_lip_mm
    inset = params.wall_mm + params.back_clearance_mm
    x0, x1, z0, z1 = inset, width - inset, inset, height - inset
    horizontal_snaps = _centered_intervals(
        x0, x1, params.back_horizontal_snap_count, params.back_snap_width_mm,
    )
    vertical_snaps = _centered_intervals(
        z0, z1, params.back_vertical_snap_count, params.back_snap_width_mm,
    )
    snap_y0, snap_y1 = thickness + 1.0, thickness + 2.0

    snap_xs = [value for interval in horizontal_snaps for value in interval]
    snap_zs = [value for interval in vertical_snaps for value in interval]
    xs = [0, x0 - params.back_snap_reach_mm, x0, x0 + lip, x1 - lip, x1, x1 + params.back_snap_reach_mm, width, *snap_xs]
    ys = [0, thickness, thickness + lip_depth, snap_y0, snap_y1]
    zs = [0, z0 - params.back_snap_reach_mm, z0, z0 + lip, z1 - lip, z1, z1 + params.back_snap_reach_mm, height, *snap_zs]

    def solid(x: float, y: float, z: float) -> bool:
        plate = y < thickness
        ring = (
            thickness < y < thickness + lip_depth
            and x0 < x < x1 and z0 < z < z1
            and (x < x0 + lip or x > x1 - lip or z < z0 + lip or z > z1 - lip)
        )
        snap = (
            snap_y0 < y < snap_y1
            and (
                any(start < x < end for start, end in horizontal_snaps)
                and (x0 - params.back_snap_reach_mm < z < z0 + lip or z1 - lip < z < z1 + params.back_snap_reach_mm)
                or any(start < z < end for start, end in vertical_snaps)
                and (x0 - params.back_snap_reach_mm < x < x0 + lip or x1 - lip < x < x1 + params.back_snap_reach_mm)
            )
        )
        return plate or ring or snap

    return _cell_mesh(xs, ys, zs, solid)


def build_housing_wedges(params) -> Mesh:
    """Tapered locking wedges, laid flat on the bed side by side."""
    length, width = params.wedge_length_mm, params.wedge_width_mm
    tip, head = params.wedge_tip_thickness_mm, params.wedge_head_thickness_mm
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    box = (
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
        (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    )
    for index in range(params.wedge_count):
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
