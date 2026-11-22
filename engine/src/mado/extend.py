"""Extending a picture's edges with LaMa, the model that draws what's missing in a square from
what's around it (Apache-2.0; a download, fetched the first time it's asked for).

LaMa sees 512 pixels square, and it draws well only when it sees the whole scene: so the canvas
(the picture in its middle, the size's shape) is drawn on a copy whose short side is 512, in
squares that span all of it (mado/core/outpaint.py places them), each holding a band of new edge
and the picture beside it. The drawing is then made the canvas's size and laid in only where
the canvas was empty, its colours matched to the picture's along the join and fading in from
the picture's own edge, with grain like the picture's, so the join doesn't show. The picture
itself never changes.

What's drawn is soft: LaMa carries skies, walls, water and grass on well, and repeats a pattern
it sees; people, faces and busy detail at an edge come out smeared, and Mado says so before
it's chosen.
"""

from collections.abc import Callable
from math import ceil
from typing import Literal

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageFilter

from mado.core.framing import Box
from mado.core.outpaint import squares
from mado.directml import Tensor, tensor
from mado.upscale import Pixels, StoppedError

SIZE = 512  # the square LaMa takes
type Filler = Callable[[Tensor, Tensor], Tensor]  # picture (1, 3, 512, 512) 0 to 1, and mask
type Told = Callable[[int, int], None]
_GRAIN_SAMPLE = 512  # pixels a side of the picture's middle its grain is measured on


def extended(
    pixels: Pixels,
    canvas: Box,
    fill: Filler,
    *,
    told: Told = lambda _done, _total: None,
    stop: Callable[[], bool] = lambda: False,
) -> tuple[Pixels, Box, tuple[int, int]]:
    """The picture on a canvas of `canvas` (its box, in the picture's pixels: it starts before
    the picture), the rest drawn by `fill`; where the canvas's exact part is on it; and where
    the picture is on it."""
    height, width = pixels.shape[:2]
    left, top, canvas_width, canvas_height = canvas_around(canvas, width, height)
    exact = Box(canvas.x + left, canvas.y + top, canvas.width, canvas.height)
    made = np.zeros((canvas_height, canvas_width, 3), np.uint8)
    made[top : top + height, left : left + width] = pixels
    if (canvas_width, canvas_height) == (width, height):
        return made, exact, (left, top)
    small, scale = _drawn_small(
        pixels, (canvas_width, canvas_height), (left, top), fill, told, stop
    )
    reach = max(4, round(min(canvas_width, canvas_height) * 0.012))
    strength = _grain(pixels)
    noise = np.random.default_rng(7)
    for side, (x0, y0, x1, y1) in _strips(
        (canvas_width, canvas_height), (left, top, width, height)
    ):
        box = (x0 * scale[0], y0 * scale[1], x1 * scale[0], y1 * scale[1])
        drawn = np.asarray(
            Image.fromarray(small).resize((x1 - x0, y1 - y0), Image.Resampling.BICUBIC, box=box),
            np.float32,
        )
        joined = _joined(drawn, pixels, side, reach)
        if strength > 0:
            joined += noise.normal(0.0, strength, (*joined.shape[:2], 1)).astype(np.float32)
        made[y0:y1, x0:x1] = np.clip(joined + 0.5, 0, 255).astype(np.uint8)
    return made, exact, (left, top)


def canvas_around(canvas: Box, width: int, height: int) -> tuple[int, int, int, int]:
    """Where a `width` by `height` picture goes on the whole pixels holding all of `canvas`
    (its left and top), and their width and height: a canvas's sides fall between pixels, so
    the pixels reach past them, never short."""
    left = max(ceil(-canvas.x - _EPSILON), 0)
    top = max(ceil(-canvas.y - _EPSILON), 0)
    canvas_width = max(ceil(left + canvas.x + canvas.width - _EPSILON), left + width)
    canvas_height = max(ceil(top + canvas.y + canvas.height - _EPSILON), top + height)
    return left, top, canvas_width, canvas_height


