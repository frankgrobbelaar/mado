"""Extending a picture's edges: where the squares go that LaMa, the model that draws more of a
picture, is given one at a time. Pure.

LaMa fills what's missing in a square from what's around it. To extend a picture, each square
holds a band of the new edge (a quarter of it) and the picture beside it (the rest), so what's
drawn follows on from what's there; a wider edge is drawn in steps outward, each going on from
the last. Squares down the edge overlap, so the drawing runs on between them.
"""

from dataclasses import dataclass

from mado.core.tiles import starts

MOST = 1024  # pixels a square covers at most: LaMa works at 512, so this halves the canvas


@dataclass(frozen=True)
class Square:
    x: int
    y: int
    size: int


def squares(width: int, height: int, picture: tuple[int, int, int, int]) -> list[Square]:
    """The squares that extend a `width` by `height` canvas, the picture at `picture` (its left,
    top, right and bottom edges) and the rest to draw: band by band outward from the picture,
    and along each band in order."""
    left, top, right, bottom = picture
    across = left > 0 or right < width
    side = min(width, height, MOST)
    if across:
        return _bands(width, height, side, left, right, columns=True)
    if top > 0 or bottom < height:
        return _bands(width, height, side, top, bottom, columns=False)
    return []


def _bands(
    width: int, height: int, side: int, low: int, high: int, *, columns: bool
) -> list[Square]:
    """Squares for the bands before `low` and after `high` along the extended axis (columns:
    across), each square reaching back over what's known by three quarters of its size."""
    length = width if columns else height
    along = starts(height if columns else width, side, side // 4)
    step = max(side // 4, 1)  # a quarter of a square new, three quarters what's known
    found: list[Square] = []
    frontier = low
    while frontier > 0:  # the edge before the picture
        band = min(frontier, step)
        start = min(frontier - band, max(length - side, 0))
        found += [_square(start, other, side, columns) for other in along]
        frontier -= band
    frontier = high
    while frontier < length:  # and after it
        band = min(length - frontier, step)
        start = max(frontier + band - side, 0)
        found += [_square(start, other, side, columns) for other in along]
        frontier += band
    return found


def _square(at: int, other: int, side: int, columns: bool) -> Square:
    return Square(at, other, side) if columns else Square(other, at, side)
