from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.housing import (
    build_housing_back, build_housing_body, build_housing_panel_wedges, build_housing_wedges, orient_front_on_bed,
)
from app.main import app
from app.mesh import validate_mesh
from app.models import HousingParams


client = TestClient(app)


def component_count(mesh) -> int:
    parent = list(range(len(mesh.vertices)))

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for a, b, c in mesh.faces:
        union(int(a), int(b)); union(int(b), int(c))
    return len({find(index) for index in range(len(mesh.vertices))})


@pytest.mark.parametrize("kind", ["box", "frame"])
def test_housing_parts_are_watertight_manifold_solids(kind):
    params = HousingParams(kind=kind)
    for mesh in (build_housing_body(params), build_housing_back(params)):
        validation = validate_mesh(mesh)
        assert validation == {
            "watertight": True,
            "boundary_edges": 0,
            "degenerate_faces": 0,
            "winding_errors": 0,
            "positive_volume": True,
        }
        assert component_count(mesh) == 1


def test_box_and_frame_derive_outer_size_from_exact_panel_size():
    box = HousingParams(kind="box", panel_width_mm=150, panel_height_mm=100)
    frame = HousingParams(kind="frame", panel_width_mm=150, panel_height_mm=100)
    assert (box.outer_width_mm, box.outer_height_mm) == pytest.approx((155.6, 105.6))
    assert (frame.outer_width_mm, frame.outer_height_mm) == pytest.approx((174, 124))
    assert box.panel_pocket_depth_mm == pytest.approx(2.0)
    assert frame.panel_pocket_depth_mm == pytest.approx(2.0)
    assert (box.rear_opening_width_mm, box.rear_opening_height_mm) == pytest.approx((150.8, 100.8))
    assert build_housing_body(box).vertices[:, 1].max() == pytest.approx(37.6)


@pytest.mark.parametrize("width,height,expected", [
    (150, 100, 10), (180, 130, 14), (200, 150, 14), (100, 150, 10), (130, 180, 14),
])
def test_integrated_clip_count_scales_with_panel(width, height, expected):
    params = HousingParams(panel_width_mm=width, panel_height_mm=height)
    assert params.panel_clip_count == expected
    assert params.panel_clip_reach_mm == pytest.approx(0.4)
    assert params.panel_clip_ramp_height_mm == pytest.approx(0.8)
    assert params.panel_clip_flex_thickness_mm == pytest.approx(0.8)
    assert params.panel_clip_relief_mm == pytest.approx(0.6)


def test_largest_preset_has_four_clips_per_long_edge_and_three_per_short_edge():
    params = HousingParams(panel_width_mm=200, panel_height_mm=150)
    assert params.panel_horizontal_clip_count == 4
    assert params.panel_vertical_clip_count == 3
    assert params.panel_clip_count == 14


def test_every_edge_has_at_least_two_panel_and_back_fasteners():
    params = HousingParams(panel_width_mm=60, panel_height_mm=60)
    assert params.panel_horizontal_clip_count == 2
    assert params.panel_vertical_clip_count == 2
    assert params.back_horizontal_snap_count >= 2
    assert params.back_vertical_snap_count >= 2


def test_rear_snap_has_positive_engagement_with_clearance_and_blind_socket():
    params = HousingParams()
    insertion_gap = params.back_clearance_mm
    engagement = params.back_snap_reach_mm - insertion_gap
    socket_depth = 0.25
    assert engagement == pytest.approx(0.2)
    assert socket_depth - engagement == pytest.approx(0.05)
    assert params.wall_mm - socket_depth >= 2.0


def test_clip_hook_reaches_over_panel_edge_at_controlled_clearance():
    params = HousingParams(panel_width_mm=150, panel_height_mm=100)
    mesh = build_housing_body(params)
    hook_y = params.front_thickness_mm + params.panel_thickness_mm + params.panel_clip_clearance_mm
    left_hook_tip = params.panel_x0_mm - params.clearance_mm / 2 + params.panel_clip_reach_mm
    clip_center_z = (
        params.panel_z0_mm
        + params.panel_height_mm / (params.panel_vertical_clip_count + 1)
    )
    vertices = mesh.vertices
    assert any(
        x == pytest.approx(left_hook_tip)
        and y == pytest.approx(hook_y)
        and z == pytest.approx(clip_center_z - params.panel_clip_width_mm / 2)
        for x, y, z in vertices
    )
    assert left_hook_tip - params.panel_x0_mm == pytest.approx(0.2)


@pytest.mark.parametrize("builder", [build_housing_body, build_housing_back])
def test_export_orientation_places_front_flat_on_print_bed(builder):
    assembly_mesh = builder(HousingParams(kind="box"))
    print_mesh = orient_front_on_bed(assembly_mesh)
    assert print_mesh.vertices[:, 2].min() == pytest.approx(0)
    assert print_mesh.vertices[:, 2].max() == pytest.approx(assembly_mesh.vertices[:, 1].max())
    validation = validate_mesh(print_mesh)
    assert validation["watertight"]
    assert validation["winding_errors"] == 0


