import hashlib
import json
import os
import secrets
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .exporter import binary_stl
from .heightmap import grid_resolution, luminance_to_thickness
from .housing import build_housing_back, build_housing_body, orient_front_on_bed
from .image_processing import InvalidImage, decode_image, prepare_image, preview_png, resample_luminance
from .mesh import add_removable_support, apply_border, build_plate, removable_support_dimensions, validate_mesh
from .models import HousingParams, LithophaneParams
from .projects import CustomerProjectConfig, OrderReference, project_store

app = FastAPI(title="Lithophane Generator API", version="1.0.0")
cors_origins = [origin.strip() for origin in os.getenv(
    "LITHO_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def parse_params(raw: str) -> LithophaneParams:
    try:
        return LithophaneParams.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail={"error_code": "PARAM_OUT_OF_RANGE", "message": str(exc)}) from exc


async def read_image(upload: UploadFile) -> bytes:
    if upload.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_IMAGE_FORMAT", "message": "Wybierz plik JPEG lub PNG."})
    raw = await upload.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail={"error_code": "IMAGE_TOO_LARGE", "message": "Obraz przekracza 20 MB."})
    return raw


def pipeline(raw: bytes, params: LithophaneParams):
    try:
        image = prepare_image(decode_image(raw), params, for_mesh=True)
    except InvalidImage as exc:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_IMAGE_FORMAT", "message": str(exc)}) from exc
    image_width_mm = params.image_width_mm
    image_height_mm = params.image_height_mm
    borders = (params.border_top_mm, params.border_right_mm, params.border_bottom_mm, params.border_left_mm)
    cols, rows = grid_resolution(image_width_mm, image_height_mm, params.effective_resolution, border_widths_mm=borders)
    luminance = resample_luminance(image, cols, rows)
    heightmap = luminance_to_thickness(luminance, params.min_thickness_mm, params.max_thickness_mm, params.gamma, params.invert)
    heightmap, mesh_width, mesh_height = apply_border(heightmap, image_width_mm, image_height_mm, params.border_width_mm, params.effective_border_height, borders)
    mesh = build_plate(heightmap, mesh_width, mesh_height)
    if params.removable_support:
        mesh = add_removable_support(mesh, mesh_width, mesh_height, float(heightmap.max()), params.line_width_mm)
    validation = validate_mesh(mesh)
    if (not validation["watertight"] or validation["degenerate_faces"]
            or validation["winding_errors"] or not validation["positive_volume"]):
        raise HTTPException(status_code=500, detail={"error_code": "MESH_GENERATION_FAILED", "message": "Mesh validation failed", "validation": validation})
    return image, mesh, (cols, rows)


def load_customer_project(project_id: str, project_token: str | None) -> dict:
    try:
        metadata = project_store.load(project_id)
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_NOT_FOUND", "message": "Projekt nie istnieje."}) from exc
    if not project_store.authorize(metadata, project_token):
        raise HTTPException(status_code=403, detail={"error_code": "PROJECT_ACCESS_DENIED", "message": "Nieprawidłowy token projektu."})
    return metadata


def require_admin(admin_key: str | None) -> None:
    configured = os.getenv("LITHO_ADMIN_API_KEY", "")
    if not configured:
        raise HTTPException(status_code=503, detail={"error_code": "ADMIN_API_DISABLED", "message": "Panel administracyjny API nie został skonfigurowany."})
    if not admin_key or not secrets.compare_digest(configured, admin_key):
        raise HTTPException(status_code=403, detail={"error_code": "ADMIN_ACCESS_DENIED", "message": "Nieprawidłowy klucz administratora."})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/customer/projects", status_code=201)
def create_customer_project(config: CustomerProjectConfig):
    metadata, token = project_store.create(config)
    return {**project_store.public(metadata), "project_token": token}


@app.get("/api/customer/projects/{project_id}")
def get_customer_project(project_id: str, x_project_token: str | None = Header(None)):
    return project_store.public(load_customer_project(project_id, x_project_token))


