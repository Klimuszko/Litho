from __future__ import annotations

from fastapi import HTTPException


class ModulePermissionService:
    """Single policy boundary for all module operations."""

    @staticmethod
    def _admin(user: dict) -> bool:
        return user.get("role") == "admin"

    @staticmethod
    def _owner(user: dict, module: dict) -> bool:
        return int(user.get("id", -1)) == int(module["owner_user_id"])

    def can(self, operation: str, user: dict, module: dict) -> bool:
        admin = self._admin(user)
        owner = self._owner(user, module)
        status = module.get("status")
        visibility = module.get("visibility")

        if operation == "read":
            if status == "deleted":
                return admin or owner
            return admin or owner or (
                visibility in {"public", "unlisted", "system"}
                and status not in {"hidden", "blocked"}
                and bool(module.get("published_version_id"))
            ) or (bool(module.get("shared_with_user")) and status not in {"hidden", "blocked"} and bool(module.get("published_version_id")))
        if operation in {"use", "execute"}:
            if status in {"deleted", "blocked"}:
                return False
            return admin or owner or (
                visibility in {"public", "unlisted", "system"}
                and status == "published"
                and bool(module.get("published_version_id"))
            ) or (bool(module.get("shared_with_user")) and status == "published" and bool(module.get("published_version_id")))
        if operation in {"publish", "unpublish"}:
            return admin or (owner and status not in {"deleted", "hidden", "blocked"})
        if operation in {"update", "delete", "version", "preset"}:
            return (owner or admin) and status != "deleted"
        if operation == "restore":
            return (owner or admin) and status == "deleted"
        if operation in {"moderate", "permanent_delete", "official", "audit_all"}:
            return admin
        if operation == "duplicate":
            return self.can("read", user, module) and status != "deleted"
        return False

    def require(self, operation: str, user: dict, module: dict) -> None:
        if not self.can(operation, user, module):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "MODULE_FORBIDDEN", "message": "Nie masz uprawnień do tej operacji."},
            )


module_permissions = ModulePermissionService()
