from app.scad.permissions import ModulePermissionService


policy = ModulePermissionService()
owner = {"id": 1, "role": "operator"}
other = {"id": 2, "role": "operator"}
admin = {"id": 3, "role": "admin"}


def module(**changes):
    return {"owner_user_id": 1, "visibility": "private", "status": "draft", "published_version_id": None, **changes}


def test_private_module_is_visible_only_to_owner_and_admin():
    item = module()
    assert policy.can("read", owner, item)
    assert policy.can("read", admin, item)
    assert not policy.can("read", other, item)


def test_public_module_can_be_used_but_not_edited_by_other_user():
    item = module(visibility="public", status="published", published_version_id="v1")
    assert policy.can("execute", other, item)
    assert policy.can("duplicate", other, item)
    assert not policy.can("update", other, item)
    assert not policy.can("delete", other, item)


def test_blocked_module_cannot_execute_even_for_admin():
    item = module(visibility="public", status="blocked", published_version_id="v1")
    assert not policy.can("execute", owner, item)
    assert not policy.can("execute", admin, item)
    assert policy.can("moderate", admin, item)
    assert not policy.can("publish", owner, item)
    assert policy.can("publish", admin, item)