_EPSILON = 1e-6  # a side this near a pixel's edge is on it


type Side = Literal["left", "right", "top", "bottom"]


def _joined(
    drawn: npt.NDArray[np.float32], pixels: Pixels, side: Side, reach: int
) -> npt.NDArray[np.float32]:
    """A new edge, drawn, joined to the picture: its colours matched to the picture's all along
    the join (the match fading out over a few reaches), and fading in from the picture's own
    edge, smoothed, over the last `reach` pixels."""
    # Turned so the picture is just past the strip's last column, the join running down.
    along, edge = _turned(drawn, side), _turned(pixels, _OPPOSITE[side])[:, ::-1][:, :reach]
    depth = along.shape[1]
    picture_line = _smoothed(edge.mean(axis=1, dtype=np.float32), reach)
    drawn_line = _smoothed(along[:, -min(reach, depth) :].mean(axis=1), reach)
    away = np.arange(depth, 0, -1, dtype=np.float32)  # pixels from the picture
    match = np.clip(1 - away / (8 * reach), 0, 1)[None, :, None]
    fade = np.clip(1 - away / reach, 0, 1)[None, :, None]
    corrected = along + (picture_line - drawn_line)[:, None, :] * match
    joined = picture_line[:, None, :] * fade + corrected * (1 - fade)
    return _turned_back(joined.astype(np.float32), side)


_OPPOSITE: dict[Side, Side] = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}


def _turned[T: np.generic](values: npt.NDArray[T], side: Side) -> npt.NDArray[T]:
    """A strip turned so the picture it joins is past its last column, the join running down:
    a strip on the picture's left as it is, the others flipped or turned to match."""
    match side:
        case "left":
            return values
        case "right":
            return values[:, ::-1]
        case "top":
            return values.transpose(1, 0, 2)
        case "bottom":
            return values[::-1].transpose(1, 0, 2)


def _turned_back(values: npt.NDArray[np.float32], side: Side) -> npt.NDArray[np.float32]:
    match side:
        case "left":
            return values
        case "right":
            return values[:, ::-1]
        case "top":
            return values.transpose(1, 0, 2)
        case "bottom":
            return values.transpose(1, 0, 2)[::-1]


def _smoothed(line: npt.NDArray[np.float32], reach: int) -> npt.NDArray[np.float32]:
    """A line of colours (one a row along the join) evened out over `reach` rows either way."""
    size = 2 * reach + 1
    padded = np.pad(line, ((reach, reach), (0, 0)), mode="edge")
    sums = np.zeros((padded.shape[0] + 1, 3), np.float64)
    sums[1:] = np.cumsum(padded, axis=0)
    return ((sums[size:] - sums[:-size]) / size).astype(np.float32)


def _strips(
    size: tuple[int, int], picture: tuple[int, int, int, int]
) -> list[tuple[Side, tuple[int, int, int, int]]]:
    """The canvas outside the picture, as rectangles (left, top, right, bottom) by the side of
    the picture they're on: its new sides, or its new top and bottom."""
    width, height = size
    left, top, picture_width, picture_height = picture
    right, bottom = left + picture_width, top + picture_height
    found: list[tuple[Side, tuple[int, int, int, int]]] = []
    if left > 0:
        found.append(("left", (0, 0, left, height)))
    if right < width:
        found.append(("right", (right, 0, width, height)))
    if top > 0:
        found.append(("top", (left, 0, right, top)))
    if bottom < height:
        found.append(("bottom", (left, bottom, right, height)))
    return found


def squares_needed(size: tuple[int, int], picture: tuple[int, int, int, int]) -> int:
    """How many squares LaMa draws to extend a canvas of `size`, the picture at `picture` (its
    left, top, right and bottom), on the copy it draws on."""
    width, height = size
    scale = SIZE / min(width, height)
    small = (max(SIZE, round(width * scale)), max(SIZE, round(height * scale)))
    sx, sy = small[0] / width, small[1] / height
    left, top, right, bottom = picture
    placed = (round(left * sx), round(top * sy), round(right * sx), round(bottom * sy))
    return len(squares(small[0], small[1], placed))


