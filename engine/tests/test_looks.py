"""Giving a picture its look and touches: its colours through the look's table, see-through parts
and grey pictures kept as they are, the colour profile kept, and the touches the same on a
preview, a part at full detail and the picture saved."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageCms

from mado.core.looks import Look, mado_look
from mado.core.recipe import Styling
from mado.core.touches import Touches
from mado.looks import Placement, seed_of, styled, through
from mado.upscale import StoppedError
from tests.drawn import photo_like, picture


def _look(look_id: str) -> Look:
    found = mado_look(look_id)
    assert found is not None
    return found


def _pixels(image: Image.Image) -> np.ndarray:
    return np.asarray(image).astype(np.int16)


def test_a_look_changes_the_colours_and_none_leaves_every_pixel_as_it_was():
    scene = photo_like((160, 120))

    warm = styled(scene, Styling(_look("warm-film")), seed=1)
    none = styled(scene, Styling(_look("warm-film"), 0.0), seed=1)

    assert warm.size == scene.size
    assert warm.mode == "RGB"
    red, blue = (
        _pixels(warm)[..., 0] - _pixels(scene)[..., 0],
        _pixels(warm)[..., 2] - _pixels(scene)[..., 2],
    )
    assert red.mean() > 0 > blue.mean()  # warmer
    assert np.array_equal(np.asarray(none), np.asarray(scene))


def test_see_through_parts_are_left_exactly_as_they_were():
    scene = picture((96, 72), mode="RGBA")
    alpha = Image.linear_gradient("L").resize(scene.size)
    scene.putalpha(alpha)

    made = styled(scene, Styling(_look("night-neon"), 1.0, Touches(grain=50, dust=60)), seed=3)

    assert made.mode == "RGBA"
    assert np.array_equal(np.asarray(made.getchannel("A")), np.asarray(alpha))
    assert not np.array_equal(np.asarray(made.convert("RGB")), np.asarray(scene.convert("RGB")))


def test_a_grey_picture_stays_grey_unless_its_look_gives_it_colour():
    grey = photo_like((96, 72)).convert("L")

    silver = styled(grey, Styling(_look("silver"), 1.0, Touches(grain=40, vignette=30)), seed=2)
    warm = styled(grey, Styling(_look("warm-film")), seed=2)

    assert silver.mode == "L"
    assert warm.mode == "RGB"


def test_a_picture_of_few_colours_takes_a_look_too():
    palette = picture((64, 48)).convert("P", palette=Image.Palette.ADAPTIVE, colors=16)

    made = through(palette, _look("cool-film").grid)

    assert made.mode == "RGB"
    assert made.size == (64, 48)


def test_the_colour_profile_stays_with_the_picture():
    scene = photo_like((64, 48))
    cms: Any = ImageCms  # Pillow's colour management, partly unknown to Pyright
    profile: bytes = cms.ImageCmsProfile(cms.createProfile("sRGB")).tobytes()
    scene.info["icc_profile"] = profile

    made = styled(scene, Styling(_look("faded"), 0.7, Touches(grain=20)), seed=5)

    assert made.info["icc_profile"] == profile


def test_a_preview_the_size_of_a_screen_shows_the_touches_the_saved_picture_gets():
    scene = photo_like((1200, 800), seed=4)
    styling = Styling(_look("golden-hour"), 0.8, Touches(30, 40, 30, 20, 40, 50))

    full = styled(scene, styling, seed=7)
    small = scene.resize((400, 267), Image.Resampling.LANCZOS)
    preview = styled(small, styling, seed=7, placement=Placement.fitted(small.size, scene.size))

    shrunk = full.resize(small.size, Image.Resampling.LANCZOS)
    assert np.abs(_pixels(shrunk) - _pixels(preview)).mean() < 1.5


def test_a_part_at_full_detail_gets_the_same_touches_as_the_whole():
    scene = photo_like((640, 480), seed=6)
    styling = Styling(_look("warm-film"), 1.0, Touches(grain=60, vignette=50, leak=40, dust=80))
    box = (200, 120, 440, 300)

    whole = styled(scene, styling, seed=9)
    part = styled(
        scene.crop(box), styling, seed=9, placement=Placement(640, 480, left=200, top=120)
    )

    inside = (slice(4, -4), slice(4, -4))  # dust's soft edges look a pixel or two beyond a part
    # The soft touches come from a small grid over each, so they may differ by a level or two.
    assert np.abs(_pixels(whole.crop(box))[inside] - _pixels(part)[inside]).max() <= 2


def test_the_same_picture_gets_the_same_grain_and_another_its_own():
    scene = photo_like((128, 96))
    styling = Styling(_look("original"), 1.0, Touches(grain=80, dust=40))

    first = styled(scene, styling, seed=seed_of(Path("D:/Pictures/Harbour at dusk.jpg")))
    again = styled(scene, styling, seed=seed_of(Path("d:/pictures/harbour at dusk.JPG")))
    other = styled(scene, styling, seed=seed_of(Path("D:/Pictures/Little sail.jpg")))

    assert np.array_equal(np.asarray(first), np.asarray(again))
    assert not np.array_equal(np.asarray(first), np.asarray(other))


def test_touches_stop_between_bands_when_asked():
    scene = photo_like((256, 192))

    with pytest.raises(StoppedError):
        styled(scene, Styling(_look("original"), 1.0, Touches(grain=10)), seed=1, stop=lambda: True)