@app.put("/api/customer/projects/{project_id}")
def update_customer_project(project_id: str, config: CustomerProjectConfig, x_project_token: str | None = Header(None)):
    load_customer_project(project_id, x_project_token)
    try:
        metadata = project_store.replace_config(project_id, config)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "PROJECT_GENERATING", "message": "Poczekaj na zakończenie generowania."}) from exc
    return project_store.public(metadata)


@app.post("/api/customer/projects/{project_id}/image")
async def upload_customer_project_image(
    project_id: str,
    image: UploadFile = File(...),
    x_project_token: str | None = Header(None),
):
    load_customer_project(project_id, x_project_token)
    raw = await read_image(image)
    try:
        decoded = decode_image(raw)
    except InvalidImage as exc:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_IMAGE_FORMAT", "message": "Nie można odczytać obrazu."}) from exc
    is_png = raw.startswith(b"\x89PNG\r\n\x1a\n")
    extension = ".png" if is_png else ".jpg"
    detected_content_type = "image/png" if is_png else "image/jpeg"
    filename = f"source{extension}"
    image_metadata = {
        "filename": filename,
        "original_name": Path(image.filename or filename).name,
        "content_type": detected_content_type,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "width_px": decoded.width,
        "height_px": decoded.height,
    }
    try:
        metadata = project_store.replace_image(project_id, filename, raw, image_metadata)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "PROJECT_GENERATING", "message": "Poczekaj na zakończenie generowania."}) from exc
    return project_store.public(metadata)


def generate_project_artifacts(project_id: str, generation_id: str) -> None:
    try:
        metadata = project_store.load(project_id)
        if metadata.get("generation_id") != generation_id or metadata["status"] != "generating":
            return
        raw = project_store.path(project_id, metadata["image"]["filename"]).read_bytes()
        settings = CustomerProjectConfig.model_validate(metadata["config"]).lithophane_params()
        _, mesh, (cols, rows) = pipeline(raw, settings)
        payload = binary_stl(mesh)
        filename = "lithophane.stl"
        artifact = {
            "filename": filename,
            "content_type": "model/stl",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "triangles": len(mesh.faces),
            "grid": f"{cols}x{rows}",
            "generator_version": os.getenv("LITHO_GENERATOR_VERSION", app.version),
        }
        project_store.finish_generation(project_id, generation_id, payload, artifact)
    except Exception:
        try:
            project_store.fail_generation(project_id, generation_id)
        except (FileNotFoundError, OSError, ValueError, KeyError):
            return


@app.post("/api/customer/projects/{project_id}/generate", status_code=202)
def generate_customer_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    x_project_token: str | None = Header(None),
):
    metadata = load_customer_project(project_id, x_project_token)
    generation_id = secrets.token_hex(16)
    try:
        metadata = project_store.begin_generation(project_id, generation_id)
    except RuntimeError as exc:
        if str(exc) == "image_required":
            raise HTTPException(status_code=409, detail={"error_code": "PROJECT_IMAGE_REQUIRED", "message": "Najpierw prześlij zdjęcie."}) from exc
        raise HTTPException(status_code=409, detail={"error_code": "PROJECT_ALREADY_GENERATING", "message": "Projekt jest już generowany."}) from exc
    background_tasks.add_task(generate_project_artifacts, project_id, generation_id)
    return project_store.public(metadata)


@app.get("/api/customer/projects/{project_id}/artifacts/{artifact_name}")
def download_customer_artifact(project_id: str, artifact_name: str, x_project_token: str | None = Header(None)):
    metadata = load_customer_project(project_id, x_project_token)
    artifact = metadata.get("artifacts", {}).get(artifact_name)
    if not artifact:
        raise HTTPException(status_code=404, detail={"error_code": "ARTIFACT_NOT_FOUND", "message": "Plik nie jest dostępny."})
    return FileResponse(project_store.path(project_id, artifact["filename"]), media_type=artifact["content_type"], filename=artifact["filename"])


