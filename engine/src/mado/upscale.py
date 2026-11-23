"""Making a picture bigger: through an AI model, a tile at a time, or without one.

The model (Real-ESRGAN, four times bigger) runs on square tiles that overlap (mado/core/tiles.py
lays them out): each tile's result is resized straight to the size made with Lanczos and faded
into place across the overlap, a band of rows at a time, so the picture four times bigger is
never held whole and no seam shows. The model runs a tile ahead on a thread of its own, so the
graphics card and the processor work at once. Without a model: pixel art grows by repeating its
pixels, a screenshot is resized smoothly and sharpened a touch, and a picture already big enough
is only made smaller. Each way makes exactly the size asked for, from exactly the part of the
picture kept (Pillow's resize with a box, to the fraction of a pixel).
"""

import math
import queue
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageFilter

from mado.core.framing import Box
from mado.core.models import SCALE
from mado.core.tiles import Place, Tile, place, tiles, weights
from mado.directml import Tensor, tensor

type Pixels = npt.NDArray[np.uint8]  # (height, width, 3) RGB
type Runner = Callable[[Tensor], Tensor]  # (1, 3, t, t) from 0 to 1, to (1, 3, 4t, 4t) (a fix's: t)
type Told = Callable[[int, int], None]  # tiles done, of how many


class StoppedError(Exception):
    """Making the picture stopped, as the owner asked."""


@dataclass(frozen=True)
class Tiling:
    run: Runner
    size: int  # the square the model takes
    overlap: int
    scale: int = SCALE  # how many times bigger its answer is each way: a fix's is 1


def through_model(
    pixels: Pixels,
    kept: Box,
    target: tuple[int, int],
    tiling: Tiling,
    *,
    told: Told = lambda _done, _total: None,
    stop: Callable[[], bool] = lambda: False,
) -> Pixels:
    """`kept`, a part of `pixels`, made `target` big by the model a tile at a time. `told`
    hears after each tile; `stop` stops it before the next (StoppedError)."""
    x0, y0 = max(math.floor(kept.x), 0), max(math.floor(kept.y), 0)
    x1 = min(math.ceil(kept.x + kept.width), pixels.shape[1])
    y1 = min(math.ceil(kept.y + kept.height), pixels.shape[0])
    region = pixels[y0:y1, x0:x1]
    origin, span = (kept.x - x0, kept.y - y0), (kept.width, kept.height)
    cut = tiles(region.shape[1], region.shape[0], tiling.size, tiling.overlap)
    places = [place(tile, origin, span, target, tiling.scale) for tile in cut]
    width, height = target
    made = np.empty((height, width, 3), np.uint8)
    band = _Band(width)
    # Where each row of tiles ends: the rows above the next row's first pixel are written out.
    ends = _row_ends(cut, places, height)
    # The model runs on the card one tile ahead while the processor resizes and lays in the
    # last: each waits for the other only when it's ahead.
    results: queue.Queue[tuple[int, Pixels | None] | BaseException] = queue.Queue(maxsize=2)
    halt = threading.Event()

    def run() -> None:
        try:
            for index, (tile, where) in enumerate(zip(cut, places, strict=True)):
                if halt.is_set() or stop():
                    raise StoppedError
                piece = _tile_result(region, tile, tiling) if where is not None else None
                _put(results, (index, piece), halt)
        except BaseException as error:  # handed to the thread laying tiles in, which raises it
            _put(results, error, halt)

    worker = threading.Thread(target=run, name="tiles", daemon=True)
    worker.start()
    try:
        for done in range(1, len(cut) + 1):
            found = results.get()
            if isinstance(found, BaseException):
                raise found
            index, piece = found
            tile, where = cut[index], places[index]
            if where is not None and piece is not None:
                across, down = weights(tile, where, origin, span, target, tiling.overlap)
                band.add(where, _resized(piece, where), np.outer(down, across))
            told(done, len(cut))
            if index in ends:
                band.finish(made, ends[index])
    finally:
        halt.set()
        while worker.is_alive():  # a model waiting on a full queue sees the halt once drained
            with suppress(queue.Empty):
                results.get(timeout=0.05)
        worker.join()
    return made


def _row_ends(cut: list[Tile], places: list[Place | None], height: int) -> dict[int, int]:
    """For the last tile of each row, the row of the picture made that the rows above can be
    written out up to: the next row of tiles' first, or the bottom."""
    rows = sorted({tile.y for tile in cut})
    ends: dict[int, int] = {}
    for number, row in enumerate(rows):
        last = max(index for index, tile in enumerate(cut) if tile.y == row)
        later = [where.v0 for tile, where in zip(cut, places, strict=True)
                 if tile.y > row and where is not None]  # fmt: skip
        ends[last] = min(later, default=height) if number + 1 < len(rows) else height
    return ends


def _put[T](into: queue.Queue[T], item: T, halt: threading.Event) -> None:
    """Puts an item in a queue, waiting for room unless asked to halt."""
    while not halt.is_set():
        try:
            into.put(item, timeout=0.05)
        except queue.Full:
            continue
        return


def by_pixels(pixels: Pixels, kept: Box, target: tuple[int, int]) -> Pixels:
    """Pixel art made `target` big by repeating its pixels: blocky, as it was drawn."""
    return _resize(pixels, kept, target, Image.Resampling.NEAREST)


def smoothly(pixels: Pixels, kept: Box, target: tuple[int, int]) -> Pixels:
    """A screenshot made `target` big without inventing anything: Lanczos, sharpened a touch so
    its words stay crisp."""
    resized = Image.fromarray(_resize(pixels, kept, target, Image.Resampling.LANCZOS))
    return np.asarray(resized.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=1)))


