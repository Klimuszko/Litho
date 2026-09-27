from __future__ import annotations

import io
import sqlite3
import difflib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from .models import ModuleCodeCreate, ModuleCodeUpdate, ModerationRequest, ModuleCreate, ModuleUpdate, PresetCreate, PresetUpdate, PublishRequest
from .permissions import module_permissions
from .repository import CATEGORIES, scad_repository


router = APIRouter(prefix="/api/scad", tags=["SCAD modules"])


def user(request: Request) -> dict:
    current = getattr(request.state, "user", None)
    if not current:
        raise HTTPException(status_code=401, detail={"error_code": "AUTH_REQUIRED", "message": "Zaloguj się."})
    return current


def module_or_404(module_id: str) -> dict:
    try: return scad_repository.get_module(module_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail={"error_code": "MODULE_NOT_FOUND", "message": "Moduł nie istnieje."}) from exc


def accessible_module(module_id: str, current: dict) -> dict:
    return scad_repository.with_share(module_or_404(module_id), current["id"])


def version_or_404(version_id: str) -> dict:
    try: return scad_repository.version(version_id)
    except KeyError as exc: raise HTTPException(status_code=404, detail={"error_code": "VERSION_NOT_FOUND", "message": "Wersja nie istnieje."}) from exc


def enriched(module: dict, current: dict) -> dict:
    owner = module["owner_user_id"] == current["id"]
    editable = owner or current.get("role") == "admin"
    version_id = module["working_version_id"] if editable or module["status"] == "draft" else (module["published_version_id"] or module["working_version_id"])
    result = dict(module)
    result["preview_url"] = f"/api/scad/modules/{module['id']}/preview" if module.get("preview_path") else None
    result.pop("preview_path", None)
    result["permissions"] = {operation: module_permissions.can(operation, current, module) for operation in ("read", "use", "execute", "update", "publish", "delete", "restore", "duplicate", "moderate", "permanent_delete")}
    result["active_version_id"] = version_id
    if version_id:
        result["active_version"] = version_or_404(version_id)
    return result


def problem(exc: Exception, code: str = "MODULE_INVALID", status: int = 422):
    raise HTTPException(status_code=status, detail={"error_code": code, "message": str(exc)}) from exc


@router.get("/categories")
def categories(request: Request):
    user(request)
    return {"categories": CATEGORIES}


@router.get("/modules")
def modules(request: Request, scope: str = Query("all"), search: str = "", category: str = "", author: str = "", sort: str = "updated", status: str = ""):
    current = user(request)
    if scope not in {"my", "all"}: problem(ValueError("Nieprawidłowy zakres"))
    if status not in {"", "draft", "published", "blocked"}: problem(ValueError("Nieprawidłowy status"))
    return {"modules": [enriched(item, current) for item in scad_repository.list_modules(current, scope, search[:120], category[:80], author[:120], sort, status)]}


@router.post("/modules", status_code=201)
async def create_module(request: Request, source: UploadFile = File(...), name: str = Form(...), description: str = Form(""), category: str = Form("Other"), visibility: str = Form("private")):
    current = user(request)
    try:
        data = ModuleCreate(name=name, description=description, category=category, visibility=visibility)
        payload = await source.read(10 * 1024 * 1024 + 1)
        return enriched(scad_repository.create_module(current, data, payload, source.filename or "module.scad"), current)
    except (ValueError, PermissionError) as exc: problem(exc)


@router.post("/modules/code", status_code=201)
def create_module_from_code(data: ModuleCodeCreate, request: Request):
    current = user(request)
    try:
        create = ModuleCreate(name=data.name, description=data.description, category=data.category, visibility="public")
        return enriched(scad_repository.create_module(current, create, data.source.encode("utf-8"), "main.scad"), current)
    except (ValueError, PermissionError) as exc: problem(exc)


@router.get("/modules/{module_id}")
def get_module(module_id: str, request: Request):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("read", current, module)
    return enriched(module, current)


