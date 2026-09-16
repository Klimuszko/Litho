import pytest

from app.models import LithophaneParams


@pytest.mark.parametrize(
    ("nozzle", "profile", "pitch", "resolution"),
    [
        (0.2, "economic", 0.20, 1000),
        (0.2, "optimal", 0.125, 1600),
        (0.2, "maximum", 0.10, 2000),
        (0.4, "economic", 0.40, 500),
        (0.4, "optimal", 0.25, 800),
        (0.4, "maximum", 0.20, 1000),
    ],
)
def test_physical_quality_profiles(nozzle, profile, pitch, resolution):
    params = LithophaneParams(
        width_mm=200,
        height_mm=150,
        orientation="landscape",
        nozzle_diameter_mm=nozzle,
        quality_profile=profile,
    )
    assert params.sample_pitch_mm == pitch
    assert params.effective_resolution == resolution


def test_legacy_resolution_override_remains_supported():
    params = LithophaneParams(resolution=48)
    assert params.effective_resolution == 48