def test_housing_rejects_dimensions_outside_p1s_bed():
    with pytest.raises(ValidationError, match="256 x 256"):
        HousingParams(kind="frame", panel_width_mm=240, panel_height_mm=150)


def test_usb_c_side_mount_rejects_too_shallow_or_too_short_housing():
    with pytest.raises(ValidationError, match="at least 27 mm"):
        HousingParams(depth_mm=26)
    shallow = HousingParams(depth_mm=27)
    assert shallow.electronics_pocket_floor_y_mm >= shallow.electronics_keepout_y_mm
    with pytest.raises(ValidationError, match="too short"):
        HousingParams(panel_height_mm=40)


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("position", ["bottom", "top"])
def test_usb_c_and_touch_dimmer_mounts_are_mandatory_and_single_manifold_body(side, position):
    params = HousingParams(usb_side=side, electronics_position=position)
    mesh = build_housing_body(params)
    assert validate_mesh(mesh) == {
        "watertight": True,
        "boundary_edges": 0,
        "degenerate_faces": 0,
        "winding_errors": 0,
        "positive_volume": True,
    }
    assert component_count(mesh) == 1

    expected_outer_x = 0 if side == "left" else params.outer_width_mm
    aperture_y = params.usb_mount_center_y_mm - params.usb_aperture_width_mm / 2
    aperture_z = params.usb_mount_center_z_mm - params.usb_aperture_height_mm / 2
    assert any(
        x == pytest.approx(expected_outer_x)
        and y == pytest.approx(aperture_y)
        and z == pytest.approx(aperture_z)
        for x, y, z in mesh.vertices
    )


def test_usb_c_pocket_matches_measured_module_and_is_open_to_the_rear():
    params = HousingParams(usb_side="left")
    mesh = build_housing_body(params)
    xs = {round(float(x), 3) for x in mesh.vertices[:, 0]}
    bezel = params.usb_bezel_mm
    # Bezel-to-stop length is the measured 14.02 mm module plus 0.3 mm play.
    assert round(bezel + params.usb_total_length_mm + 0.3, 3) in xs
    assert round(bezel + params.usb_shell_length_mm, 3) in xs
    # The shell slot in the wall runs out through the rear edge of the body.
    slot_z = params.usb_mount_center_z_mm - params.usb_pocket_half_height_mm
    assert any(
        x == pytest.approx(bezel) and y == pytest.approx(params.body_depth_mm) and z == pytest.approx(slot_z)
        for x, y, z in mesh.vertices
    )


def test_touch_dimmer_channels_preload_the_antenna_spring_against_the_wall():
    params = HousingParams(usb_side="left")
    mesh = build_housing_body(params)
    xs = {round(float(x), 3) for x in mesh.vertices[:, 0]}
    rear_stop = params.wall_mm + params.dimmer_board_face_offset_mm + params.dimmer_board_thickness_mm
    assert round(rear_stop, 3) in xs
    assert params.dimmer_spring_height_mm - params.dimmer_board_face_offset_mm == pytest.approx(0.4)
    # Channels stand outside both board ends and clear the USB-C pocket.
    assert params.dimmer_mount_top_mm - params.dimmer_mount_bottom_mm == pytest.approx(37.54)
    assert params.dimmer_mount_bottom_mm - params.dimmer_end_wall_mm > params.usb_mount_top_mm


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("position", ["bottom", "top"])
def test_usb_and_touch_icons_are_engraved_on_the_outer_side_wall(side, position):
    params = HousingParams(usb_side=side, electronics_position=position)
    mesh = build_housing_body(params)
    assert validate_mesh(mesh)["watertight"]
    assert component_count(mesh) == 1
    direction = 1 if position == "bottom" else -1
    assert params.touch_icon_center_z_mm - params.usb_mount_center_z_mm == pytest.approx(29.5 * direction)
    assert params.dimmer_mount_bottom_mm < params.touch_icon_center_z_mm < params.dimmer_mount_top_mm
    engraved_x = 0.4 if side == "left" else params.outer_width_mm - 0.4
    # Triangles lying in the recess plane are the floors of the two icons.
    corners = mesh.vertices[mesh.faces]
    floors = corners[(abs(corners[:, :, 0] - engraved_x) < 1e-4).all(axis=1)].reshape(-1, 3)
    near_usb = abs(floors[:, 2] - params.usb_icon_center_z_mm) <= 3.6 + 1e-4
    near_touch = abs(floors[:, 2] - params.touch_icon_center_z_mm) <= 5.2 + 1e-4
    assert near_usb.any() and near_touch.any() and (near_usb | near_touch).all()
    assert abs(floors[:, 1] - params.usb_mount_center_y_mm).max() <= 7.9 + 1e-4


