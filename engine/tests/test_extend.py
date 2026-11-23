"""Extending a picture's edges: the picture stays exactly as it was, and the new edges are drawn
by the model (a stand-in here: LaMa itself is a 209 MB download)."""

from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image, ImageDraw

from mado.ai import Ai
from mado.core.framing import Box, frame
from mado.core.recipe import Recipe, Sizing
from mado.core.sizes import resolve
from mado.directml import Tensor
from mado.extend import Filler, extended
from mado.making import Picture, make, planned, see
from mado.upscale import Tiling, smaller, through_model
from tests.drawn import picture
from tests.test_upscale import repeated


def grey_fill(image: Tensor, mask: Tensor) -> Tensor:
    """A stand-in for LaMa: what's missing drawn mid-grey, what's there as it was."""
    assert image.shape == (1, 3, 512, 512)
    assert mask.shape == (1, 1, 512, 512)
    return np.where(mask > 0, np.float32(0.5), image).astype(np.float32)


def test_the_picture_stays_as_it_was_and_the_new_sides_are_drawn():
    pixels = np.asarray(picture((480, 360)))
    made = frame(480, 360, 1920, 1080, "extend")
    told: list[int] = []

    canvas, exact, at = extended(pixels, made.canvas, grey_fill, told=lambda d, _t: told.append(d))

    assert canvas.shape == (360, 640, 3)
    assert at == (80, 0)
    assert np.array_equal(canvas[:, 80:560], pixels)
    assert abs(int(canvas[180, 5, 0]) - 128) <= 8  # drawn, far from the join
    assert abs(int(canvas[180, 635, 0]) - 128) <= 8
    assert exact.width == made.canvas.width
    assert told[-1] == len(told)


def test_the_join_takes_the_pictures_colours_so_it_doesnt_show():
    pixels = np.full((360, 480, 3), (200, 120, 60), np.uint8)
    made = frame(480, 360, 1920, 1080, "extend")

    canvas, _exact, _at = extended(pixels, made.canvas, grey_fill)

    beside = canvas[180, 79].astype(int)  # just left of the picture
    assert np.abs(beside - (200, 120, 60)).max() <= 6


def test_extending_a_tall_size_draws_the_top_and_bottom():
    pixels = np.asarray(picture((120, 90)))
    made = frame(120, 90, 1290, 2796, "extend")

    canvas, _exact, at = extended(pixels, made.canvas, grey_fill)

    assert canvas.shape[1] == 120
    assert canvas.shape[0] > 90
    assert at[0] == 0
    assert np.array_equal(canvas[at[1] : at[1] + 90], pixels)


def _inside(canvas: np.ndarray, exact: Box) -> bool:
    height, width = canvas.shape[:2]
    return (
        exact.x >= 0
        and exact.y >= 0
        and exact.x + exact.width <= width + 1e-9
        and exact.y + exact.height <= height + 1e-9
    )


def test_a_canvas_of_fractional_pixels_holds_all_of_its_exact_part():
    # 103 by 75 at 16:9 is 133.3 pixels across, starting 15.17 before the picture.
    pixels = np.asarray(picture((103, 75)))
    made = frame(103, 75, 1920, 1080, "extend")

    canvas, exact, at = extended(pixels, made.canvas, grey_fill)

    assert _inside(canvas, exact)
    assert exact.width == made.canvas.width
    assert np.array_equal(canvas[at[1] : at[1] + 75, at[0] : at[0] + 103], pixels)
    # Where the picture is, the exact part says too: a pixel's worth either way at most.
    assert abs((at[0] - exact.x) - (-made.canvas.x)) < 1e-9


def test_a_fractional_canvas_resizes_and_makes_to_its_last_column():
    pixels = np.asarray(picture((103, 75)))
    made = frame(103, 75, 1920, 1080, "extend")
    canvas, exact, _at = extended(pixels, made.canvas, grey_fill)

    shrunk = smaller(canvas, exact, (1920, 1080))  # Pillow refuses a box past the picture
    through = through_model(canvas, exact, (1920, 1080), Tiling(repeated, 64, 16))

    assert shrunk.shape == (1080, 1920, 3)
    assert through[:, -1].max() > 0  # not left black
    assert through[-1, :].max() > 0


def test_big_pictures_extended_to_wide_sizes_hold_their_exact_part():
    for target in ((3840, 2160), (7680, 4320), (3440, 1440)):
        made = frame(4000, 3000, *target, "extend")
        pixels = np.zeros((3000, 4000, 3), np.uint8)

        canvas, exact, _at = extended(pixels, made.canvas, grey_fill)

        assert _inside(canvas, exact), target


class _Standing:
    """A stand-in for Mado's models: LaMa drawing mid-grey, and the model repeating pixels."""

    def filler(self, _timer: object = None) -> Filler:
        return grey_fill

    def tiling(self, _model: object, _timer: object = None) -> Tiling:
        return Tiling(repeated, 64, 16)


def test_a_see_through_pictures_new_edges_are_as_see_through_as_its_edge_beside_them():
    sticker = Image.new("RGBA", (120, 80), (0, 0, 0, 0))  # nothing round a disc
    ImageDraw.Draw(sticker).ellipse([30, 10, 90, 70], fill=(220, 40, 40, 255))
    seen = see(sticker, Picture(Path("Sticker.png"), "picture", "PNG", None))
    made = planned(
        Recipe(Sizing(size=resolve("other-512x320", []), shape="extend")),
        seen,
        {"photo": "fast", "drawing": "fast"},
    )

    result = make(
        sticker,
        made,
        cast("Ai", _Standing()),
        report=lambda _stage, _within: None,
        stop=lambda: False,
    ).image

    assert result.mode == "RGBA"
    alpha = np.asarray(result.getchannel("A"))
    assert alpha[:, :8].max() == 0  # the new sides: see-through, as the picture's sides are
    assert alpha[:, -8:].max() == 0
    assert alpha[160, 256] == 255  # the disc
