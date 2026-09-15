from PIL import Image

from app.image_processing import crop_to_aspect, prepare_image
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
