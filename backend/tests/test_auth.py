from fastapi.testclient import TestClient

from app.auth import auth_store
from app.main import app


def configure_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("LITHO_AUTH_DISABLED", "false")
    monkeypatch.setenv("LITHO_BOOTSTRAP_ADMIN_USERNAME", "owner")
    monkeypatch.setenv("LITHO_BOOTSTRAP_ADMIN_PASSWORD", "correct-horse-battery-staple")
    monkeypatch.setenv("LITHO_BOOTSTRAP_ADMIN_DISPLAY_NAME", "Owner")
    monkeypatch.setenv("LITHO_ADMIN_API_KEY", "wordpress-service-key")
    auth_store.database = tmp_path / "auth.sqlite3"
    auth_store._initialized_for = None
    auth_store.initialize()


def login(client: TestClient, username: str, password: str):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_login_roles_csrf_and_user_management(tmp_path, monkeypatch):
    configure_auth(tmp_path, monkeypatch)
    admin = TestClient(app, base_url="http://testserver")

    assert admin.get("/api/health").status_code == 200
    assert admin.get("/api/auth/me").status_code == 401
    assert admin.post("/api/generate").status_code == 401
    assert admin.post("/api/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 401

    csrf = login(admin, "owner", "correct-horse-battery-staple")
    assert admin.get("/api/auth/me").json()["user"]["role"] == "admin"
    assert admin.post("/api/auth/users", json={}).status_code == 403

    created = admin.post(
        "/api/auth/users",
        headers={"X-CSRF-Token": csrf},
        json={"username": "partner", "display_name": "Partner", "password": "another-strong-password", "role": "operator"},
    )
    assert created.status_code == 201, created.text
    partner_id = created.json()["id"]
    assert created.json()["role"] == "operator"

    operator = TestClient(app, base_url="http://testserver")
    operator_csrf = login(operator, "partner", "another-strong-password")
    assert operator.get("/api/auth/users").status_code == 403
    assert operator.post("/api/generate", headers={"X-CSRF-Token": operator_csrf}).status_code == 422

    reset = admin.put(
        f"/api/auth/users/{partner_id}/password",
        headers={"X-CSRF-Token": csrf},
        json={"new_password": "replacement-strong-password"},
    )
    assert reset.status_code == 204
    assert operator.get("/api/auth/me").status_code == 401


def test_cannot_disable_last_admin(tmp_path, monkeypatch):
    configure_auth(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, "owner", "correct-horse-battery-staple")
    owner = client.get("/api/auth/me").json()["user"]
    response = client.put(
        f"/api/auth/users/{owner['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"display_name": "Owner", "role": "operator", "active": True},
    )
    assert response.status_code == 409


def test_service_key_is_limited_to_wordpress_project_routes(tmp_path, monkeypatch):
    configure_auth(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    headers = {"X-Litho-Admin-Key": "wordpress-service-key"}
    created = client.post("/api/customer/projects", headers=headers, json={})
    assert created.status_code == 201, created.text
    assert client.get("/api/admin/projects", headers=headers).status_code == 200
    assert client.get("/api/auth/users", headers=headers).status_code == 401
