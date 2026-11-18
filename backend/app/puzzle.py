from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import math
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw
import shapely
import shapely.affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .exporter import binary_stl
from .image_processing import decode_image, prepare_puzzle_image
from .mesh import Mesh, combine_meshes, validate_mesh
from .models import PuzzleParams


CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MATERIAL_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MODEL_RELATIONSHIP = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"

ET.register_namespace("", CORE_NS)
ET.register_namespace("m", MATERIAL_NS)


@dataclass(frozen=True)
class PuzzlePiece:
    index: int
    row: int
    column: int
    shape: Polygon


@dataclass(frozen=True)
class PuzzlePalette:
    labels: np.ndarray
    colors: tuple[tuple[int, int, int], ...]

    @property
    def hex_colors(self) -> list[str]:
        return [f"#{red:02X}{green:02X}{blue:02X}" for red, green, blue in self.colors]


def _vertical_direction(row: int, boundary: int) -> int:
    return 1 if ((row * 37 + boundary * 17 + 11) % 4) < 2 else -1


def _horizontal_direction(boundary: int, column: int) -> int:
    return 1 if ((boundary * 29 + column * 19 + 7) % 4) < 2 else -1


def _vertical_tab(x: float, center_y: float, depth: float, direction: int):
    head_radius = depth * 0.46
    head_center_x = x + direction * depth * 0.70
    neck_end_x = x + direction * depth * 0.62
    neck_half = depth * 0.21
    neck = box(min(x, neck_end_x), center_y - neck_half, max(x, neck_end_x), center_y + neck_half)
    return unary_union((neck, Point(head_center_x, center_y).buffer(head_radius, quad_segs=8)))


def _horizontal_tab(center_x: float, y: float, depth: float, direction: int):
    head_radius = depth * 0.46
    head_center_y = y + direction * depth * 0.70
    neck_end_y = y + direction * depth * 0.62
    neck_half = depth * 0.21
    neck = box(center_x - neck_half, min(y, neck_end_y), center_x + neck_half, max(y, neck_end_y))
    return unary_union((neck, Point(center_x, head_center_y).buffer(head_radius, quad_segs=8)))


def puzzle_piece_shapes(params: PuzzleParams, *, with_clearance: bool = True) -> list[PuzzlePiece]:
    grid = params.grid_size
    piece_width = params.piece_width_mm
    piece_height = params.piece_height_mm
    tab_depth = min(piece_width, piece_height) * 0.22
    pieces: list[PuzzlePiece] = []

    for row in range(grid):
        y0 = params.height_mm - (row + 1) * piece_height
        y1 = params.height_mm - row * piece_height
        for column in range(grid):
            x0 = column * piece_width
            x1 = (column + 1) * piece_width
            shape = box(x0, y0, x1, y1)

            if column > 0:
                direction = _vertical_direction(row, column)
                tab = _vertical_tab(x0, (y0 + y1) / 2, tab_depth, direction)
                shape = shape.difference(tab) if direction > 0 else shape.union(tab)
            if column < grid - 1:
                direction = _vertical_direction(row, column + 1)
                tab = _vertical_tab(x1, (y0 + y1) / 2, tab_depth, direction)
                shape = shape.union(tab) if direction > 0 else shape.difference(tab)
            if row > 0:
                direction = _horizontal_direction(row, column)
                tab = _horizontal_tab((x0 + x1) / 2, y1, tab_depth, direction)
                shape = shape.union(tab) if direction > 0 else shape.difference(tab)
            if row < grid - 1:
                direction = _horizontal_direction(row + 1, column)
                tab = _horizontal_tab((x0 + x1) / 2, y0, tab_depth, direction)
                shape = shape.difference(tab) if direction > 0 else shape.union(tab)

            shape = shape.buffer(0)
            if with_clearance:
                shape = shape.buffer(-params.piece_clearance_mm / 2, join_style=1).buffer(0)
            if shape.is_empty or shape.geom_type != "Polygon":
                raise ValueError("Puzzle geometry became invalid")
            pieces.append(PuzzlePiece(row * grid + column + 1, row, column, orient(shape, 1)))
    return pieces


