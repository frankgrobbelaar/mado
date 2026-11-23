"""Erasing a part: filling it from what's around it (docs/stack/editing.md).

The erasing models draw in a 512 square, so the hole is cut out of the picture in a square with
half its size again around it on every side (512 pixels at least, so a small hole is drawn at the
picture's own detail), made 512 square, filled, made its size again, and laid back only where the
hole was, softly, with grain like the picture's so a photo's fill doesn't show as smooth. The hole
is grown a little first: what a click picks stops at the thing's edge, and its fringe would stay.
The rest of the picture is never touched. An erase whose fill came out much smoother than what's
round it (a smear: big holes in busy places do that at Fast) says so, so Best can be offered.
"""

import zlib

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado.ai import ERASE_SIZE, Fill
from mado.core.masks import Mask, bounds, detail, feathered, grown, square_around
from mado.extend import grain

type Pixels = npt.NDArray[np.uint8]

_GROW = 0.003  # the hole grown by this much of the picture's shorter side (3 pixels at least)
_MARGIN = 0.5  # around the hole, half its longer side again on every side
_SOFT = 2  # pixels the fill fades in over, past the grown hole
_SMEAR = 0.3  # a fill with less than this of the fine detail round it has smeared
_BUSY = 3.0  # round it, the detail (0 to 255, on the quarter copy) for a smooth fill to show
_POOL = 4  # smears are told on a copy this many times smaller each way


def erased(pixels: Pixels, hole: Mask, fill: Fill) -> tuple[Pixels, bool]:
    """The picture with the hole filled from what's around it, and whether the fill smeared."""
    height, width = pixels.shape[:2]
    by = max(3, round(min(width, height) * _GROW))
    raw = bounds(hole)
    if raw is None:
        return pixels, False
    # The hole grows only `by` past its box, so it's grown there alone, not across the picture.
    reach = by + _SOFT + 2
    left, top = max(raw[0] - reach, 0), max(raw[1] - reach, 0)
    right, bottom = min(raw[2] + reach, width), min(raw[3] + reach, height)
    solid = np.zeros_like(hole)
    solid[top:bottom, left:right] = grown(hole[top:bottom, left:right], by)
    found = bounds(solid)
    if found is None:
        return pixels, False
    x0, y0, x1, y1 = square_around(found, (width, height), least=ERASE_SIZE, margin=_MARGIN)
    crop = pixels[y0:y1, x0:x1]
    inside = solid[y0:y1, x0:x1] >= 128
    side = max(x1 - x0, y1 - y0)
    pad = ((0, side - (y1 - y0)), (0, side - (x1 - x0)))
    square = np.pad(crop, (*pad, (0, 0)), mode="reflect") if any(p[1] for p in pad) else crop
    holed = np.pad(inside, pad) if any(p[1] for p in pad) else inside
    small = np.asarray(
        Image.fromarray(np.ascontiguousarray(square)).resize(
            (ERASE_SIZE, ERASE_SIZE), Image.Resampling.LANCZOS
        )
    )
    small_hole = (
        np.asarray(
            Image.fromarray((holed * 255).astype(np.uint8)).resize(
                (ERASE_SIZE, ERASE_SIZE), Image.Resampling.BILINEAR
            )
        )
        > 0
    )
    drawn = fill(np.ascontiguousarray(small), small_hole)
    back = np.asarray(
        Image.fromarray(drawn).resize((side, side), Image.Resampling.BICUBIC), np.float32
    )[: y1 - y0, : x1 - x0]
    blend = feathered(grown(hole[y0:y1, x0:x1], by + _SOFT), _SOFT).astype(np.float32) / 255.0
    strength = grain(pixels)
    if strength > 0:
        seed = zlib.crc32(f"{x0},{y0},{x1},{y1}".encode())
        noise = np.random.default_rng(seed).normal(0.0, strength, (*back.shape[:2], 1))
        back += noise.astype(np.float32)
    made = crop.astype(np.float32) * (1 - blend[..., None]) + back * blend[..., None]
    result = pixels.copy()
    result[y0:y1, x0:x1] = np.clip(made + 0.5, 0, 255).astype(np.uint8)
    return result, _smeared(result[y0:y1, x0:x1], inside, blend > 0.99)


def _smeared(made: Pixels, inside: npt.NDArray[np.bool_], filled: npt.NDArray[np.bool_]) -> bool:
    """Whether a fill came out much smoother than the picture round it, in a busy place: told on a
    copy a quarter the size, where a photo's grain averages away and what's drawn stays."""
    grey = made.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    height, width = (grey.shape[0] // _POOL) * _POOL, (grey.shape[1] // _POOL) * _POOL
    if height == 0 or width == 0:
        return False
    shape = (height // _POOL, _POOL, width // _POOL, _POOL)
    pooled = grey[:height, :width].reshape(shape).mean(axis=(1, 3)).astype(np.float32)
    hole = inside[:height, :width].reshape(shape).any(axis=(1, 3))
    drawn = filled[:height, :width].reshape(shape).all(axis=(1, 3))
    ring = (grown((hole * 255).astype(np.uint8), 6) >= 128) & ~hole
    around = detail(pooled, ring)
    if around < _BUSY:
        return False
    return detail(pooled, drawn) < around * _SMEAR