@router.get("/modules/{module_id}/code")
def get_module_code(module_id: str, request: Request, version_id: str | None = None):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("read", current, module)
    editable = current.get("role") == "admin" or current["id"] == module["owner_user_id"]
    selected_id = version_id or (module["working_version_id"] if editable or module["status"] == "draft" else (module["published_version_id"] or module["working_version_id"]))
    selected = version_or_404(selected_id)
    if selected["module_id"] != module_id: problem(ValueError("Wersja nie należy do modułu"), status=404)
    path = Path(selected["storage_path"]) / selected["entry_file"]
    return {"source": path.read_text(encoding="utf-8"), "entry_file": selected["entry_file"], "version_id": selected["id"], "editable": module_permissions.can("update", current, module)}


@router.put("/modules/{module_id}/code", status_code=201)
def update_module_code(module_id: str, data: ModuleCodeUpdate, request: Request):
    try:
        return scad_repository.update_code(user(request), module_id, data.source, data.version_label, data.changelog)
    except (ValueError, PermissionError) as exc: problem(exc, "SOURCE_INVALID", 403 if isinstance(exc, PermissionError) else 422)


@router.put("/modules/{module_id}")
def update_module(module_id: str, update: ModuleUpdate, request: Request):
    current = user(request)
    try: return enriched(scad_repository.update_module(current, module_id, update), current)
    except RuntimeError as exc:
        if str(exc) == "revision_conflict": problem(exc, "REVISION_CONFLICT", 409)
        raise
    except PermissionError as exc: problem(exc, "MODULE_FORBIDDEN", 403)


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(module_id: str, request: Request):
    scad_repository.soft_delete(user(request), module_id)


@router.post("/modules/{module_id}/restore")
def restore_module(module_id: str, request: Request):
    current = user(request)
    return enriched(scad_repository.restore(current, module_id), current)


@router.delete("/modules/{module_id}/permanent", status_code=204)
def permanently_delete(module_id: str, request: Request):
    scad_repository.permanent_delete(user(request), module_id)


@router.post("/modules/{module_id}/publish")
def publish(module_id: str, publish_request: PublishRequest, request: Request):
    current = user(request)
    try: return enriched(scad_repository.publish(current, module_id, publish_request.version_id, publish_request.visibility), current)
    except PermissionError as exc: problem(exc, "MODULE_FORBIDDEN", 403)


@router.post("/modules/{module_id}/unpublish")
def unpublish(module_id: str, request: Request):
    current = user(request)
    return enriched(scad_repository.unpublish(current, module_id), current)


@router.post("/modules/{module_id}/duplicate", status_code=201)
def duplicate(module_id: str, request: Request):
    current = user(request)
    return enriched(scad_repository.duplicate(current, module_id), current)


@router.post("/modules/{module_id}/moderate")
def moderate(module_id: str, moderation: ModerationRequest, request: Request):
    current = user(request)
    return enriched(scad_repository.moderate(current, module_id, moderation.action), current)


@router.get("/modules/{module_id}/versions")
def versions(module_id: str, request: Request):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("read", current, module)
    visible = scad_repository.versions(module_id)
    if current.get("role") != "admin" and current["id"] != module["owner_user_id"]:
        visible = [item for item in visible if item["id"] == module["published_version_id"]]
    return {"versions": visible}


@router.get("/modules/{module_id}/versions/compare")
def compare_versions(module_id: str, request: Request, left: str, right: str):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("update", current, module)
    first, second = version_or_404(left), version_or_404(right)
    if first["module_id"] != module_id or second["module_id"] != module_id:
        problem(ValueError("Wersja nie należy do modułu"), status=404)
    first_source = (Path(first["storage_path"]) / first["entry_file"]).read_text(encoding="utf-8").splitlines()
    second_source = (Path(second["storage_path"]) / second["entry_file"]).read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(first_source, second_source, fromfile=f"v{first['version_number']}", tofile=f"v{second['version_number']}", lineterm=""))
    return {"left": first["id"], "right": second["id"], "source_diff": diff[:5000], "parameters_before": first["parameters"], "parameters_after": second["parameters"]}


