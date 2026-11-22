"""Making a picture bigger: through a model a tile at a time (the shipped Fast model on the
processor, on tiny made-up pictures, or a stand-in), and without one."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mado.core.framing import Box
from mado.core.models import FAST
from mado.directml import Sessions, Tensor
from mado.upscale import (
    StoppedError,
    Tiling,
    bled,
    by_pixels,
    resize_alpha,
    smaller,
    smoothly,
    through_model,
)
from tests.drawn import photo_like, picture, sprite

ASSETS = Path(__file__).parents[1] / "src" / "mado" / "assets"


def repeated(batch: Tensor) -> Tensor:
    """A stand-in for the model: each pixel four times, each way."""
    return np.repeat(np.repeat(batch, 4, axis=2), 4, axis=3)


def _whole(pixels: np.ndarray, kept: Box, target: tuple[int, int]) -> np.ndarray:
    """What the stand-in makes in one go, without tiles: the picture four times bigger by
    repeating, then resized to the target, as a reference."""
    big = Image.fromarray(np.repeat(np.repeat(pixels, 4, axis=0), 4, axis=1))
    box = (kept.x * 4, kept.y * 4, (kept.x + kept.width) * 4, (kept.y + kept.height) * 4)
    return np.asarray(big.resize(target, Image.Resampling.LANCZOS, box=box)).astype(np.int16)


def test_tiles_meet_without_a_seam_on_a_flat_colour():
    pixels = np.full((300, 500, 3), (90, 140, 200), np.uint8)
    made = through_model(pixels, Box(0, 0, 500, 300), (1500, 900), Tiling(repeated, 128, 16))

    assert made.shape == (900, 1500, 3)
    assert np.abs(made.astype(np.int16) - (90, 140, 200)).max() <= 1


def test_tiles_land_where_one_whole_resize_puts_them():
    pixels = np.asarray(photo_like((230, 170)))
    kept = Box(10.5, 7.25, 200.0, 150.0)
    target = (640, 480)

    made = through_model(pixels, kept, target, Tiling(repeated, 64, 16)).astype(np.int16)

    reference = _whole(pixels, kept, target)
    inner = (slice(4, -4), slice(4, -4))  # the outermost pixels see the picture's edge
    assert np.abs(made - reference)[inner].mean() < 1.5
    assert np.percentile(np.abs(made - reference)[inner], 99) <= 8


def test_the_shipped_fast_model_runs_on_the_processor_on_a_tiny_picture():
    session = Sessions().get(ASSETS / FAST.file, 32, "processor")
    tiling = Tiling(lambda batch: session.run({"input": batch})[0], 32, 8)
    pixels = np.asarray(picture((64, 48)))
    told: list[tuple[int, int]] = []

    made = through_model(
        pixels, Box(0, 0, 64, 48), (256, 192), tiling, told=lambda d, t: told.append((d, t))
    )

    assert made.shape == (192, 256, 3)
    plain = np.asarray(Image.fromarray(pixels).resize((256, 192), Image.Resampling.LANCZOS))
    assert np.abs(made.astype(np.int16) - plain).mean() < 12  # the same picture, sharper
    assert len(told) == 6
    assert told[-1] == (6, 6)


def test_a_picture_smaller_than_a_tile_is_padded_for_the_model():
    pixels = np.asarray(picture((40, 30)))

    made = through_model(pixels, Box(0, 0, 40, 30), (160, 120), Tiling(repeated, 64, 16))

    plain = np.repeat(np.repeat(pixels, 4, axis=0), 4, axis=1)
    assert np.abs(made.astype(np.int16) - plain).mean() < 2


def test_stopping_stops_before_the_next_tile():
    pixels = np.zeros((200, 200, 3), np.uint8)

    with pytest.raises(StoppedError):
        through_model(pixels, Box(0, 0, 200, 200), (800, 800), Tiling(repeated, 64, 16),
                      stop=lambda: True)  # fmt: skip


def test_pixel_art_stays_blocky_and_screenshots_and_big_pictures_are_resized():
    art = np.asarray(sprite(block=1, cells=16))
    blocky = by_pixels(art, Box(0, 0, 16, 16), (64, 64))

    assert np.array_equal(blocky[::4, ::4], art)
    assert len(np.unique(blocky.reshape(-1, 3), axis=0)) == len(
        np.unique(art.reshape(-1, 3), axis=0)
    )
    assert smoothly(np.asarray(picture()), Box(0, 0, 64, 48), (128, 96)).shape == (96, 128, 3)
    assert smaller(np.asarray(picture((400, 300))), Box(0, 0, 400, 300), (200, 150)).shape == (
        150,
        200,
        3,
    )


def test_colours_are_carried_into_see_through_parts_so_edges_dont_darken():
    pixels = np.zeros((40, 40, 3), np.uint8)  # hidden black around the shape
    pixels[10:30, 10:30] = (220, 40, 40)
    alpha = np.zeros((40, 40), np.uint8)
    alpha[10:30, 10:30] = 255
    alpha[9, 10:30] = 128  # a soft edge keeps its own colour
    pixels[9, 10:30] = (10, 200, 10)

    filled = bled(pixels, alpha)

    assert np.array_equal(filled[10:30, 10:30], pixels[10:30, 10:30])  # seen: as it was
    assert np.array_equal(filled[9, 10:30], pixels[9, 10:30])
    assert np.abs(filled[20, 0].astype(int) - (220, 40, 40)).max() <= 40  # hidden: carried
    assert filled[39, 39].max() > 0
    grown = smoothly(filled, Box(0, 0, 40, 40), (160, 160)).astype(int)
    edge = grown[80, 38:42]  # where the shape's left edge lands, a little either side
    assert (edge[:, 0] > 150).all()


def test_see_through_parts_are_resized_from_the_part_kept():
    alpha = np.zeros((40, 40), np.uint8)
    alpha[:, 20:] = 255

    made = resize_alpha(alpha, Box(10, 0, 20, 40), (80, 160))

    assert made.shape == (160, 80)
    assert made[:, :30].max() < 40
    assert made[:, 50:].min() > 215


def test_colours_reach_every_hidden_part_of_a_long_narrow_picture():
    pixels = np.zeros((20, 600, 3), np.uint8)
    pixels[:, :40] = (30, 160, 220)
    alpha = np.zeros((20, 600), np.uint8)
    alpha[:, :40] = 255

    filled = bled(pixels, alpha)

    assert np.abs(filled[:, -1].astype(int) - (30, 160, 220)).max() <= 40  # not left black
