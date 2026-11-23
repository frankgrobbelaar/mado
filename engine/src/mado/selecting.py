"""Picking a part of a picture with a click: SAM 2.1 (tiny) reads the picture once, the whole of it
squeezed to 1024 × 1024 however big it is, then answers each part's clicks with three masks at
256 × 256 in a few hundredths of a second, on the processor (docs/stack/editing.md). The answers
are kept smallest first; Mado shows one first (mado/core/edits.py) and the owner can step through
the others. A mask is made the picture's size smoothly from the model's own numbers; the outline
the window draws is worked out on a copy 1024 across, so a click never waits for a big picture.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado.ai import Array, Selector, imagenet
from mado.core.edits import CHOICES, Part, first_choice
from mado.core.masks import Floats, Mask, outline, path

READ = 1024  # the square SAM reads a picture at
GRID = 1024  # the outline is worked out on a copy this big on its long side
_GREY = (128, 128, 128)  # what see-through parts are read as
_NEAR = -6.0  # SAM's numbers below this are surely outside a part (its mask under 0.3%)

type Read = tuple[Array, Array, Array]


@dataclass(frozen=True)
class Answers:
    """A part's three answers, smallest first: SAM's numbers for each (above 0 is in it), how
    sure it is of each, and how much of the picture each covers."""

    logits: Floats  # 3 × 256 × 256
    scores: tuple[float, ...]
    areas: tuple[float, ...]

    def choice(self, asked: int | None) -> int:
        """The answer shown: the one asked for, or the one Mado picks."""
        if asked is not None:
            return min(max(asked, 0), CHOICES - 1)
        return first_choice(self.scores, self.areas)


def readable(image: Image.Image) -> Floats:
    """A picture as SAM reads it: its colours, see-through parts on grey, squeezed to 1024
    square."""
    return imagenet(flat(image), READ)


def flat(image: Image.Image) -> Image.Image:
    """A picture's colours as RGB, see-through parts laid on grey."""
    if image.mode == "RGB":
        return image
    if "A" in image.getbands() or "transparency" in image.info:
        rgba = image.convert("RGBA")
        ground = Image.new("RGB", rgba.size, _GREY)
        ground.paste(rgba, mask=rgba.getchannel("A"))
        return ground
    return image.convert("RGB")


def answers(selector: Selector, read: Read, part: Part) -> Answers:
    """A part's three answers to its clicks, smallest first."""
    points = np.array([[[[click.x * READ, click.y * READ] for click in part.clicks]]], np.float32)
    labels = np.array([[[1 if click.keep else 0 for click in part.clicks]]], np.int64)
    scores, logits = selector.pick(read, points, labels)
    covered = (logits > 0).mean(axis=(1, 2))
    order = np.argsort(covered, kind="stable")
    return Answers(
        logits=np.ascontiguousarray(logits[order], dtype=np.float32),
        scores=tuple(float(scores[at]) for at in order),
        areas=tuple(float(covered[at]) for at in order),
    )


def soft(logits: Floats, size: tuple[int, int]) -> Floats:
    """One answer made `size` big, smoothly, as 0 to 1 (half is its edge)."""
    grown = np.asarray(
        Image.fromarray(np.ascontiguousarray(logits, np.float32), "F").resize(
            size, Image.Resampling.BILINEAR
        ),
        np.float32,
    )
    return (1.0 / (1.0 + np.exp(-np.clip(grown, -30, 30)))).astype(np.float32)


def mask_at(logits: Floats, size: tuple[int, int]) -> Mask:
    """One answer at the picture's size as a mask, its edge where SAM put it: made only over the
    part of the picture the answer reaches (a small part of a big picture takes a moment)."""
    width, height = size
    found = np.zeros((height, width), np.uint8)
    near = logits > _NEAR
    rows, columns = np.flatnonzero(near.any(axis=1)), np.flatnonzero(near.any(axis=0))
    if rows.size == 0:
        return found
    cells_y, cells_x = logits.shape
    top, bottom = max(int(rows[0]) - 2, 0), min(int(rows[-1]) + 3, cells_y)
    left, right = max(int(columns[0]) - 2, 0), min(int(columns[-1]) + 3, cells_x)
    x0, x1 = left * width // cells_x, -(-right * width // cells_x)
    y0, y1 = top * height // cells_y, -(-bottom * height // cells_y)
    box = (x0 * cells_x / width, y0 * cells_y / height, x1 * cells_x / width, y1 * cells_y / height)
    grown = np.asarray(
        Image.fromarray(np.ascontiguousarray(logits, np.float32), "F").resize(
            (x1 - x0, y1 - y0), Image.Resampling.BILINEAR, box=box
        ),
        np.float32,
    )
    made = 1.0 / (1.0 + np.exp(-np.clip(grown, -30, 30)))
    found[y0:y1, x0:x1] = (made * 255 + 0.5).astype(np.uint8)
    return found


def grid_size(size: tuple[int, int]) -> tuple[int, int]:
    """The copy the outline is worked out on: the picture's shape, GRID on its long side (never
    bigger than the picture)."""
    width, height = size
    scale = min(GRID / max(width, height), 1.0)
    return max(1, round(width * scale)), max(1, round(height * scale))


def on_grid(logits: Floats, size: tuple[int, int]) -> npt.NDArray[np.bool_]:
    """One answer on the outline's copy: what's in it."""
    grown = Image.fromarray(np.ascontiguousarray(logits, np.float32), "F").resize(
        grid_size(size), Image.Resampling.BILINEAR
    )
    return np.asarray(grown, np.float32) > 0


def drawn(shown: list[npt.NDArray[np.bool_]], size: tuple[int, int]) -> str:
    """The outline round the parts shown (on the outline's copy), as the window's SVG path."""
    if not shown:
        return ""
    every = np.logical_or.reduce(shown)
    grid = grid_size(size)
    return path(outline(every), grid)


def holding(shown: list[npt.NDArray[np.bool_]], x: float, y: float) -> int | None:
    """The last of the parts shown with the point (x, y), as fractions, in it."""
    for at in range(len(shown) - 1, -1, -1):
        grid = shown[at]
        row = min(int(y * grid.shape[0]), grid.shape[0] - 1)
        column = min(int(x * grid.shape[1]), grid.shape[1] - 1)
        if grid[row, column]:
            return at
    return None
