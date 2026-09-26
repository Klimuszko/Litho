from fastapi.testclient import TestClient
from io import BytesIO
from PIL import Image

from app.auth import UserCreate, auth_store
from app.main import app
from app.scad.repository import scad_repository


SOURCE = b'''/* [Main] */
size = 20; // [10:1:40] @unit:mm
style = "Round"; // [Round,Square]
enabled = true;
cube([size,size,2]);
'''


def setup_users(tmp_path, monkeypatch):
    monkeypatch.setenv("LITHO_AUTH_DISABLED", "false")
    monkeypatch.setenv("LITHO_SECURE_COOKIES", "false")
    monkeypatch.setenv("LITHO_BOOTSTRAP_ADMIN_USERNAME", "owner")
    monkeypatch.setenv("LITHO_BOOTSTRAP_ADMIN_PASSWORD", "correct-horse-battery-staple")
    auth_store.database = tmp_path / "auth.sqlite3"
    auth_store._initialized_for = None
    auth_store.initialize()
    auth_store.create_user(UserCreate(username="alice", display_name="Alice", password="password123", role="operator"))
    auth_store.create_user(UserCreate(username="bob", display_name="Bob", password="password123", role="operator"))
    scad_repository.database = auth_store.database
    scad_repository.storage = tmp_path / "scad"
    scad_repository._initialized_for = None
    scad_repository.initialize()


def login(username, password):
    client = TestClient(app, base_url="http://testserver")
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def test_multi_user_publish_duplicate_and_admin_moderation(tmp_path, monkeypatch):
    setup_users(tmp_path, monkeypatch)
    alice, alice_headers = login("alice", "password123")
    created = alice.post(
        "/api/scad/modules", headers=alice_headers,
        data={"name": "Shared box", "description": "A box", "category": "Storage", "visibility": "private"},
        files={"source": ("main.scad", SOURCE, "text/plain")},
    )
    assert created.status_code == 201, created.text
    module = created.json()
    assert module["active_version"]["parameters"][0]["name"] == "size"

    bob, bob_headers = login("bob", "password123")
    assert bob.get(f"/api/scad/modules/{module['id']}").status_code == 403
    assert bob.delete(f"/api/scad/modules/{module['id']}", headers=bob_headers).status_code == 403

    published = alice.post(
        f"/api/scad/modules/{module['id']}/publish", headers=alice_headers,
        json={"visibility": "public"},
    )
    assert published.status_code == 200, published.text
    assert bob.get(f"/api/scad/modules/{module['id']}").status_code == 200
    forbidden = bob.put(
        f"/api/scad/modules/{module['id']}", headers=bob_headers,
        json={"name": "Hijacked", "description": "", "category": "Other", "visibility": "public", "revision": published.json()["revision"]},
    )
    assert forbidden.status_code == 403

    duplicate = bob.post(f"/api/scad/modules/{module['id']}/duplicate", headers=bob_headers)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["owner_username"] == "bob"
    assert duplicate.json()["forked_from_module_id"] == module["id"]

    shared = alice.post(f"/api/scad/modules/{module['id']}/shares", headers=alice_headers, data={"username":"bob"})
    assert shared.status_code == 201, shared.text
    shared_list = bob.get("/api/scad/modules?scope=shared")
    assert module["id"] in [item["id"] for item in shared_list.json()["modules"]]

    preview = alice.post(
        f"/api/scad/modules/{module['id']}/preview", headers=alice_headers,
        files={"preview": ("preview.png", preview_png(), "image/png")},
    )
    assert preview.status_code == 200, preview.text
    assert alice.get(f"/api/scad/modules/{module['id']}/preview").status_code == 200

    admin, admin_headers = login("owner", "correct-horse-battery-staple")
    blocked = admin.post(f"/api/scad/modules/{module['id']}/moderate", headers=admin_headers, json={"action": "block"})
    assert blocked.status_code == 200 and blocked.json()["status"] == "blocked"
    render = bob.post(f"/api/scad/modules/{module['id']}/renders", headers=bob_headers, json={"parameters": {"size": 20, "style": "Round", "enabled": True}})
    assert render.status_code == 403
    audit = admin.get(f"/api/scad/modules/{module['id']}/audit")
    assert audit.status_code == 200
    assert "module.blocked" in [item["action"] for item in audit.json()["audit"]]


def preview_png():
    output = BytesIO()
    Image.new("RGB", (8, 8), "navy").save(output, "PNG")
    return output.getvalue()


def test_published_version_stays_stable_while_owner_adds_draft(tmp_path, monkeypatch):
    setup_users(tmp_path, monkeypatch)
    alice, headers = login("alice", "password123")
    module = alice.post("/api/scad/modules", headers=headers, data={"name":"Versioned"}, files={"source": ("main.scad", SOURCE, "text/plain")}).json()
    published = alice.post(f"/api/scad/modules/{module['id']}/publish", headers=headers, json={"visibility":"public"}).json()
    old_public = published["published_version_id"]
    version = alice.post(
        f"/api/scad/modules/{module['id']}/versions", headers=headers,
        data={"version_label":"Next", "changelog":"Work in progress"},
        files={"source": ("main.scad", SOURCE.replace(b"20", b"21"), "text/plain")},
    )
    assert version.status_code == 201, version.text
    latest = alice.get(f"/api/scad/modules/{module['id']}").json()
    assert latest["working_version_id"] == version.json()["id"]
    assert latest["published_version_id"] == old_public
    comparison = alice.get(f"/api/scad/modules/{module['id']}/versions/compare", params={"left":old_public,"right":version.json()["id"]})
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["source_diff"]
    bob, bob_headers = login("bob", "password123")
    assert bob.get(f"/api/scad/modules/{module['id']}/source", params={"version_id":version.json()["id"]}).status_code == 403
    assert bob.post(
        f"/api/scad/modules/{module['id']}/renders", headers=bob_headers,
        json={"version_id":version.json()["id"],"parameters":{"size":21,"style":"Round","enabled":True}},
    ).status_code == 403
