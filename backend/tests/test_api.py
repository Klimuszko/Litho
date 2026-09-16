from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app, pipeline
from app.models import LithophaneParams


client = TestClient(app)


def sample_png() -> bytes:
    output = BytesIO()
    Image.linear_gradient("L").resize((64, 48)).save(output, "PNG")
    return output.getvalue()


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


def test_optional_removable_support_is_reported_and_added():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"resolution":24,"removable_support":true}'},
    )
    assert response.status_code == 200, response.text
    assert response.headers["x-removable-support"] == "true"


def test_rejects_border_lower_than_relief():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":150,"height_mm":100,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"border_width_mm":5,"border_height_mm":2}'},
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