@app.get("/api/admin/projects")
def list_customer_projects(x_litho_admin_key: str | None = Header(None)):
    require_admin(x_litho_admin_key)
    return {"projects": project_store.list()}


@app.get("/api/admin/projects/{project_id}")
def get_admin_project(project_id: str, x_litho_admin_key: str | None = Header(None)):
    require_admin(x_litho_admin_key)
    try:
        return project_store.public(project_store.load(project_id))
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_NOT_FOUND", "message": "Projekt nie istnieje."}) from exc


@app.get("/api/admin/projects/{project_id}/artifacts/{artifact_name}")
def download_admin_artifact(project_id: str, artifact_name: str, x_litho_admin_key: str | None = Header(None)):
    require_admin(x_litho_admin_key)
    try:
        metadata = project_store.load(project_id)
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_NOT_FOUND", "message": "Projekt nie istnieje."}) from exc
    artifact = metadata.get("artifacts", {}).get(artifact_name)
    if not artifact:
        raise HTTPException(status_code=404, detail={"error_code": "ARTIFACT_NOT_FOUND", "message": "Plik nie jest dostępny."})
    return FileResponse(project_store.path(project_id, artifact["filename"]), media_type=artifact["content_type"], filename=artifact["filename"])


@app.get("/api/admin/projects/{project_id}/source")
def download_admin_source(project_id: str, x_litho_admin_key: str | None = Header(None)):
    require_admin(x_litho_admin_key)
    try:
        metadata = project_store.load(project_id)
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_NOT_FOUND", "message": "Projekt nie istnieje."}) from exc
    if not metadata.get("image"):
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_IMAGE_NOT_FOUND", "message": "Zdjęcie nie jest dostępne."})
    image = metadata["image"]
    return FileResponse(project_store.path(project_id, image["filename"]), media_type=image["content_type"], filename=image["original_name"])


@app.put("/api/admin/projects/{project_id}/order")
def attach_project_order(project_id: str, reference: OrderReference, x_litho_admin_key: str | None = Header(None)):
    require_admin(x_litho_admin_key)
    try:
        metadata = project_store.attach_order(project_id, reference.order_id)
    except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_NOT_FOUND", "message": "Projekt nie istnieje."}) from exc
    return project_store.public(metadata)


@app.delete("/api/admin/projects/{project_id}", status_code=204)
def delete_admin_project(project_id: str, x_litho_admin_key: str | None = Header(None)):
    require_admin(x_litho_admin_key)
    try:
        project_store.delete(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "PROJECT_NOT_FOUND", "message": "Projekt nie istnieje."}) from exc


@app.exception_handler(RequestValidationError)
async def request_validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error_code": "PARAM_INVALID_TYPE", "message": str(exc)})


@app.exception_handler(Exception)
async def internal_error(_: Request, __: Exception):
    return JSONResponse(status_code=500, content={"error_code": "INTERNAL_ERROR", "message": "Unexpected server error"})


