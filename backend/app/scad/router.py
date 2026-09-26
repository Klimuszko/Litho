from __future__ import annotations

import io
import json
import sqlite3
import difflib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from .engine import scad_engine
from .jobs import scad_render_service
from .models import ModerationRequest, ModuleCreate, ModuleUpdate, PresetCreate, PresetUpdate, PublishRequest, RenderCreate
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
    version_id = module["working_version_id"] if editable else module["published_version_id"]
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


@router.get("/engine")
def engine_status(request: Request):
    user(request)
    return scad_engine.status()


@router.get("/categories")
def categories(request: Request):
    user(request)
    return {"categories": CATEGORIES}


@router.get("/modules")
def modules(request: Request, scope: str = Query("public"), search: str = "", category: str = "", author: str = "", sort: str = "updated"):
    current = user(request)
    if scope not in {"my", "public", "official", "all", "shared"}: problem(ValueError("Nieprawidłowy zakres"))
    return {"modules": [enriched(item, current) for item in scad_repository.list_modules(current, scope, search[:120], category[:80], author[:120], sort)]}


@router.post("/modules", status_code=201)
async def create_module(request: Request, source: UploadFile = File(...), name: str = Form(...), description: str = Form(""), category: str = Form("Other"), visibility: str = Form("private")):
    current = user(request)
    try:
        data = ModuleCreate(name=name, description=description, category=category, visibility=visibility)
        payload = await source.read(10 * 1024 * 1024 + 1)
        return enriched(scad_repository.create_module(current, data, payload, source.filename or "module.scad"), current)
    except (ValueError, PermissionError) as exc: problem(exc)


@router.get("/modules/{module_id}")
def get_module(module_id: str, request: Request):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("read", current, module)
    return enriched(module, current)


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
    selected = version_or_404(version_id or (module["working_version_id"] if current["id"] == module["owner_user_id"] or current.get("role") == "admin" else module["published_version_id"]))
    if selected["module_id"] != module_id: problem(ValueError("Wersja nie należy do modułu"), status=404)
    if current.get("role") != "admin" and current["id"] != module["owner_user_id"] and selected["id"] != module["published_version_id"]:
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


@router.post("/modules/{module_id}/renders", status_code=202)
def render(module_id: str, data: RenderCreate, request: Request):
    current = user(request); module = accessible_module(module_id, current)
    module_permissions.require("execute", current, module)
    editable = current.get("role") == "admin" or current["id"] == module["owner_user_id"]
    version_id = data.version_id or (module["working_version_id"] if editable else module["published_version_id"])
    version = version_or_404(version_id)
    if version["module_id"] != module_id: problem(ValueError("Wersja nie należy do modułu"))
    if not editable and version["id"] != module["published_version_id"]:
        problem(PermissionError("Wersja robocza nie jest publiczna"), "VERSION_FORBIDDEN", 403)
    try: return scad_render_service.create(current, module, version, data.parameters, data.output_format, data.mode)
    except ValueError as exc: problem(exc, "PARAMETERS_INVALID")


def owned_job(job_id: str, current: dict) -> dict:
    try: job = scad_render_service.get(job_id)
    except KeyError as exc: problem(exc, "RENDER_NOT_FOUND", 404)
    if job["user_id"] != current["id"] and current.get("role") != "admin": problem(PermissionError(), "RENDER_FORBIDDEN", 403)
    return job


@router.get("/renders")
def render_history(request: Request, limit: int = Query(50, ge=1, le=200)):
    return {"renders": scad_render_service.list(user(request), limit)}


@router.get("/renders/{job_id}")
def render_status(job_id: str, request: Request):
    return owned_job(job_id, user(request))


@router.delete("/renders/{job_id}")
def cancel_render(job_id: str, request: Request):
    current = user(request); owned_job(job_id, current)
    return scad_render_service.cancel(job_id)


@router.get("/renders/{job_id}/download")
def download_render(job_id: str, request: Request):
    job = owned_job(job_id, user(request))
    if job["mode"] == "metadata": problem(ValueError("Tryb metadata nie tworzy modelu"), "METADATA_HAS_NO_MODEL", 409)
    if job["status"] != "completed" or not job.get("output_path"): problem(ValueError("Render nie jest gotowy"), "RENDER_NOT_READY", 409)
    path = Path(job["output_path"])
    if not path.is_file(): problem(FileNotFoundError(), "OUTPUT_MISSING", 404)
    return FileResponse(path, media_type="model/stl" if job["output_format"] == "stl" else "model/3mf", filename=f"litho-{job['module_id']}.{job['output_format']}")