def _quantize(image: Image.Image, params: PuzzleParams) -> PuzzlePalette:
    columns = max(2, round(params.width_mm / params.color_pixel_mm))
    rows = max(2, round(params.height_mm / params.color_pixel_mm))
    reduced = np.asarray(
        image.resize((columns, rows), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    pixels = reduced.reshape(-1, 3)
    available = np.asarray([
        tuple(int(color[offset:offset + 2], 16) for offset in (1, 3, 5))
        for color in params.available_colors
    ], dtype=np.float32)

    def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
        srgb = rgb / 255.0
        linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        xyz = linear @ np.asarray([
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ], dtype=np.float32).T
        xyz /= np.asarray([0.95047, 1.0, 1.08883], dtype=np.float32)
        delta = 6 / 29
        transformed = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4 / 29)
        return np.column_stack((
            116 * transformed[:, 1] - 16,
            500 * (transformed[:, 0] - transformed[:, 1]),
            200 * (transformed[:, 1] - transformed[:, 2]),
        ))

    pixel_lab = rgb_to_lab(pixels)
    available_lab = rgb_to_lab(available)
    distances = np.sum((pixel_lab[:, None, :] - available_lab[None, :, :]) ** 2, axis=2)

    # Start from the available filament which naturally covers the largest
    # part of the image, then greedily add colors which reduce the perceptual
    # error most. This constrains the result to filament the user really owns.
    all_assignments = np.argmin(distances, axis=1)
    selected = [int(np.argmax(np.bincount(all_assignments, minlength=len(available))))]
    best_distance = distances[:, selected[0]].copy()
    while len(selected) < params.color_count:
        improvements = np.maximum(best_distance[:, None] - distances, 0).sum(axis=0)
        improvements[selected] = -1
        candidate = int(np.argmax(improvements))
        selected.append(candidate)
        best_distance = np.minimum(best_distance, distances[:, candidate])

    selected_distances = distances[:, selected]
    raw_labels = np.argmin(selected_distances, axis=1)
    counts = np.bincount(raw_labels, minlength=len(selected))
    dominant = int(np.argmax(counts))
    order = [dominant, *[index for index in range(len(selected)) if index != dominant]]
    remap = np.empty(len(order), dtype=np.int16)
    for new_index, old_index in enumerate(order):
        remap[old_index] = new_index
    labels = remap[raw_labels].reshape(rows, columns)
    colors = tuple(
        tuple(int(channel) for channel in available[selected[index]])
        for index in order
    )
    return PuzzlePalette(labels, colors)


def prepare_puzzle(raw: bytes, params: PuzzleParams) -> tuple[Image.Image, PuzzlePalette]:
    image = prepare_puzzle_image(decode_image(raw), params)
    return image, _quantize(image, params)


def puzzle_preview_png(raw: bytes, params: PuzzleParams) -> tuple[bytes, list[str]]:
    _, palette = prepare_puzzle(raw, params)
    rgb = np.asarray(palette.colors, dtype=np.uint8)[palette.labels]
    preview = Image.fromarray(rgb)
    maximum = 900
    scale = min(maximum / params.width_mm, maximum / params.height_mm)
    preview = preview.resize(
        (max(1, round(params.width_mm * scale)), max(1, round(params.height_mm * scale))),
        Image.Resampling.NEAREST,
    )
    draw = ImageDraw.Draw(preview)
    line_width = max(1, round(scale * 0.28))
    for piece in puzzle_piece_shapes(params, with_clearance=False):
        points = [
            (round(x * scale), round((params.height_mm - y) * scale))
            for x, y in piece.shape.exterior.coords
        ]
        draw.line(points, fill=(20, 24, 31), width=line_width, joint="curve")
    output = BytesIO()
    preview.save(output, "PNG", optimize=True)
    return output.getvalue(), palette.hex_colors


def _polygon_parts(geometry) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [orient(geometry, 1)]
    if isinstance(geometry, MultiPolygon):
        return [orient(part, 1) for part in geometry.geoms if part.area > 1e-5]
    return [
        orient(part, 1)
        for part in getattr(geometry, "geoms", ())
        if isinstance(part, Polygon) and part.area > 1e-5
    ]


def extrude_geometry(geometry, z0: float, z1: float) -> Mesh:
    meshes: list[Mesh] = []
    for polygon in _polygon_parts(geometry):
        vertices: list[tuple[float, float, float]] = []
        vertex_ids: dict[tuple[float, float, float], int] = {}
        faces: list[tuple[int, int, int]] = []

        def vertex(x: float, y: float, z: float) -> int:
            key = (round(float(x), 6), round(float(y), 6), round(float(z), 6))
            if key not in vertex_ids:
                vertex_ids[key] = len(vertices)
                vertices.append(key)
            return vertex_ids[key]

        triangles = shapely.constrained_delaunay_triangles(polygon)
        for triangle in triangles.geoms:
            if not polygon.covers(triangle.representative_point()):
                continue
            coordinates = list(triangle.exterior.coords)[:3]
            cross = (
                (coordinates[1][0] - coordinates[0][0]) * (coordinates[2][1] - coordinates[0][1])
                - (coordinates[1][1] - coordinates[0][1]) * (coordinates[2][0] - coordinates[0][0])
            )
            if cross < 0:
                coordinates[1], coordinates[2] = coordinates[2], coordinates[1]
            bottom = [vertex(x, y, z0) for x, y in coordinates]
            top = [vertex(x, y, z1) for x, y in coordinates]
            faces.append((top[0], top[1], top[2]))
            faces.append((bottom[0], bottom[2], bottom[1]))

        for ring in (polygon.exterior, *polygon.interiors):
            coordinates = list(ring.coords)
            for (ax, ay), (bx, by) in zip(coordinates, coordinates[1:]):
                a0 = vertex(ax, ay, z0)
                b0 = vertex(bx, by, z0)
                b1 = vertex(bx, by, z1)
                a1 = vertex(ax, ay, z1)
                faces.extend(((a0, b0, b1), (a0, b1, a1)))

        meshes.append(Mesh(np.asarray(vertices, dtype=np.float32), np.asarray(faces, dtype=np.int32)))
    if not meshes:
        raise ValueError("Cannot extrude empty geometry")
    return meshes[0] if len(meshes) == 1 else combine_meshes(*meshes)


def _rectangles_for_label(labels: np.ndarray, label: int, width: float, height: float):
    rows, columns = labels.shape
    dx, dy = width / columns, height / rows
    active: dict[tuple[int, int], int] = {}
    rectangles = []

    for row in range(rows + 1):
        spans: list[tuple[int, int]] = []
        if row < rows:
            column = 0
            while column < columns:
                if labels[row, column] != label:
                    column += 1
                    continue
                start = column
                column += 1
                while column < columns and labels[row, column] == label:
                    column += 1
                spans.append((start, column))
        current = set(spans)
        for span, start_row in list(active.items()):
            if span not in current:
                x0, x1 = span[0] * dx, span[1] * dx
                y0, y1 = height - row * dy, height - start_row * dy
                rectangles.append(box(x0, y0, x1, y1))
                del active[span]
        for span in spans:
            active.setdefault(span, row)
    return unary_union(rectangles) if rectangles else Polygon()


def _mesh_xml(parent, mesh: Mesh):
    mesh_element = ET.SubElement(parent, f"{{{CORE_NS}}}mesh")
    vertices_element = ET.SubElement(mesh_element, f"{{{CORE_NS}}}vertices")
    for x, y, z in mesh.vertices:
        ET.SubElement(
            vertices_element,
            f"{{{CORE_NS}}}vertex",
            {"x": f"{x:.5f}", "y": f"{y:.5f}", "z": f"{z:.5f}"},
        )
    triangles_element = ET.SubElement(mesh_element, f"{{{CORE_NS}}}triangles")
    for first, second, third in mesh.faces:
        ET.SubElement(
            triangles_element,
            f"{{{CORE_NS}}}triangle",
            {"v1": str(int(first)), "v2": str(int(second)), "v3": str(int(third))},
        )


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build_puzzle_3mf(raw: bytes, params: PuzzleParams) -> tuple[bytes, list[str]]:
    _, palette = prepare_puzzle(raw, params)
    pieces = puzzle_piece_shapes(params)
    exact_color_shapes = [
        _rectangles_for_label(palette.labels, color, params.width_mm, params.height_mm)
        for color in range(params.color_count)
    ]
    if params.color_layout == "layered":
        # Each higher mask is a subset of the previous one. A pixel assigned to
        # color N receives all lower masks and color N becomes its exposed top.
        # Consequently the printer uses exactly one filament in every Z band.
        color_volumes = [
            (
                color_index,
                unary_union(exact_color_shapes[color_index:]),
                params.base_thickness_mm + (color_index - 1) * params.color_thickness_mm,
                params.base_thickness_mm + color_index * params.color_thickness_mm,
                f"Warstwa koloru {color_index + 1}",
            )
            for color_index in range(1, params.color_count)
        ]
    else:
        # Exact color masks share one top band. This creates a flat image
        # surface for AMS and other multi-material systems.
        color_volumes = [
            (
                color_index,
                exact_color_shapes[color_index],
                params.base_thickness_mm,
                params.total_thickness_mm,
                f"Kolor powierzchni {color_index + 1}",
            )
            for color_index in range(params.color_count)
        ]

    model = ET.Element(
        f"{{{CORE_NS}}}model",
        {
            "unit": "millimeter",
            "{http://www.w3.org/XML/1998/namespace}lang": "pl-PL",
            "requiredextensions": "m",
        },
    )
    ET.SubElement(model, f"{{{CORE_NS}}}metadata", {"name": "Title"}).text = "Litho Puzzle"
    ET.SubElement(model, f"{{{CORE_NS}}}metadata", {"name": "Designer"}).text = "Litho"
    resources = ET.SubElement(model, f"{{{CORE_NS}}}resources")
    materials = ET.SubElement(resources, f"{{{MATERIAL_NS}}}basematerials", {"id": "1"})
    for index, (red, green, blue) in enumerate(palette.colors, start=1):
        ET.SubElement(
            materials,
            f"{{{MATERIAL_NS}}}base",
            {"name": f"Filament {index}", "displaycolor": f"#{red:02X}{green:02X}{blue:02X}FF"},
        )

    build = ET.SubElement(model, f"{{{CORE_NS}}}build")
    model_config = ET.Element("config")
    plate_config = ET.SubElement(model_config, "plate")
    ET.SubElement(plate_config, "metadata", {"key": "plater_id", "value": "1"})
    ET.SubElement(plate_config, "metadata", {"key": "plater_name", "value": "Litho Puzzle"})
    ET.SubElement(plate_config, "metadata", {"key": "locked", "value": "false"})
    filament_map = " ".join(str(index) for index in range(1, params.color_count + 1))
    ET.SubElement(plate_config, "metadata", {"key": "filament_maps", "value": filament_map})
    ET.SubElement(
        plate_config,
        "metadata",
        {"key": "filament_volume_maps", "value": " ".join("1" for _ in range(params.color_count))},
    )

    next_object_id = 2
    exploded_gap = 1.2
    margin = 3.0
    for piece in pieces:
        x_offset = margin + piece.column * exploded_gap
        y_offset = margin + (params.grid_size - 1 - piece.row) * exploded_gap
        translated_piece = shapely.affinity.translate(piece.shape, xoff=x_offset, yoff=y_offset)
        parts: list[tuple[int, int, str]] = []

        base_id = next_object_id
        next_object_id += 1
        base_object = ET.SubElement(
            resources,
            f"{{{CORE_NS}}}object",
            {"id": str(base_id), "type": "model", "name": f"Puzzle {piece.index:03d} - baza", "pid": "1", "pindex": "0"},
        )
        _mesh_xml(base_object, extrude_geometry(translated_piece, 0, params.base_thickness_mm))
        parts.append((base_id, 1, "Baza"))

        for color_index, color_shape, z_min, z_max, part_name in color_volumes:
            clipped = color_shape.intersection(piece.shape)
            if clipped.is_empty or clipped.area < 1e-4:
                continue
            translated = shapely.affinity.translate(clipped, xoff=x_offset, yoff=y_offset)
            child_id = next_object_id
            next_object_id += 1
            child = ET.SubElement(
                resources,
                f"{{{CORE_NS}}}object",
                {
                    "id": str(child_id),
                    "type": "model",
                    "name": f"Puzzle {piece.index:03d} - kolor {color_index + 1}",
                    "pid": "1",
                    "pindex": str(color_index),
                },
            )
            _mesh_xml(
                child,
                extrude_geometry(translated, z_min, z_max),
            )
            parts.append((child_id, color_index + 1, part_name))

        parent_id = next_object_id
        next_object_id += 1
        parent = ET.SubElement(
            resources,
            f"{{{CORE_NS}}}object",
            {"id": str(parent_id), "type": "model", "name": f"Puzzle {piece.index:03d}"},
        )
        components = ET.SubElement(parent, f"{{{CORE_NS}}}components")
        for child_id, _, _ in parts:
            ET.SubElement(components, f"{{{CORE_NS}}}component", {"objectid": str(child_id)})
        ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": str(parent_id), "printable": "1"})

        config_object = ET.SubElement(model_config, "object", {"id": str(parent_id)})
        ET.SubElement(config_object, "metadata", {"key": "name", "value": f"Puzzle {piece.index:03d}"})
        ET.SubElement(config_object, "metadata", {"key": "extruder", "value": "1"})
        for child_id, extruder, name in parts:
            part = ET.SubElement(
                config_object,
                "part",
                {"id": str(child_id), "subtype": "normal_part"},
            )
            ET.SubElement(part, "metadata", {"key": "name", "value": name})
            ET.SubElement(part, "metadata", {"key": "extruder", "value": str(extruder)})

        instance = ET.SubElement(plate_config, "model_instance")
        ET.SubElement(instance, "metadata", {"key": "object_id", "value": str(parent_id)})
        ET.SubElement(instance, "metadata", {"key": "instance_id", "value": "0"})

    content_types = ET.Element(f"{{{CONTENT_TYPES_NS}}}Types")
    ET.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"},
    )
    ET.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        {"Extension": "model", "ContentType": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"},
    )
    ET.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        {"Extension": "config", "ContentType": "application/xml"},
    )
    ET.SubElement(
        content_types,
        f"{{{CONTENT_TYPES_NS}}}Default",
        {"Extension": "json", "ContentType": "application/json"},
    )
    relationships = ET.Element(f"{{{RELATIONSHIPS_NS}}}Relationships")
    ET.SubElement(
        relationships,
        f"{{{RELATIONSHIPS_NS}}}Relationship",
        {"Target": "/3D/3dmodel.model", "Id": "rel0", "Type": MODEL_RELATIONSHIP},
    )
    settings = {
        "width_mm": params.width_mm,
        "height_mm": params.height_mm,
        "piece_count": params.piece_count,
        "color_count": params.color_count,
        "color_layout": params.color_layout,
        "palette": palette.hex_colors,
        "dominant_base_color": palette.hex_colors[0],
        "print_strategy": (
            "dominant_base_then_one_filament_per_height_band"
            if params.color_layout == "layered"
            else "dominant_base_then_multimaterial_surface_band"
        ),
        "base_thickness_mm": params.base_thickness_mm,
        "color_layer_height_mm": params.color_thickness_mm,
        "total_thickness_mm": params.total_thickness_mm,
        "color_change_heights_mm": (
            [
                round(params.base_thickness_mm + index * params.color_thickness_mm, 3)
                for index in range(params.color_count - 1)
            ]
            if params.color_layout == "layered"
            else []
        ),
        "shared_surface_band_mm": (
            [params.base_thickness_mm, params.total_thickness_mm]
            if params.color_layout == "same_layer"
            else None
        ),
        "piece_clearance_mm": params.piece_clearance_mm,
    }

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", _xml_bytes(content_types))
        archive.writestr("_rels/.rels", _xml_bytes(relationships))
        archive.writestr("3D/3dmodel.model", _xml_bytes(model))
        archive.writestr("Metadata/model_settings.config", _xml_bytes(model_config))
        archive.writestr("Metadata/puzzle_settings.json", json.dumps(settings, ensure_ascii=False, indent=2))
    return output.getvalue(), palette.hex_colors