@app.post("/api/preview")
async def preview(image: UploadFile = File(...), params: str = Form(...)):
    settings = parse_params(params)
    raw = await read_image(image)
    try:
        prepared = prepare_image(decode_image(raw), settings)
    except InvalidImage as exc:
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_IMAGE_FORMAT", "message": str(exc)}) from exc
    return Response(preview_png(prepared), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/generate")
async def generate(image: UploadFile = File(...), params: str = Form(...)):
    settings = parse_params(params)
    raw = await read_image(image)
    _, mesh, (cols, rows) = pipeline(raw, settings)
    payload = binary_stl(mesh)
    _, support_extension, support_count = removable_support_dimensions(
        settings.height_mm, settings.max_thickness_mm, settings.width_mm
    )
    return Response(
        content=payload,
        media_type="model/stl",
        headers={
            "Content-Disposition": 'attachment; filename="lithophane.stl"',
            "Cache-Control": "no-store",
            "X-Triangle-Count": str(len(mesh.faces)),
            "X-Nozzle-Diameter-Mm": str(settings.nozzle_diameter_mm),
            "X-Quality-Profile": settings.quality_profile,
            "X-Sample-Pitch-Mm": str(settings.effective_sample_pitch_mm),
            "X-Effective-Sample-Pitch-Mm": str(max(settings.image_width_mm / (cols - 1), settings.image_height_mm / (rows - 1))),
            "X-Grid-Size": f"{cols}x{rows}",
            "X-Removable-Support": str(settings.removable_support).lower(),
            "X-Support-Extension-Mm": str(support_extension) if settings.removable_support else "0",
            "X-Support-Count": str(support_count) if settings.removable_support else "0",
        },
    )


@app.post("/api/housing/generate")
async def generate_housing(settings: HousingParams):
    body = orient_front_on_bed(build_housing_body(settings))
    back = orient_front_on_bed(build_housing_back(settings))
    validations = {"body": validate_mesh(body), "back": validate_mesh(back)}
    for name, validation in validations.items():
        if (not validation["watertight"] or validation["degenerate_faces"]
                or validation["winding_errors"] or not validation["positive_volume"]):
            raise HTTPException(
                status_code=500,
                detail={"error_code": "HOUSING_MESH_FAILED", "message": f"{name} mesh validation failed", "validation": validation},
            )
    output = BytesIO()
    prefix = f"litho-{settings.kind}-{settings.panel_width_mm:g}x{settings.panel_height_mm:g}"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"{prefix}-body.stl", binary_stl(body))
        archive.writestr(f"{prefix}-back.stl", binary_stl(back))
        archive.writestr(
            "README-PL.txt",
            (
                "LITHO - ZESTAW OBUDOWY V1\n\n"
                f"Typ: {settings.kind}\n"
                f"Panel Litho: {settings.panel_width_mm:g} x {settings.panel_height_mm:g} mm\n"
                f"Obudowa: {settings.outer_width_mm:g} x {settings.outer_height_mm:g} x {settings.depth_mm:g} mm\n"
                f"Kieszen panelu: {settings.panel_pocket_depth_mm:g} mm (panel {settings.panel_thickness_mm:g} mm + luz {settings.clearance_mm:g} mm)\n\n"
                "Oba pliki STL sa juz obrocone plaska strona do stolu i nie wymagaja podpor.\n"
                "Wloz panel od otwartego tylu i rownomiernie docisnij jego kolnierz do frontu.\n"
                f"Panel przejdzie pod {settings.panel_clip_count} sprezystymi zatrzaskami i zablokuje sie bez kleju.\n"
                "Po zwiazaniu kleju uloz oswietlenie i przewod, a nastepnie zamontuj tylna pokrywe.\n"
                "Przed drukiem produkcyjnym wykonaj krotka probe pasowania kieszeni dla swojego filamentu.\n"
            ).encode("utf-8"),
        )
    return Response(
        content=output.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{prefix}.zip"',
            "Cache-Control": "no-store",
            "X-Housing-Kind": settings.kind,
            "X-Panel-Size-Mm": f"{settings.panel_width_mm:g}x{settings.panel_height_mm:g}",
            "X-Housing-Outer-Size-Mm": f"{settings.outer_width_mm:g}x{settings.outer_height_mm:g}x{settings.depth_mm:g}",
            "X-Panel-Pocket-Depth-Mm": f"{settings.panel_pocket_depth_mm:g}",
            "X-Panel-Clip-Count": str(settings.panel_clip_count),
            "X-Print-Orientation": "front-face-down",
            "X-Body-Triangle-Count": str(len(body.faces)),
            "X-Back-Triangle-Count": str(len(back.faces)),
        },
    )
# W obrazie produkcyjnym frontend React jest kopiowany do /app/static.
# Montowanie następuje po trasach API, więc /api/* zachowuje pierwszeństwo.
STATIC_DIR = Path("/app/static")
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