def test_frame_panel_is_locked_by_wedge_sockets_between_the_clips():
    params = HousingParams(kind="frame", panel_width_mm=150, panel_height_mm=100)
    assert params.panel_horizontal_lock_centers_mm == pytest.approx([12 + 56.25, 12 + 93.75])
    assert params.panel_vertical_lock_centers_mm == pytest.approx([12 + 50])
    assert params.panel_lock_count == 6
    body = build_housing_body(params)
    assert validate_mesh(body)["watertight"] and validate_mesh(body)["winding_errors"] == 0
    assert component_count(body) == 1
    # Socket floor: 0.1 mm above the seated panel, at the left pocket edge.
    floor_y = params.front_thickness_mm + params.panel_thickness_mm + 0.1
    pocket_x0 = params.panel_x0_mm - params.clearance_mm / 2
    assert any(
        x == pytest.approx(pocket_x0 - params.panel_lock_depth_mm) and y == pytest.approx(floor_y)
        for x, y, _ in body.vertices
    )

    wedges = build_housing_panel_wedges(params)
    assert validate_mesh(wedges)["watertight"] and validate_mesh(wedges)["winding_errors"] == 0
    assert component_count(wedges) == params.panel_wedge_count == 8
    # A seated wedge covers the panel flange without reaching past its 2 mm.
    overlap = params.panel_wedge_length_mm - params.panel_lock_depth_mm - params.clearance_mm / 2
    assert 1.0 < overlap < 2.0
    assert params.panel_wedge_tip_thickness_mm < params.wedge_slot_height_mm < params.panel_wedge_head_thickness_mm


def test_box_and_narrow_frames_keep_clips_only():
    assert HousingParams(kind="box").panel_lock_count == 0
    assert HousingParams(kind="box").panel_wedge_count == 0
    assert HousingParams(kind="frame", frame_border_mm=5).panel_lock_count == 0


def test_locking_wedges_print_flat_and_jam_inside_their_slots():
    params = HousingParams()
    wedges = build_housing_wedges(params)
    validation = validate_mesh(wedges)
    assert validation["watertight"] and validation["winding_errors"] == 0 and validation["positive_volume"]
    assert component_count(wedges) == params.wedge_count == 4
    assert wedges.vertices[:, 2].min() == pytest.approx(0)
    # The taper crosses the slot height, so the wedge enters freely and jams.
    assert params.wedge_tip_thickness_mm < params.wedge_slot_height_mm < params.wedge_head_thickness_mm
    assert params.wedge_width_mm < params.wedge_slot_width_mm
    # Wedge slots end below the rear-cover lip.
    slot_top = params.usb_mount_center_y_mm + (params.usb_shell_width_mm + 2 * params.usb_fit_clearance_mm) / 2 + 3.5
    assert slot_top < params.body_depth_mm - params.back_lip_depth_mm


def test_back_cover_is_closed_without_legacy_cable_pass_through():
    back = build_housing_back(HousingParams())
    assert validate_mesh(back)["watertight"]
    assert component_count(back) == 1


@pytest.mark.parametrize("width,height", [(150, 100), (180, 130), (200, 150), (100, 150), (130, 180), (150, 200)])
@pytest.mark.parametrize("kind", ["box", "frame"])
def test_every_preset_orientation_fits_and_stays_manifold(kind, width, height):
    params = HousingParams(kind=kind, panel_width_mm=width, panel_height_mm=height)
    assert params.outer_width_mm <= 256
    assert params.outer_height_mm <= 256
    assert validate_mesh(build_housing_body(params))["watertight"]


def test_housing_api_returns_body_and_back_as_separate_stls():
    response = client.post("/api/housing/generate", json={
        "kind": "frame",
        "panel_width_mm": 150,
        "panel_height_mm": 100,
    })
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-housing-kind"] == "frame"
    assert response.headers["x-housing-outer-size-mm"] == "174x124x40"
    assert response.headers["x-panel-pocket-depth-mm"] == "2"
    assert response.headers["x-panel-clip-count"] == "10"
    assert response.headers["x-back-snap-count"] == "10"
    assert response.headers["x-print-orientation"] == "front-face-down"
    with ZipFile(BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [
            "README-PL.txt",
            "litho-frame-150x100-back.stl",
            "litho-frame-150x100-body.stl",
            "litho-frame-150x100-panel-wedges.stl",
            "litho-frame-150x100-wedges.stl",
        ]
        for name in (entry for entry in archive.namelist() if entry.endswith(".stl")):
            payload = archive.read(name)
            assert len(payload) > 84
            assert payload.startswith(b"Lithophane Generator V1")
        instructions = archive.read("README-PL.txt").decode("utf-8")
        assert "sprezystymi zatrzaskami" in instructions
        assert "bez kleju" in instructions


def test_housing_api_describes_usb_c_and_touch_dimmer_mounts():
    response = client.post("/api/housing/generate", json={
        "kind": "box",
        "panel_width_mm": 150,
        "panel_height_mm": 100,
        "usb_side": "left",
        "electronics_position": "top",
    })
    assert response.status_code == 200
    assert response.headers["x-connection-type"] == "usb_c"
    assert response.headers["x-usb-side"] == "left"
    assert response.headers["x-electronics-position"] == "top"
    assert response.headers["x-touch-dimmer"] == "true"
    with ZipFile(BytesIO(response.content)) as archive:
        instructions = archive.read("README-PL.txt").decode("utf-8")
        assert "modul USB-C" in instructions
        assert "sprezyna anteny" in instructions
