import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .exporter import binary_stl
from .heightmap import grid_resolution, luminance_to_thickness
from .housing import build_housing_back, build_housing_body
from .image_processing import InvalidImage, decode_image, prepare_image, preview_png, resample_luminance
from .mesh import add_removable_support, apply_border, build_plate, removable_support_dimensions, validate_mesh
from .models import HousingParams, LithophaneParams

app = FastAPI(title="Lithophane Generator API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


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
    body = build_housing_body(settings)
    back = build_housing_back(settings)
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
                f"Rowek: {settings.slot_width_mm:g} mm (panel {settings.panel_thickness_mm:g} mm + luz {settings.clearance_mm:g} mm)\n\n"
                "Korpus drukuj frontem polozonym na stole. Tylna pokrywe drukuj plaska strona na stole, rantem do gory.\n"
                "Panel wsun od gory. Pokrywe zamontuj z tylu po ulozeniu oswietlenia i przewodu.\n"
                "Przed drukiem produkcyjnym wykonaj krotka probe pasowania rowka dla swojego filamentu.\n"
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
            "X-Panel-Slot-Mm": f"{settings.slot_width_mm:g}",
            "X-Body-Triangle-Count": str(len(body.faces)),
            "X-Back-Triangle-Count": str(len(back.faces)),
        },
    )
# W obrazie produkcyjnym frontend React jest kopiowany do /app/static.
# Montowanie następuje po trasach API, więc /api/* zachowuje pierwszeństwo.
STATIC_DIR = Path("/app/static")
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