def _tube_x(
    x0: float,
    x1: float,
    center_y: float,
    center_z: float,
    outer_radius: float,
    inner_radius: float,
    segments: int = 32,
) -> Mesh:
    vertices: list[tuple[float, float, float]] = []
    for x in (x0, x1):
        for radius in (outer_radius, inner_radius):
            for index in range(segments):
                angle = 2 * math.pi * index / segments
                vertices.append((x, center_y + radius * math.cos(angle), center_z + radius * math.sin(angle)))
    points = np.asarray(vertices, dtype=np.float32)
    faces: list[tuple[int, int, int]] = []

    def index(x_side: int, radius_side: int, segment: int) -> int:
        return (x_side * 2 + radius_side) * segments + segment % segments

    def quad(a: int, b: int, c: int, d: int, normal: np.ndarray):
        pa, pb, pc = points[[a, b, c]]
        if np.dot(np.cross(pb - pa, pc - pa), normal) < 0:
            b, d = d, b
        faces.extend(((a, b, c), (a, c, d)))

    for current in range(segments):
        following = (current + 1) % segments
        angle = 2 * math.pi * (current + 0.5) / segments
        radial = np.array([0.0, math.cos(angle), math.sin(angle)])
        quad(index(0, 0, current), index(0, 0, following), index(1, 0, following), index(1, 0, current), radial)
        quad(index(0, 1, current), index(1, 1, current), index(1, 1, following), index(0, 1, following), -radial)
        quad(index(0, 0, current), index(0, 1, current), index(0, 1, following), index(0, 0, following), np.array([-1.0, 0.0, 0.0]))
        quad(index(1, 0, current), index(1, 0, following), index(1, 1, following), index(1, 1, current), np.array([1.0, 0.0, 0.0]))
    return Mesh(points, np.asarray(faces, dtype=np.int32))


