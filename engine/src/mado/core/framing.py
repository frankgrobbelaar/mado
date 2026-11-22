"""The shape a picture takes for a size: cropped around its subject, or its edges extended, and
the words saying what that does. Where the subject is, when the owner hasn't said, comes from a
small grey copy of the picture: the most detailed part, a little drawn to the middle. Pure.

Geometry is in the picture's own pixels, as it's shown (turned upright). A crop keeps the
biggest part of the picture with the size's shape, centred on the focus point as far as the
edges let it; extending keeps all of the picture and adds to two of its sides, so the canvas has
the size's shape, the picture in its middle.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from mado.core.sizes import shape_name

type Shape = Literal["crop", "extend"]
type Sides = Literal["none", "top and bottom", "sides"]
type Grey = npt.NDArray[np.float32]

_SAME = 0.004  # shapes this close are the same: a few pixels either way, resized away


@dataclass(frozen=True)
class Box:
    """A part of the picture, in its pixels; fractional, so a crop has the size's shape
    exactly."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Frame:
    shape: Shape
    kept: Box  # the part of the picture kept: all of it when extending
    canvas: Box  # what's made, in the picture's pixels: the kept part, or more when extending
    sides: Sides  # where the picture loses or gains
    share: float  # of the picture cropped away (crop), or of the canvas drawn new (extend)


def frame(
    width: int,
    height: int,
    target_width: int,
    target_height: int,
    shape: Shape,
    focus: tuple[float, float] = (0.5, 0.5),
) -> Frame:
    """The part of a `width` by `height` picture kept, and the canvas made, for a size of
    `target_width` by `target_height`: cropped around `focus` (fractions of the picture across
    and down), or extended."""
    whole = Box(0.0, 0.0, float(width), float(height))
    ratio, wanted = width / height, target_width / target_height
    if abs(ratio - wanted) / wanted < _SAME:
        return Frame(shape, whole, whole, "none", 0.0)
    wider = wanted > ratio  # the size is wider than the picture
    if shape == "crop":
        fx, fy = (min(max(value, 0.0), 1.0) for value in focus)
        if wider:  # keep the whole width, lose some of the top and bottom
            kept_height = width / wanted
            y = _clamp(fy * height - kept_height / 2, 0.0, height - kept_height)
            kept = Box(0.0, y, float(width), kept_height)
            return Frame(shape, kept, kept, "top and bottom", 1 - kept_height / height)
        kept_width = height * wanted
        x = _clamp(fx * width - kept_width / 2, 0.0, width - kept_width)
        kept = Box(x, 0.0, kept_width, float(height))
        return Frame(shape, kept, kept, "sides", 1 - kept_width / width)
    if wider:  # draw more at the sides
        canvas_width = height * wanted
        canvas = Box(-(canvas_width - width) / 2, 0.0, canvas_width, float(height))
        return Frame(shape, whole, canvas, "sides", 1 - width / canvas_width)
    canvas_height = width / wanted
    canvas = Box(0.0, -(canvas_height - height) / 2, float(width), canvas_height)
    return Frame(shape, whole, canvas, "top and bottom", 1 - height / canvas_height)


def note(made: Frame, size_phrase: str, width: int, height: int, target: tuple[int, int]) -> str:
    """What the shape does, in a sentence: "A TV is 16:9 and this picture is 4:3, so a little of
    the top and bottom goes." `size_phrase` names what it's made for, with its article ("A TV",
    "An A4 print")."""
    theirs = shape_name(*target)
    ours = shape_name(width, height)
    if made.sides == "none":
        if theirs:
            return f"This picture is already {theirs}, the shape {_lower(size_phrase)} is."
        return f"This picture already has the shape {_lower(size_phrase)} has."
    if theirs and ours:
        start = f"{size_phrase} is {theirs} and this picture is {ours}"
    else:
        cropping = made.shape == "crop"
        if (made.sides == "top and bottom") == cropping:
            relation = "wider"
        else:
            relation = "narrower" if cropping else "taller"
        start = f"{size_phrase} is {relation} than this picture"
    if made.shape == "crop":
        return f"{start}, so {_amount(made.share)} of the {made.sides} goes."
    return f"{start}, so Mado draws more at the {made.sides}."


def subject(grey: Grey) -> tuple[float, float]:
    """Where a picture's subject most likely is, as fractions across and down: the most detailed
    part of a small grey copy (0 to 1), drawn a little to the middle, since that's where people
    put what they took the picture of. The middle when nothing stands out."""
    height, width = grey.shape
    if height < 3 or width < 3:
        return (0.5, 0.5)
    detail = np.abs(np.diff(grey, axis=1))[:-1, :] + np.abs(np.diff(grey, axis=0))[:, :-1]
    detail = _blurred(detail, max(1, min(height, width) // 12))
    ys, xs = np.mgrid[0 : detail.shape[0], 0 : detail.shape[1]].astype(np.float32)
    cy, cx = (detail.shape[0] - 1) / 2, (detail.shape[1] - 1) / 2
    spread = 0.55 * max(detail.shape)
    middle = np.exp(-(((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * spread**2)))
    weighted = detail * middle
    total = float(weighted.sum())
    if total <= 1e-6 or float(detail.max()) - float(detail.mean()) < 0.01:
        return (0.5, 0.5)
    # The middle of the most detailed tenth: one bright spot shouldn't pull it alone.
    cut = float(np.quantile(weighted, 0.9))
    strong = np.where(weighted >= cut, weighted, 0.0)
    mass = float(strong.sum()) or total
    x = float((strong * xs).sum()) / mass
    y = float((strong * ys).sum()) / mass
    return (
        round((x + 1) / (width), 3),
        round((y + 1) / (height), 3),
    )


def _blurred(values: Grey, radius: int) -> Grey:
    """A box blur, twice (near enough a Gaussian), along both axes, the edges held."""
    out = values.astype(np.float32)
    for _ in range(2):
        for axis in (0, 1):
            out = _box(out, radius, axis)
    return out


def _box(values: Grey, radius: int, axis: int) -> Grey:
    """The mean of each value's `radius` neighbours either way along `axis`, from running sums."""
    rows = values if axis == 0 else values.T
    padded = np.pad(rows, ((radius, radius), (0, 0)), "edge")
    sums = np.zeros((padded.shape[0] + 1, padded.shape[1]), np.float64)
    sums[1:] = np.cumsum(padded, axis=0)
    size = 2 * radius + 1
    count = rows.shape[0]
    mean = ((sums[size : size + count] - sums[:count]) / size).astype(np.float32)
    return mean if axis == 0 else mean.T


def _amount(share: float) -> str:
    if share < 0.3:
        return "a little"
    if share < 0.5:
        return "some"
    return "a lot"


def _lower(phrase: str) -> str:
    """ "A TV" as it reads mid-sentence: "a TV"."""
    first, _, rest = phrase.partition(" ")
    return f"{first.lower()} {rest}" if first in ("A", "An") else phrase


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