@router.post("/modules/{module_id}/versions", status_code=201)
async def add_version(module_id: str, request: Request, source: UploadFile = File(...), version_label: str = Form(""), changelog: str = Form("")):
    try:
        payload = await source.read(10 * 1024 * 1024 + 1)
        return scad_repository.add_version(user(request), module_id, payload, source.filename or "main.scad", version_label, changelog)
    except ValueError as exc: problem(exc)


@router.post("/modules/{module_id}/versions/{version_id}/restore", status_code=201)
def restore_version(module_id: str, version_id: str, request: Request):
    return scad_repository.restore_version(user(request), module_id, version_id)


@router.get("/modules/{module_id}/source")
def download_source(module_id: str, request: Request, version_id: str | None = None):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("read", current, module)
    editable = current["id"] == module["owner_user_id"] or current.get("role") == "admin"
    selected = version_or_404(version_id or (module["working_version_id"] if editable or module["status"] == "draft" else (module["published_version_id"] or module["working_version_id"])))
    if selected["module_id"] != module_id: problem(ValueError("Wersja nie należy do modułu"), status=404)
    allowed_version = module["working_version_id"] if module["status"] == "draft" else module["published_version_id"]
    if not editable and selected["id"] != allowed_version:
        problem(PermissionError("Wersja robocza nie jest publiczna"), "VERSION_FORBIDDEN", 403)
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        root = Path(selected["storage_path"])
        for path in root.rglob("*"):
            if path.is_file(): archive.write(path, path.relative_to(root).as_posix())
    return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{module["slug"]}-v{selected["version_number"]}.zip"'})


@router.post("/modules/{module_id}/preview")
async def upload_preview(module_id: str, request: Request, preview: UploadFile = File(...)):
    current = user(request)
    try:
        payload = await preview.read(5 * 1024 * 1024 + 1)
        return enriched(scad_repository.save_preview(current, module_id, payload, preview.content_type or ""), current)
    except ValueError as exc: problem(exc, "PREVIEW_INVALID")


@router.get("/modules/{module_id}/preview")
def get_preview(module_id: str, request: Request):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("read", current, module)
    path = Path(module.get("preview_path") or "")
    if not path.is_file(): problem(FileNotFoundError(), "PREVIEW_NOT_FOUND", 404)
    return FileResponse(path, media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg")


@router.get("/modules/{module_id}/presets")
def presets(module_id: str, request: Request):
    return {"presets": scad_repository.presets(user(request), module_id)}


@router.get("/modules/{module_id}/shares")
def shares(module_id: str, request: Request):
    return {"users": scad_repository.shares(user(request), module_id)}


@router.post("/modules/{module_id}/shares", status_code=201)
def share(module_id: str, request: Request, username: str = Form(...)):
    try: return scad_repository.share(user(request), module_id, username)
    except KeyError as exc: problem(exc, "USER_NOT_FOUND", 404)
    except ValueError as exc: problem(exc)


@router.delete("/modules/{module_id}/shares/{target_user_id}", status_code=204)
def unshare(module_id: str, target_user_id: int, request: Request):
    scad_repository.unshare(user(request), module_id, target_user_id)


@router.post("/modules/{module_id}/presets", status_code=201)
def create_preset(module_id: str, data: PresetCreate, request: Request):
    try: return scad_repository.save_preset(user(request), module_id, data)
    except sqlite3.IntegrityError as exc: problem(exc, "PRESET_NAME_EXISTS", 409)


@router.put("/modules/{module_id}/presets/{preset_id}")
def update_preset(module_id: str, preset_id: str, data: PresetUpdate, request: Request):
    return scad_repository.save_preset(user(request), module_id, data, preset_id)


@router.delete("/modules/{module_id}/presets/{preset_id}", status_code=204)
def delete_preset(module_id: str, preset_id: str, request: Request):
    try: scad_repository.delete_preset(user(request), module_id, preset_id)
    except KeyError as exc: problem(exc, "PRESET_NOT_FOUND", 404)


@router.get("/modules/{module_id}/audit")
def audit(module_id: str, request: Request):
    return {"audit": scad_repository.audit(user(request), module_id)}