def build_puzzle_frame(params: PuzzleParams) -> tuple[Mesh, Mesh]:
    outer_width = params.frame_outer_width_mm
    outer_height = params.frame_outer_height_mm
    border = params.frame_border_mm
    back_thickness = 1.8
    rim_top = back_thickness + params.total_thickness_mm + 0.9
    outer = box(0, 0, outer_width, outer_height)
    cavity_width = params.width_mm + params.frame_clearance_mm
    cavity_height = params.height_mm + params.frame_clearance_mm
    cavity_x0 = (outer_width - cavity_width) / 2
    cavity_y0 = (outer_height - cavity_height) / 2
    cavity = box(cavity_x0, cavity_y0, cavity_x0 + cavity_width, cavity_y0 + cavity_height)

    keyholes = []
    for center_x in (outer_width * 0.32, outer_width * 0.68):
        center_y = outer_height - 6.5
        keyholes.append(
            unary_union((
                Point(center_x, center_y - 4).buffer(4, quad_segs=12),
                box(center_x - 1.8, center_y - 4, center_x + 1.8, center_y + 6),
            ))
        )
    back = extrude_geometry(outer.difference(unary_union(keyholes)), 0, back_thickness)
    rim = extrude_geometry(outer.difference(cavity), back_thickness, rim_top)
    # A shallow, support-free overlap retains the finished puzzle when the
    # frame is standing or hanging. Its 1.2 mm bridge is printable without
    # supports and still leaves almost the entire picture visible.
    lip_window = cavity.buffer(-1.2, join_style=2)
    retaining_lip = extrude_geometry(outer.difference(lip_window), rim_top - 0.8, rim_top)

    hinge_center = outer_width / 2
    hinge_radius = 2.8
    hinge_y = -hinge_radius
    hinge_z = hinge_radius
    left_hinge = _tube_x(hinge_center - 13.2, hinge_center - 6.2, hinge_y, hinge_z, hinge_radius, 1.7)
    right_hinge = _tube_x(hinge_center + 6.2, hinge_center + 13.2, hinge_y, hinge_z, hinge_radius, 1.7)
    frame = combine_meshes(back, rim, retaining_lip, left_hinge, right_hinge)

    stand_outline = Polygon([(-6, -1), (6, -1), (22, -95), (-22, -95)])
    stand_plate = extrude_geometry(stand_outline, 0, 3)
    stand_hinge = _tube_x(-5.7, 5.7, 0, hinge_z, 2.65, 1.7)
    stand = combine_meshes(stand_plate, stand_hinge)
    return frame, stand


