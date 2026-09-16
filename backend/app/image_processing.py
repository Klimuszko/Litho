from io import BytesIO
import math

import numpy as np
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

from .models import LithophaneParams

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8000


class InvalidImage(ValueError):
    pass


def crop_to_aspect(image: Image.Image, target_aspect: float) -> Image.Image:
    """Center-crop an already selected region without stretching it."""
    current_aspect = image.width / image.height
    if current_aspect > target_aspect:
        width = max(1, round(image.height * target_aspect))
        left = (image.width - width) // 2
        return image.crop((left, 0, left + width, image.height))
    if current_aspect < target_aspect:
        height = max(1, round(image.width / target_aspect))
        top = (image.height - height) // 2
        return image.crop((0, top, image.width, top + height))
    return image


def inscribed_size(width: float, height: float, angle_degrees: float) -> tuple[float, float]:
    """Largest axis-aligned rectangle fully covered by a rotated rectangle."""
    angle = math.radians(abs(angle_degrees) % 180)
    if angle > math.pi / 2:
        angle = math.pi - angle
    if angle < 1e-10:
        return width, height
    sin_a, cos_a = math.sin(angle), math.cos(angle)
    if abs(cos_a) < 1e-10:
        return height, width
    long_side, short_side = max(width, height), min(width, height)
    if short_side <= 2 * sin_a * cos_a * long_side:
        half_short = 0.5 * short_side
        if width >= height:
            result_width, result_height = half_short / sin_a, half_short / cos_a
        else:
            result_width, result_height = half_short / cos_a, half_short / sin_a
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        result_width = (width * cos_a - height * sin_a) / cos_2a
        result_height = (height * cos_a - width * sin_a) / cos_2a
    return max(1.0, result_width), max(1.0, result_height)


def rotate_and_inscribe(image: Image.Image, angle_degrees: float) -> Image.Image:
    angle = angle_degrees % 360
    if abs(angle) < 1e-10:
        return image
    quarter_turn = round(angle / 90)
    if abs(angle - quarter_turn * 90) < 1e-10:
        transpose = {
            1: Image.Transpose.ROTATE_270,
            2: Image.Transpose.ROTATE_180,
            3: Image.Transpose.ROTATE_90,
            4: None,
        }[quarter_turn]
        return image if transpose is None else image.transpose(transpose)
    rotated = image.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    width, height = inscribed_size(image.width, image.height, angle)
    target_width = max(1, round(width))
    target_height = max(1, round(height))
    left = round((rotated.width - target_width) / 2)
    top = round((rotated.height - target_height) / 2)
    return rotated.crop((left, top, left + target_width, top + target_height))


def decode_image(raw: bytes) -> Image.Image:
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidImage("Image is empty or exceeds 20 MB")
    try:
        image = Image.open(BytesIO(raw))
        if image.format not in {"JPEG", "PNG"}:
            raise InvalidImage("Only JPEG and PNG are supported")
        if min(image.size) < 8 or max(image.size) > MAX_IMAGE_DIMENSION:
            raise InvalidImage("Image dimensions must be between 8 and 8000 pixels")
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImage("Invalid JPEG or PNG image") from exc
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")


def prepare_image(image: Image.Image, params: LithophaneParams) -> Image.Image:
    image = rotate_and_inscribe(image, params.rotation_degrees)
    crop = params.crop
    left = round(crop.x * image.width)
    top = round(crop.y * image.height)
    right = round((crop.x + crop.width) * image.width)
    bottom = round((crop.y + crop.height) * image.height)
    image = image.crop((left, top, max(left + 1, right), max(top + 1, bottom)))
    image = crop_to_aspect(image, params.image_width_mm / params.image_height_mm)
    if params.mirror:
        image = ImageOps.mirror(image)
    image = ImageEnhance.Brightness(image).enhance(params.brightness)
    image = ImageEnhance.Contrast(image).enhance(params.contrast)
    return image.convert("L")


def resample_luminance(image: Image.Image, cols: int, rows: int) -> np.ndarray:
    resized = image.resize((cols, rows), Image.Resampling.LANCZOS)
    return np.asarray(resized, dtype=np.float32) / 255.0


def preview_png(image: Image.Image, max_size: int = 900) -> bytes:
    copy = image.copy()
    copy.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    output = BytesIO()
    copy.save(output, "PNG", optimize=True)
    return output.getvalue()
