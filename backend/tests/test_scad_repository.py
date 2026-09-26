from pathlib import Path

import pytest

from app.auth import AuthStore, UserCreate
from app.scad.models import ModuleCreate
from app.scad.repository import ScadRepository


SOURCE = b'''/* [Main] */
width = 50; // [10:1:100] @unit:mm
rounded = true;
cube([width, 20, 3]);
'''


@pytest.fixture
def system(tmp_path: Path):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    auth.initialize()
    admin = auth.create_user(UserCreate(username="admin", display_name="Admin", password="password123", role="admin"))
    alice = auth.create_user(UserCreate(username="alice", display_name="Alice", password="password123", role="operator"))
    bob = auth.create_user(UserCreate(username="bob", display_name="Bob", password="password123", role="operator"))
    repository = ScadRepository(auth.database, tmp_path / "scad")
    repository.initialize()
    return repository, admin, alice, bob


def test_create_publish_duplicate_and_version_isolation(system):
    repository, admin, alice, bob = system
    created = repository.create_module(alice, ModuleCreate(name="Parametric box"), SOURCE, "box.scad")
    assert created["owner_user_id"] == alice["id"]
    first_version = repository.version(created["working_version_id"])
    assert [item["name"] for item in first_version["parameters"]] == ["width", "rounded"]
    assert repository.list_modules(bob, "public") == []

    published = repository.publish(alice, created["id"], None, "public")
    assert published["published_version_id"] == first_version["id"]
    assert repository.list_modules(bob, "public")[0]["id"] == created["id"]

    second = repository.add_version(alice, created["id"], SOURCE.replace(b"50", b"60"), "box.scad", "v2")
    unchanged = repository.get_module(created["id"])
    assert unchanged["working_version_id"] == second["id"]
    assert unchanged["published_version_id"] == first_version["id"]

    fork = repository.duplicate(bob, created["id"])
    assert fork["owner_user_id"] == bob["id"]
    assert fork["status"] == "draft" and fork["visibility"] == "private"
    assert fork["forked_from_module_id"] == created["id"]


def test_soft_delete_restore_and_admin_moderation(system):
    repository, admin, alice, bob = system
    created = repository.create_module(alice, ModuleCreate(name="Thing"), SOURCE, "main.scad")
    with pytest.raises(Exception):
        repository.soft_delete(bob, created["id"])
    repository.publish(alice, created["id"], None, "public")
    assert repository.moderate(admin, created["id"], "block")["status"] == "blocked"
    repository.soft_delete(alice, created["id"])
    assert repository.get_module(created["id"])["status"] == "deleted"
    assert repository.restore(alice, created["id"])["status"] == "blocked"
    actions = [item["action"] for item in repository.audit(admin, created["id"])]
    assert "module.blocked" in actions and "module.restored" in actions


def test_bundled_examples_are_seeded_as_official_modules(system, monkeypatch):
    repository, admin, alice, bob = system
    examples = Path(__file__).resolve().parents[2] / "examples" / "scad"
    monkeypatch.setenv("LITHO_SCAD_EXAMPLES_DIR", str(examples))
    monkeypatch.setenv("LITHO_SCAD_SEED_EXAMPLES", "true")
    created = repository.seed_bundled_examples()
    assert len(created) == 2
    official = repository.list_modules(bob, "official")
    assert {item["slug"] for item in official} == {"minimal-parametric-box", "planetary-fidget"}
    assert all(item["official"] and item["visibility"] == "system" for item in official)


def test_regular_user_cannot_create_system_module(system):
    repository, admin, alice, bob = system
    with pytest.raises(PermissionError):
        repository.create_module(alice, ModuleCreate(name="Fake official", visibility="system"), SOURCE, "main.scad")
