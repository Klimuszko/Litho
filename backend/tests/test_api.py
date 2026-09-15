from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


client = TestClient(app)


def sample_png() -> bytes:
    output = BytesIO()
    Image.linear_gradient("L").resize((64, 48)).save(output, "PNG")
    return output.getvalue()


def test_generate_returns_binary_stl():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":100,"height_mm":75,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"gamma":1,"resolution":48}'},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "model/stl"
    assert len(response.content) > 84


def test_rejects_invalid_thickness_relation():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":100,"height_mm":75,"min_thickness_mm":3,"max_thickness_mm":2}'},
    )
    assert response.status_code == 422


def test_height_is_optional_and_derived_from_image():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":100,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"resolution":24}'},
    )
    assert response.status_code == 200, response.text


def test_rejects_border_lower_than_relief():
    response = client.post(
        "/api/generate",
        files={"image": ("photo.png", sample_png(), "image/png")},
        data={"params": '{"width_mm":100,"height_mm":75,"min_thickness_mm":0.8,"max_thickness_mm":3.2,"border_width_mm":5,"border_height_mm":2}'},
    )
    assert response.status_code == 422
