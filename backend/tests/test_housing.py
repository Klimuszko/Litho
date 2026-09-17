from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.housing import build_housing_back, build_housing_body, orient_front_on_bed
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
    (150, 100, 4), (180, 130, 6), (200, 150, 6), (100, 150, 4), (130, 180, 6),
])
def test_integrated_clip_count_scales_with_panel(width, height, expected):
    params = HousingParams(panel_width_mm=width, panel_height_mm=height)
    assert params.panel_clip_count == expected
    assert params.panel_clip_reach_mm == pytest.approx(0.4)
    assert params.panel_clip_ramp_height_mm == pytest.approx(0.8)
    assert params.panel_clip_flex_thickness_mm == pytest.approx(0.8)
    assert params.panel_clip_relief_mm == pytest.approx(0.6)


def test_clip_hook_reaches_over_panel_edge_at_controlled_clearance():
    params = HousingParams(panel_width_mm=150, panel_height_mm=100)
    mesh = build_housing_body(params)
    hook_y = params.front_thickness_mm + params.panel_thickness_mm + params.panel_clip_clearance_mm
    left_hook_tip = params.panel_x0_mm - params.clearance_mm / 2 + params.panel_clip_reach_mm
    clip_center_z = params.panel_z0_mm + params.panel_height_mm / 2
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
    assert response.headers["x-panel-clip-count"] == "4"
    assert response.headers["x-print-orientation"] == "front-face-down"
    with ZipFile(BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [
            "README-PL.txt",
            "litho-frame-150x100-back.stl",
            "litho-frame-150x100-body.stl",
        ]
        for name in (entry for entry in archive.namelist() if entry.endswith(".stl")):
            payload = archive.read(name)
            assert len(payload) > 84
            assert payload.startswith(b"Lithophane Generator V1")
        instructions = archive.read("README-PL.txt").decode("utf-8")
        assert "sprezystymi zatrzaskami" in instructions
        assert "bez kleju" in instructions