def _drawn_small(
    pixels: Pixels,
    size: tuple[int, int],
    at: tuple[int, int],
    fill: Filler,
    told: Told,
    stop: Callable[[], bool],
) -> tuple[Pixels, tuple[float, float]]:
    """The canvas drawn by LaMa on a copy whose short side is 512, and how many of its pixels
    there are to one of the canvas's, across and down."""
    width, height = size
    scale = SIZE / min(width, height)
    small_size = (max(SIZE, round(width * scale)), max(SIZE, round(height * scale)))
    sx, sy = small_size[0] / width, small_size[1] / height
    picture = Image.fromarray(pixels)
    left, top = round(at[0] * sx), round(at[1] * sy)
    inside = (
        min(max(1, round(pixels.shape[1] * sx)), small_size[0] - left),
        min(max(1, round(pixels.shape[0] * sy)), small_size[1] - top),
    )
    small = np.zeros((small_size[1], small_size[0], 3), np.uint8)
    small[top : top + inside[1], left : left + inside[0]] = np.asarray(
        picture.resize(inside, Image.Resampling.LANCZOS)
    )
    known = np.zeros(small.shape[:2], bool)
    known[top : top + inside[1], left : left + inside[0]] = True
    found = squares(small_size[0], small_size[1], (left, top, left + inside[0], top + inside[1]))
    for done, square in enumerate(found, start=1):
        if stop():
            raise StoppedError
        window = (slice(square.y, square.y + square.size), slice(square.x, square.x + square.size))
        missing = ~known[window]
        if missing.any():
            part = _square_drawn(small[window], missing, fill)
            small[window][missing] = part[missing]
            known[window] = True
        told(done, len(found))
    return small, (sx, sy)


def _square_drawn(part: Pixels, missing: npt.NDArray[np.bool_], fill: Filler) -> Pixels:
    """A square drawn whole by LaMa at 512 (the square is that size, or made it)."""
    side = part.shape[0]
    image = Image.fromarray(part)
    holes_image = Image.fromarray(missing.astype(np.uint8) * 255)
    if side != SIZE:
        image = image.resize((SIZE, SIZE), Image.Resampling.BICUBIC)
        holes_image = holes_image.resize((SIZE, SIZE), Image.Resampling.BOX)
    holes = (np.asarray(holes_image) > 0).astype(np.float32)  # any of it missing: draw it
    seen = np.asarray(image, np.float32) * (1 - holes)[..., None]  # missing shows as nothing
    out = fill(tensor(seen.transpose(2, 0, 1)[None] / 255.0), tensor(holes[None, None]))[0]
    drawn = Image.fromarray(np.clip(out.transpose(1, 2, 0) * 255.0 + 0.5, 0, 255).astype(np.uint8))
    if side != SIZE:
        drawn = drawn.resize((side, side), Image.Resampling.BICUBIC)
    return np.asarray(drawn)


def _grain(pixels: Pixels) -> float:
    """How grainy the picture is: the spread of its finest detail where it's flat, so what's
    drawn (smooth) can be given the same and sit beside what was taken without showing. Nothing
    for a drawing, or a picture without grain."""
    height, width = pixels.shape[:2]
    side = min(_GRAIN_SAMPLE, height, width)
    y0, x0 = (height - side) // 2, (width - side) // 2
    sample = Image.fromarray(pixels[y0 : y0 + side, x0 : x0 + side]).convert("L")
    fine = np.asarray(sample, np.float32) - np.asarray(
        sample.filter(ImageFilter.BoxBlur(1)), np.float32
    )
    detail = np.abs(np.asarray(sample.filter(ImageFilter.FIND_EDGES), np.float32))
    flat = detail <= np.percentile(detail, 50)
    strength = float(fine[flat].std()) if flat.any() else 0.0
    return strength if strength >= 0.5 else 0.0
