from io import BytesIO

import numpy as np
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError

from .models import LithophaneParams

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8000


class InvalidImage(ValueError):
    pass


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
    crop = params.crop
    left = round(crop.x * image.width)
    top = round(crop.y * image.height)
    right = round((crop.x + crop.width) * image.width)
    bottom = round((crop.y + crop.height) * image.height)
    image = image.crop((left, top, max(left + 1, right), max(top + 1, bottom)))
    if params.mirror:
        image = ImageOps.mirror(image)
    target_landscape = params.orientation == "landscape"
    model_landscape = params.height_mm is None or params.width_mm >= params.height_mm
    if target_landscape != model_landscape:
        image = image.transpose(Image.Transpose.ROTATE_90)
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