def build_puzzle_frame_zip(params: PuzzleParams) -> bytes:
    frame, stand = build_puzzle_frame(params)
    for name, mesh in (("frame", frame), ("stand", stand)):
        validation = validate_mesh(mesh)
        if (
            not validation["watertight"]
            or validation["degenerate_faces"]
            or validation["winding_errors"]
            or not validation["positive_volume"]
        ):
            raise ValueError(f"{name} mesh validation failed: {validation}")

    readme = (
        "LITHO PUZZLE - RAMKA UNIWERSALNA\n\n"
        f"Pole puzzli: {params.width_mm:g} x {params.height_mm:g} mm\n"
        f"Ramka: {params.frame_outer_width_mm:g} x {params.frame_outer_height_mm:g} mm\n"
        f"Luz pola puzzli: {params.frame_clearance_mm:g} mm\n\n"
        "frame.stl zawiera tacke z podwyzszonym rantem, dwa otwory typu keyhole do powieszenia oraz dwa ucha zawiasu.\n"
        "Przedni rant zachodzi 1,2 mm na krawedzie puzzli i zabezpiecza je po ustawieniu ramki pionowo.\n"
        "stand.stl to skladana nozka. Polacz ja z ramka popularna sruba M3 x 30 mm i nakretka M3.\n"
        "Do powieszenia zloz nozke plasko za ramka i uzyj dwoch wkretow z glowkami pasujacymi do otworow keyhole.\n"
        "Oba zastosowania sa dostepne w tym samym komplecie - nie trzeba drukowac drugiej ramki.\n"
    )
    output = BytesIO()
    prefix = f"litho-puzzle-frame-{params.width_mm:g}x{params.height_mm:g}"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(f"{prefix}-frame.stl", binary_stl(frame))
        archive.writestr(f"{prefix}-stand.stl", binary_stl(stand))
        archive.writestr("README-PL.txt", readme.encode("utf-8"))
    return output.getvalue()
