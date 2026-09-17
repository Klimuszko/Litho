from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app, pipeline
from app.models import LithophaneParams


client = TestClient(app)


def sample_png() -> bytes:
    output = BytesIO()
    Image.linear_gradient("L").resize((64, 48)).save(output, "PNG")
    return output.getvalue()


def directional_png() -> bytes:
    image = Image.new("L", (60, 40), 255)
    for x in range(30):
        for y in range(40):
            image.putpixel((x, y), 0)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def test_pipeline_applies_technical_mirror_opposite_to_preview_choice():
    default_image, default_mesh, (default_cols, _) = pipeline(
        directional_png(), LithophaneParams(resolution=24)
    )
    creative_mirror, mirrored_mesh, (mirrored_cols, _) = pipeline(
        directional_png(), LithophaneParams(resolution=24, mirror=True)
    )
    assert default_image.getpixel((0, 20)) > default_image.getpixel((59, 20))
    assert creative_mirror.getpixel((0, 20)) < creative_mirror.getpixel((59, 20))
    # Front-surface Y is the local material thickness. The default STL has its
    # thick/dark side on the opposite X edge; creative mirror reverses it.
    assert default_mesh.vertices[0, 1] < default_mesh.vertices[default_cols - 1, 1]
    assert mirrored_mesh.vertices[0, 1] > mirrored_mesh.vertices[mirrored_cols - 1, 1]


def test_preview_endpoint_keeps_creative_orientation_without_technical_mirror():
    normal = client.post(
        "/api/preview",
        files={"image": ("direction.png", directional_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"resolution":24}'},
    )
    mirrored = client.post(
        "/api/preview",
        files={"image": ("direction.png", directional_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"resolution":24,"mirror":true}'},
    )
    assert normal.status_code == mirrored.status_code == 200
    normal_image = Image.open(BytesIO(normal.content))
    mirrored_image = Image.open(BytesIO(mirrored.content))
    y = normal_image.height // 2
    assert normal_image.getpixel((0, y)) < normal_image.getpixel((normal_image.width - 1, y))
    assert mirrored_image.getpixel((0, y)) > mirrored_image.getpixel((mirrored_image.width - 1, y))


def test_generate_returns_binary_stl():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"gamma":1,"resolution":48}'},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "model/stl"
    assert response.headers["x-nozzle-diameter-mm"] == "0.4"
    assert response.headers["x-quality-profile"] == "optimal"
    assert response.headers["x-sample-pitch-mm"] == "3.125"
    assert response.headers["x-effective-sample-pitch-mm"] == "3.125"
    assert response.headers["x-grid-size"] == "49x33"
    assert len(response.content) > 84


def test_rejects_invalid_thickness_relation():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"min_thickness_mm":3,"max_thickness_mm":2}'},
    )
    assert response.status_code == 422


def test_accepts_largest_preset_with_twenty_mm_border():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":200,"height_mm":150,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"border_width_mm":20,"resolution":24}'},
    )
    assert response.status_code == 200, response.text


def test_border_stays_inside_selected_final_dimensions():
    params = LithophaneParams(
        width_mm=150, height_mm=100, border_width_mm=4, resolution=24
    )
    _, mesh, _ = pipeline(sample_png(), params)
    assert float(mesh.vertices[:, 0].min()) == 0
    assert float(mesh.vertices[:, 0].max()) == 150
    assert float(mesh.vertices[:, 2].min()) == 0
    assert float(mesh.vertices[:, 2].max()) == 100


def test_asymmetric_border_stays_inside_selected_final_dimensions():
    params = LithophaneParams(
        width_mm=150, height_mm=100, border_widths_mm={"top": 2, "right": 4, "bottom": 6, "left": 8}, resolution=24
    )
    _, mesh, _ = pipeline(sample_png(), params)
    assert float(mesh.vertices[:, 0].max()) == 150
    assert float(mesh.vertices[:, 2].max()) == 100


def test_mounting_flange_has_fixed_geometry_and_preserves_manual_frame_settings():
    params = LithophaneParams(
        width_mm=150,
        height_mm=100,
        border_width_mm=10,
        border_height_mm=0.7,
        mounting_flange=True,
        resolution=24,
    )
    assert params.border_width_mm == 10
    assert params.border_height_mm == 0.7
    assert (params.border_top_mm, params.border_right_mm, params.border_bottom_mm, params.border_left_mm) == (2, 2, 2, 2)
    assert params.effective_border_height == 1.6
    assert (params.image_width_mm, params.image_height_mm) == (146, 96)
    _, mesh, _ = pipeline(sample_png(), params)
    assert float(mesh.vertices[:, 0].max()) == 150
    assert float(mesh.vertices[:, 2].max()) == 100
    front_vertex_count = len(mesh.vertices) // 2
    assert float(mesh.vertices[0, 1]) == pytest.approx(1.6)
    assert float(mesh.vertices[front_vertex_count - 1, 1]) == pytest.approx(1.6)


def test_optional_removable_support_is_reported_and_added():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"resolution":24,"removable_support":true}'},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-removable-support"] == "true"
    assert response.headers["x-support-count"] == "2"
    assert response.headers["x-support-extension-mm"] == "18.75"


def test_largest_landscape_format_reports_full_support_profile():
    response = client.post(
        "/api/generate",
        files={"image": ("test.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":200,"height_mm":150,"resolution":24,"removable_support":true}'},
    )
    assert response.status_code == 200
    assert response.headers["x-support-count"] == "3"
    assert response.headers["x-support-extension-mm"] == "25.0"


def test_default_photo_contrast_is_slightly_enhanced():
    params = LithophaneParams()
    assert params.contrast == 1.25
    assert params.min_thickness_mm == 0.8
    assert params.max_thickness_mm == 3.2


def test_accepts_border_lower_than_relief_for_lightweight_frame():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"border_width_mm":5,"border_height_mm":0.8,"resolution":24}'},
    )
    assert response.status_code == 200, response.text


def test_rejects_border_thinner_than_two_nozzle_widths():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"border_width_mm":5,"border_height_mm":0.7,"nozzle_diameter_mm":0.4,"resolution":24}'},
    )
    assert response.status_code == 422


def test_accepts_custom_size_within_machine_envelope():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":220,"height_mm":180,"min_thickness_mm":0.8,"max_thickness_mm":3.2}'},
    )
    assert response.status_code == 200, response.text


def test_rejects_orientation_that_does_not_match_dimensions():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":100,"height_mm":150,"orientation":"landscape"}'},
    )
    assert response.status_code == 422
