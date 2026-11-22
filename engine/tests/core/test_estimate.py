"""How long making a picture takes, and how big it comes out."""

import pytest

from mado.core.estimate import blended, seconds_for, speed
from mado.core.quality import about_bytes, colour_words, phrase, suited


def test_a_speed_measured_here_wins_over_the_guess():
    assert speed("realesr-general-x4v3", "card", {}) == pytest.approx(0.59)
    measured = {"realesr-general-x4v3@card": 0.3}
    assert speed("realesr-general-x4v3", "card", measured) == 0.3


def test_time_grows_with_the_tiles_and_the_pixels_made():
    few = seconds_for("realesr-general-x4v3", "card", 12, 512, 33_177_600, {})
    many = seconds_for("realesr-general-x4v3", "card", 45, 512, 33_177_600, {})
    none = seconds_for(None, "card", 0, 0, 8_294_400, {})

    assert 3 < few < many
    assert none == pytest.approx(0.5 + 8.2944 * 0.06)


def test_a_speed_kept_moves_a_little_toward_each_one_measured():
    assert blended(None, 1.0) == 1.0
    assert blended(1.0, 2.0) == pytest.approx(1.3)


def test_photos_mado_cant_write_as_they_were_are_jpeg_suited_to_the_screen_the_rest_png():
    assert suited("tv", "photo", "HEIC").format == "JPEG"
    assert suited("tv", "photo", "HEIC").quality == 95
    assert suited("phone", "photo", "HEIC").quality == 90
    assert suited("tv", "photo", "HEIC").fits == "What every TV shows."
    assert suited("laptop", "pixels", "GIF").format == "PNG"


def test_the_format_stays_as_it_was_when_mado_writes_it():
    assert suited("tv", "photo", "PNG").format == "PNG"
    assert suited("tv", "photo", "PNG").quality is None
    assert suited("tv", "photo", "PNG").fits == "Kept exactly, every pixel as it was made."
    assert suited("phone", "drawing", "JPEG").format == "JPEG"
    assert suited("phone", "drawing", "JPEG").quality == 90
    assert suited("tv", "photo", "WebP").format == "WebP"
    assert suited("tv", "photo", "WebP").quality == 90
    assert "TVs" in suited("tv", "photo", "WebP").fits
    assert suited("print", "photo", "AVIF").format == "AVIF"
    assert "print shops" in suited("print", "photo", "AVIF").fits


def test_a_picture_with_see_through_parts_is_never_jpeg():
    assert suited("tv", "photo", "HEIC", alpha=True).format == "PNG"
    assert suited("tv", "photo", "TIFF", alpha=True).fits == (
        "Kept exactly, its see-through parts too."
    )
    assert suited("tv", "photo", "WebP", alpha=True).format == "WebP"


def test_about_how_big_a_tv_8k_jpeg_comes_out():
    assert about_bytes("JPEG", 95, "photo", 7680 * 4320) == pytest.approx(18e6, rel=0.1)
    assert about_bytes("PNG", None, "pixels", 1000) == 50


def test_colours_keep_the_pictures_own_profile_unless_it_is_srgb_or_turned():
    assert colour_words("Display P3", keep=True) == "Display P3"
    assert colour_words("Display P3", keep=False) == "sRGB"
    assert colour_words("sRGB IEC61966-2.1", keep=True) == "sRGB"
    assert colour_words(None, keep=True) == "sRGB"


def test_what_a_picture_is_made_for_reads_at_the_start_of_a_sentence():
    assert phrase("tv", "TV 8K") == "A TV"
    assert phrase("print", "A4") == "An A4 print"
    assert phrase("print", "10 × 15 cm") == "A 10 × 15 cm print"
