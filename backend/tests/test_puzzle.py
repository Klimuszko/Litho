from io import BytesIO
import json
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from app.main import app
from app.mesh import validate_mesh
from app.models import PuzzleParams
from app.puzzle import build_puzzle_3mf, build_puzzle_frame, prepare_puzzle, puzzle_piece_shapes


client = TestClient(app)
CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def sample_png() -> bytes:
    image = Image.new("RGB", (96, 120), "white")
    for y in range(image.height):
        for x in range(image.width):
            if x < image.width // 2 and y < image.height // 2:
                color = (20, 30, 45)
            elif x >= image.width // 2 and y < image.height // 2:
                color = (205, 65, 45)
            elif x < image.width // 2:
                color = (235, 190, 55)
            else:
                color = (242, 239, 224)
            image.putpixel((x, y), color)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def small_params(**overrides) -> PuzzleParams:
    values = {
        "width_mm": 100,
        "height_mm": 120,
        "piece_count": 36,
        "color_count": 4,
        "color_pixel_mm": 1.5,
        "frame_border_mm": 10,
    }
    values.update(overrides)
    return PuzzleParams(**values)


def test_defaults_are_the_recommended_product_configuration():
    params = PuzzleParams()
    assert (params.width_mm, params.height_mm) == (150, 200)
    assert params.piece_count == 100
    assert params.color_count == 4
    assert params.color_layout == "layered"
    assert params.image_style == "auto"
    assert params.detail_strength == pytest.approx(1.0)
    assert params.total_thickness_mm == pytest.approx(2.6)


def test_sepia_uses_an_ordered_warm_tonal_filament_palette():
    params = small_params(
        image_style="sepia",
        available_colors=[
            "#111111", "#7F4F24", "#B08968", "#F5F3E8", "#D62828", "#277DA1",
        ],
    )
    _, palette = prepare_puzzle(sample_png(), params)
    assert set(palette.hex_colors) == {"#111111", "#7F4F24", "#B08968", "#F5F3E8"}
    assert len(np.unique(palette.labels)) == 4


def test_jigsaw_edges_are_complementary_and_cover_the_picture():
    params = small_params()
    pieces = puzzle_piece_shapes(params, with_clearance=False)
    combined = unary_union([piece.shape for piece in pieces])
    expected = box(0, 0, params.width_mm, params.height_mm)
    assert len(pieces) == 36
    assert combined.symmetric_difference(expected).area < 1e-5
    assert sum(piece.shape.area for piece in pieces) == pytest.approx(expected.area, abs=1e-4)


def test_3mf_contains_separate_pieces_and_selected_filaments():
    payload, palette = build_puzzle_3mf(sample_png(), small_params())
    assert len(palette) == 4
    with ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert {
            "[Content_Types].xml",
            "_rels/.rels",
            "3D/3dmodel.model",
            "Metadata/model_settings.config",
            "Metadata/puzzle_settings.json",
        } <= names
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
        build_items = model.findall(f".//{{{CORE_NS}}}build/{{{CORE_NS}}}item")
        materials = model.findall(".//{http://schemas.microsoft.com/3dmanufacturing/material/2015/02}base")
        assert len(build_items) == 36
        assert len(materials) == 4
        config = ET.fromstring(archive.read("Metadata/model_settings.config"))
        extruders = {
            element.attrib["value"]
            for element in config.findall(".//metadata")
            if element.attrib.get("key") == "extruder"
        }
        assert extruders == {"1", "2", "3", "4"}
        settings = json.loads(archive.read("Metadata/puzzle_settings.json"))
        assert settings["piece_count"] == 36
        assert settings["palette"] == palette
        assert settings["dominant_base_color"] == palette[0]
        assert settings["color_layout"] == "layered"
        assert settings["image_style"] == "auto"
        assert settings["resolved_image_style"] == "sepia"
        assert settings["print_strategy"] == "dominant_base_then_one_filament_per_height_band"
        assert settings["color_change_heights_mm"] == [2.0, 2.2, 2.4]
        assert settings["shared_surface_band_mm"] is None


def test_same_layer_mode_creates_one_flat_multimaterial_surface_band():
    params = small_params(color_layout="same_layer")
    assert params.total_thickness_mm == pytest.approx(2.2)
    payload, palette = build_puzzle_3mf(sample_png(), params)

    with ZipFile(BytesIO(payload)) as archive:
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
        vertices = model.findall(f".//{{{CORE_NS}}}vertex")
        assert max(float(vertex.attrib["z"]) for vertex in vertices) == pytest.approx(2.2)

        settings = json.loads(archive.read("Metadata/puzzle_settings.json"))
        assert settings["palette"] == palette
        assert settings["color_layout"] == "same_layer"
        assert settings["print_strategy"] == "dominant_base_then_multimaterial_surface_band"
        assert settings["color_change_heights_mm"] == []
        assert settings["shared_surface_band_mm"] == [2.0, 2.2]


def test_frame_and_hinged_stand_are_watertight_and_fit_the_plate():
    params = small_params()
    frame, stand = build_puzzle_frame(params)
    for mesh in (frame, stand):
        result = validate_mesh(mesh)
        assert result["watertight"], result
        assert result["degenerate_faces"] == 0, result
        assert result["winding_errors"] == 0, result
        assert result["positive_volume"], result
    assert params.frame_outer_width_mm <= 250
    assert params.frame_total_height_mm <= 250


def test_puzzle_api_preview_generate_and_frame_endpoints():
    params = small_params()
    raw_params = params.model_dump_json()
    files = {"image": ("photo.png", sample_png(), "image/png")}

    preview = client.post("/api/puzzle/preview", files=files, data={"params": raw_params})
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "image/png"
    assert len(json.loads(preview.headers["x-puzzle-palette"])) == 4
    assert preview.headers["x-puzzle-image-style"] == "sepia"

    generated = client.post("/api/puzzle/generate", files=files, data={"params": raw_params})
    assert generated.status_code == 200, generated.text
    assert generated.headers["content-type"] == "model/3mf"
    assert generated.content.startswith(b"PK")

    frame = client.post("/api/puzzle/frame", json=params.model_dump())
    assert frame.status_code == 200, frame.text
    assert frame.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(frame.content)) as archive:
        names = archive.namelist()
        assert sum(name.endswith(".stl") for name in names) == 2
        assert "README-PL.txt" in names


def test_rejects_frame_larger_than_250_mm_plate():
    with pytest.raises(ValueError, match="250 x 250"):
        PuzzleParams(width_mm=230, height_mm=230)
