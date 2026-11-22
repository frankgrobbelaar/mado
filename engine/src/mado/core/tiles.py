"""Tiles: how a picture is cut into squares the AI model takes one at a time, and how each
square's result lands in the picture made. Pure.

The model runs on squares of one size (a graphics card runs a fixed size much faster, and its
memory holds one square, not the whole picture), each overlapping its neighbours. Each square's
result, four times bigger, is resized straight to the size made and laid in its place, faded
across the overlap so no seam shows. That way the picture four times bigger is never held whole:
an 8K picture from a big photo needs a fraction of the memory.

Coordinates: the canvas is the picture as shaped (cropped or extended), in its own pixels;
`origin` and `span` are the exact part of it that becomes the size made, `target` pixels.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

_EDGE = 1e-6  # a hair, against rounding, at the size made's edges
_FAINT = 1e-3  # the weight at a square's very edge: never nothing, so every pixel has some


@dataclass(frozen=True)
class Tile:
    x: int  # where it starts on the canvas
    y: int
    width: int  # its part of the canvas: the tile's size, unless the canvas is smaller
    height: int
    inside_left: bool  # an edge with a neighbour, faded across the overlap
    inside_top: bool
    inside_right: bool
    inside_bottom: bool


@dataclass(frozen=True)
class Place:
    """Where a tile's result lands: the size made's pixels [u0, u1) across and [v0, v1) down,
    and the part of the tile's result (in its own pixels, `scale` times the canvas's) they're
    resized from."""

    u0: int
    v0: int
    u1: int
    v1: int
    box: tuple[float, float, float, float]


def starts(length: int, size: int, overlap: int) -> list[int]:
    """Where tiles start along a side of `length` pixels: every `size - overlap` pixels, the last
    pushed back to end at the edge."""
    if length <= size:
        return [0]
    step = size - overlap
    found = list(range(0, length - size, step))
    if found[-1] != length - size:
        found.append(length - size)
    return found


def tiles(width: int, height: int, size: int, overlap: int) -> list[Tile]:
    """The tiles a `width` by `height` canvas is cut into, row by row."""
    across = starts(width, size, overlap)
    down = starts(height, size, overlap)
    tile_width, tile_height = min(size, width), min(size, height)
    return [
        Tile(
            x,
            y,
            tile_width,
            tile_height,
            inside_left=x > 0,
            inside_top=y > 0,
            inside_right=x + tile_width < width,
            inside_bottom=y + tile_height < height,
        )
        for y in down
        for x in across
    ]


def count(width: int, height: int, size: int, overlap: int) -> int:
    """How many tiles a `width` by `height` canvas is cut into."""
    return len(starts(width, size, overlap)) * len(starts(height, size, overlap))


def place(
    tile: Tile,
    origin: tuple[float, float],
    span: tuple[float, float],
    target: tuple[int, int],
    scale: int,
) -> Place | None:
    """Where a tile's result lands in the size made: the pixels whose share of the canvas lies
    within the tile, and the part of its result (`scale` times bigger) they come from. None when
    it gives none (a tile outside the part made)."""
    kx, ky = target[0] / span[0], target[1] / span[1]
    u0, u1 = _range(tile.x, tile.width, origin[0], kx, target[0])
    v0, v1 = _range(tile.y, tile.height, origin[1], ky, target[1])
    if u1 <= u0 or v1 <= v0:
        return None
    left = _within((origin[0] + u0 / kx - tile.x) * scale, tile.width * scale)
    top = _within((origin[1] + v0 / ky - tile.y) * scale, tile.height * scale)
    right = _within((origin[0] + u1 / kx - tile.x) * scale, tile.width * scale)
    bottom = _within((origin[1] + v1 / ky - tile.y) * scale, tile.height * scale)
    return Place(u0, v0, u1, v1, (left, top, right, bottom))


def weights(
    tile: Tile,
    where: Place,
    origin: tuple[float, float],
    span: tuple[float, float],
    target: tuple[int, int],
    overlap: int,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """How much the tile counts at each pixel it lands on, across and down: fully, except within
    `overlap` of an edge it shares with a neighbour, where it fades to almost nothing."""
    kx, ky = target[0] / span[0], target[1] / span[1]
    across = origin[0] + (np.arange(where.u0, where.u1, dtype=np.float64) + 0.5) / kx
    down = origin[1] + (np.arange(where.v0, where.v1, dtype=np.float64) + 0.5) / ky
    return (
        _fade(across, tile.x, tile.width, tile.inside_left, tile.inside_right, overlap),
        _fade(down, tile.y, tile.height, tile.inside_top, tile.inside_bottom, overlap),
    )


def _range(start: int, length: int, origin: float, k: float, total: int) -> tuple[int, int]:
    """The size made's pixels whose share of the canvas lies within [start, start + length)."""
    first = math.ceil((start - origin) * k - _EDGE)
    last = math.floor((start + length - origin) * k + _EDGE)
    return max(first, 0), min(last, total)


def _within(value: float, limit: float) -> float:
    return min(max(value, 0.0), limit)


def _fade(
    at: npt.NDArray[np.float64],
    start: int,
    length: int,
    inside_low: bool,
    inside_high: bool,
    overlap: int,
) -> npt.NDArray[np.float32]:
    weight = np.ones_like(at)
    ramp = max(overlap, 1)
    if inside_low:
        weight = np.minimum(weight, np.clip((at - start) / ramp, _FAINT, 1.0))
    if inside_high:
        weight = np.minimum(weight, np.clip((start + length - at) / ramp, _FAINT, 1.0))
    return weight.astype(np.float32)
