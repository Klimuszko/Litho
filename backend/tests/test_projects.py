from io import BytesIO

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main_module
from app.main import app
from app.projects import CustomerProjectConfig, project_store


client = TestClient(app)


def sample_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, "PNG")
    return output.getvalue()


def test_customer_configuration_maps_presets_to_locked_production_settings():
    portrait = CustomerProjectConfig(size="130x180", orientation="portrait", power_source="battery")
    assert portrait.dimensions_mm == (130, 180)
    params = portrait.lithophane_params()
    assert (params.width_mm, params.height_mm) == (130, 180)
    assert (params.min_thickness_mm, params.max_thickness_mm) == (0.6, 4.0)
    assert params.quality_profile == "maximum"
    assert params.mounting_flange is True


def test_project_lifecycle_and_admin_access(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "root", tmp_path)
    monkeypatch.setenv("LITHO_ADMIN_API_KEY", "admin-secret")

    created = client.post("/api/customer/projects", json={
        "size": "100x150",
        "orientation": "landscape",
        "housing_type": "frame",
        "housing_color": "black-matte",
        "power_source": "wired",
        "light_temperature": "warm",
    })
    assert created.status_code == 201, created.text
    project = created.json()
    project_id = project["project_id"]
    token = project["project_token"]
    assert project["status"] == "awaiting_image"
    assert "token_hash" not in project

    denied = client.get(f"/api/customer/projects/{project_id}")
    assert denied.status_code == 403

    uploaded = client.post(
        f"/api/customer/projects/{project_id}/image",
        headers={"X-Project-Token": token},
        files={"image": ("portrait.png", sample_png(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "ready"

    class DummyMesh:
        faces = np.zeros((2, 3), dtype=np.int32)

    monkeypatch.setattr(main_module, "pipeline", lambda raw, params: (None, DummyMesh(), (11, 9)))
    monkeypatch.setattr(main_module, "binary_stl", lambda mesh: b"binary-stl")
    generated = client.post(
        f"/api/customer/projects/{project_id}/generate",
        headers={"X-Project-Token": token},
    )
    assert generated.status_code == 202, generated.text
    assert generated.json()["status"] == "generating"

    completed = client.get(
        f"/api/customer/projects/{project_id}",
        headers={"X-Project-Token": token},
    )
    assert completed.json()["status"] == "completed"
    assert completed.json()["artifacts"]["lithophane_stl"]["grid"] == "11x9"

    artifact = client.get(
        f"/api/customer/projects/{project_id}/artifacts/lithophane_stl",
        headers={"X-Project-Token": token},
    )
    assert artifact.status_code == 200
    assert artifact.content == b"binary-stl"

    assert client.get("/api/admin/projects", headers={"X-Litho-Admin-Key": "wrong"}).status_code == 403
    listing = client.get("/api/admin/projects", headers={"X-Litho-Admin-Key": "admin-secret"})
    assert listing.status_code == 200
    assert listing.json()["projects"][0]["project_id"] == project_id
    assert "token_hash" not in listing.json()["projects"][0]

    attached = client.put(
        f"/api/admin/projects/{project_id}/order",
        headers={"X-Litho-Admin-Key": "admin-secret"},
        json={"order_id": "WC-1234"},
    )
    assert attached.status_code == 200
    assert attached.json()["customer_ref"] == "WC-1234"

    deleted = client.delete(
        f"/api/admin/projects/{project_id}",
        headers={"X-Litho-Admin-Key": "admin-secret"},
    )
    assert deleted.status_code == 204
    assert not (tmp_path / project_id).exists()


def test_project_ids_cannot_escape_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "root", tmp_path)
    response = client.get("/api/customer/projects/..%2Fsecret", headers={"X-Project-Token": "x"})
    assert response.status_code == 404


def test_background_generation_cannot_resurrect_admin_deleted_project(tmp_path, monkeypatch):
    monkeypatch.setattr(project_store, "root", tmp_path)
    created = client.post("/api/customer/projects", json={}).json()
    project_id = created["project_id"]
    token = created["project_token"]
    client.post(
        f"/api/customer/projects/{project_id}/image",
        headers={"X-Project-Token": token},
        files={"image": ("photo.png", sample_png(), "image/png")},
    )

    class DummyMesh:
        faces = np.zeros((2, 3), dtype=np.int32)

    def delete_during_pipeline(raw, params):
        project_store.delete(project_id)
        return None, DummyMesh(), (11, 9)

    monkeypatch.setattr(main_module, "pipeline", delete_during_pipeline)
    monkeypatch.setattr(main_module, "binary_stl", lambda mesh: b"binary-stl")
    response = client.post(
        f"/api/customer/projects/{project_id}/generate",
        headers={"X-Project-Token": token},
    )
    assert response.status_code == 202
    assert not (tmp_path / project_id).exists()
