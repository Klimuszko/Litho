from PIL import Image

from app.image_processing import crop_to_aspect, inscribed_size, prepare_image, rotate_and_inscribe
from app.models import LithophaneParams


def test_wide_image_is_center_cropped_without_stretching():
    image = Image.new("RGB", (400, 200))
    result = crop_to_aspect(image, 1.5)
    assert result.size == (300, 200)


def test_tall_image_is_center_cropped_without_stretching():
    image = Image.new("RGB", (200, 400))
    result = crop_to_aspect(image, 2 / 3)
    assert result.size == (200, 300)


def test_matching_aspect_is_left_untouched():
    image = Image.new("RGB", (300, 200))
    result = crop_to_aspect(image, 1.5)
    assert result.size == (300, 200)


def test_extremely_thin_region_never_collapses_to_zero_pixels():
    image = Image.new("RGB", (400, 4))
    result = crop_to_aspect(image, 0.1)
    assert result.width >= 1 and result.height >= 1


def test_prepare_image_never_deforms_a_full_frame_crop_with_mismatched_aspect():
    # A 4:3 photo submitted with a full-frame crop (0,0,1,1) against a 3:2 preset:
    # the API request itself does not encode the preset's aspect ratio, so the
    # backend must derive it rather than stretch the pixels to fit.
    image = Image.new("RGB", (400, 300))
    params = LithophaneParams(width_mm=150, height_mm=100, orientation="landscape")
    prepared = prepare_image(image, params)
    assert abs(prepared.width / prepared.height - 150 / 100) < 0.02


def test_prepare_image_corrects_a_badly_shaped_crop_region():
    # A malformed/hand-crafted API crop (a thin horizontal strip) must still be
    # center-cropped to the preset's aspect ratio, never stretched into it.
    image = Image.new("RGB", (400, 300))
    params = LithophaneParams(
        width_mm=200,
        height_mm=150,
        orientation="landscape",
        crop={"x": 0.1, "y": 0.4, "width": 0.8, "height": 0.1},
    )
    prepared = prepare_image(image, params)
    assert abs(prepared.width / prepared.height - 200 / 150) < 0.02


def test_prepare_image_uses_inner_area_aspect_when_frame_is_present():
    image = Image.new("RGB", (400, 300))
    params = LithophaneParams(
        width_mm=150, height_mm=100, border_width_mm=4
    )
    prepared = prepare_image(image, params)
    assert abs(prepared.width / prepared.height - 142 / 92) < 0.02


def test_prepare_image_rotates_before_applying_crop():
    image = Image.new("RGB", (400, 200))
    params = LithophaneParams(
        width_mm=150, height_mm=100, rotation_degrees=90
    )
    prepared = prepare_image(image, params)
    # A 90-degree turn changes the source from 2:1 to 1:2 before it is
    # center-cropped to the requested landscape aspect.
    assert prepared.width == 200
    assert prepared.height == 133


def test_arbitrary_rotation_is_cropped_to_fully_covered_rectangle():
    image = Image.new("RGB", (400, 300), "white")
    width, height = inscribed_size(400, 300, 17.5)
    result = rotate_and_inscribe(image, 17.5)
    assert result.size == (round(width), round(height))
    assert min(pixel[0] for pixel in (result.getpixel((0, 0)), result.getpixel((result.width - 1, 0)), result.getpixel((0, result.height - 1)), result.getpixel((result.width - 1, result.height - 1)))) > 200