def smaller(pixels: Pixels, kept: Box, target: tuple[int, int]) -> Pixels:
    """A picture already big enough, made exactly `target` big: Lanczos, which keeps it sharp."""
    return _resize(pixels, kept, target, Image.Resampling.LANCZOS)


type Floats = npt.NDArray[np.float32]


def bled(pixels: Pixels, alpha: npt.NDArray[np.uint8]) -> Pixels:
    """A picture's colours carried into its see-through parts from the nearest it shows, so
    growing it doesn't pull in the colour hidden there (often black) as a dark fringe. What
    shows, even faintly, stays as it is. Pushed down halving, then pulled back up."""
    weight: Floats = (alpha.astype(np.float32) / np.float32(255))[..., None]
    start: Floats = (pixels.astype(np.float32) * weight).astype(np.float32)
    levels: list[tuple[Floats, Floats]] = [(start, weight)]
    while max(levels[-1][1].shape[:2]) > 1:  # down to one pixel, however long and narrow
        colour, seen = levels[-1]
        levels.append((_halved(colour), _halved(seen)))
    colour, seen = levels[-1]
    filled = colour / np.maximum(seen, 1e-6)
    for colour, seen in reversed(levels[:-1]):
        height, width = seen.shape[:2]
        above = np.repeat(np.repeat(filled, 2, axis=0), 2, axis=1)[:height, :width]
        filled = colour + (1.0 - np.minimum(seen, 1.0)) * above
    carried = np.clip(filled + 0.5, 0, 255).astype(np.uint8)
    return np.where(alpha[..., None] > 0, pixels, carried)


def _halved(values: Floats) -> Floats:
    """Each two by two the mean of its four (the last row and column held at an odd edge)."""
    height, width = values.shape[:2]
    padded = np.pad(values, ((0, height % 2), (0, width % 2), (0, 0)), mode="edge")
    total = padded[0::2, 0::2] + padded[1::2, 0::2] + padded[0::2, 1::2] + padded[1::2, 1::2]
    return (total / 4).astype(np.float32)


def resize_alpha(alpha: npt.NDArray[np.uint8], kept: Box, target: tuple[int, int]) -> Pixels:
    """A picture's see-through parts, made `target` big from the part kept."""
    image = Image.fromarray(alpha, "L")
    box = (kept.x, kept.y, kept.x + kept.width, kept.y + kept.height)
    return np.asarray(image.resize(target, Image.Resampling.LANCZOS, box=box))


def _resize(pixels: Pixels, kept: Box, target: tuple[int, int], how: Image.Resampling) -> Pixels:
    box = (kept.x, kept.y, kept.x + kept.width, kept.y + kept.height)
    return np.asarray(Image.fromarray(pixels).resize(target, how, box=box))


def _tile_result(region: Pixels, tile: Tile, tiling: Tiling) -> Pixels:
    """One tile through the model: padded to the model's square when the picture is smaller
    than one (mirrored, so its edge carries on), and its result cut back to the tile."""
    part = region[tile.y : tile.y + tile.height, tile.x : tile.x + tile.width]
    size = tiling.size
    pad_y, pad_x = size - part.shape[0], size - part.shape[1]
    if pad_y or pad_x:
        mode = "reflect" if part.shape[0] > pad_y and part.shape[1] > pad_x else "edge"
        part = np.pad(part, ((0, pad_y), (0, pad_x), (0, 0)), mode=mode)
    batch = tensor(part.transpose(2, 0, 1)[None] / 255.0)
    out = tiling.run(batch)[0]
    out = out[:, : tile.height * tiling.scale, : tile.width * tiling.scale]
    return np.clip(out.transpose(1, 2, 0) * 255.0 + 0.5, 0, 255).astype(np.uint8)


def _resized(piece: Pixels, where: Place) -> npt.NDArray[np.float32]:
    """A tile's result resized to the pixels it lands on."""
    size = (where.u1 - where.u0, where.v1 - where.v0)
    image = Image.fromarray(piece).resize(size, Image.Resampling.LANCZOS, box=where.box)
    return np.asarray(image, np.float32)


class _Band:
    """The rows of the picture made that tiles are still landing on, each pixel's colours and
    weights summed as they come, written out once no tile still to come touches them."""

    def __init__(self, width: int) -> None:
        self._width = width
        self._top = 0  # the picture's row the band starts at
        self._sum = np.zeros((0, width, 3), np.float32)
        self._weight = np.zeros((0, width), np.float32)

    def add(
        self, where: Place, colours: npt.NDArray[np.float32], weight: npt.NDArray[np.float32]
    ) -> None:
        self._grow(where.v1 - self._top)
        top, bottom = where.v0 - self._top, where.v1 - self._top
        self._sum[top:bottom, where.u0 : where.u1] += colours * weight[..., None]
        self._weight[top:bottom, where.u0 : where.u1] += weight

    def _grow(self, rows: int) -> None:
        if rows > self._sum.shape[0]:
            more = rows - self._sum.shape[0]
            self._sum = np.concatenate([self._sum, np.zeros((more, self._width, 3), np.float32)])
            self._weight = np.concatenate([self._weight, np.zeros((more, self._width), np.float32)])

    def finish(self, made: Pixels, upto: int) -> None:
        """Writes out the rows above `upto`, which no tile still to come lands on."""
        count = upto - self._top
        if count <= 0:
            return
        if count > self._sum.shape[0]:  # rows no tile landed on: never, as tiles cover it all
            self._grow(count)
        weight = np.maximum(self._weight[:count], 1e-6)[..., None]
        made[self._top : upto] = np.clip(self._sum[:count] / weight + 0.5, 0, 255).astype(np.uint8)
        self._sum = self._sum[count:]
        self._weight = self._weight[count:]
        self._top = upto
