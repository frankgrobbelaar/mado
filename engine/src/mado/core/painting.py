"""Painting styles, by their rules: Mado's painters, a picture of the owner's as the style, and the
classic means drawn by code. Pure.

Mado's painters are four small networks trained for Mado on public-domain paintings (Van Gogh's
The Starry Night, Hokusai's The Great Wave, Monet's Water Lilies, Seurat's The Channel of
Gravelines), so their licence is Mado's; the paintings never ship, only the networks. A picture
of the owner's gives its colours and textures (never its subject) through MicroAST, as 512
numbers read once. Both paint at a working size: the picture's long side `CANVAS` pixels on a
square canvas that big, the rest of it mirrored, so one session of one fixed size paints every
shape (the same 1.94 megapixels as 1600 × 1200); the painting is then made the size of the
picture made by plain resampling, which keeps every stroke as it was painted
(docs/stack/styles.md). The strokes are the same size against the picture in a preview and in
the picture saved, however big that is.

The classic means (pencil sketch, coloured pencil, oil paint and cartoon) are numpy and
Pillow; each reaches as far as a share of the picture made's short side (`reach`, a hundredth
of it in the pixels at hand), so a preview and the picture saved get the same lines and strokes.
A painting at a strength is mixed with the picture as it was; "the picture's own colours" keeps
the painting's lightness with the picture's colour.
"""

import base64
import binascii
from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageFilter, ImageOps

from mado.core.edits import Part

type Floats = npt.NDArray[np.float32]
type Numbers = npt.NDArray[np.floating[Any]]
type Pixels = npt.NDArray[np.uint8]
type Kind = Literal["painter", "picture", "classic"]

CANVAS = 1392  # the networks' square canvas, a multiple of 4: about 1600 × 1200's pixels
# A small copy's canvas: a third of the working one's sides, a multiple of 4. A small copy is a
# thumbnail, so its strokes can't show; painted this small on the processor, it never takes the
# graphics card's memory for a style no one has chosen.
SMALL_CANVAS = 464
NAMED = 200  # a picture's style is named after the picture, in this many letters at most
CODE = 512  # the numbers MicroAST reads a style picture into
SMALLEST = 96  # a style picture's shorter side, at least, to read a style from
ENLARGED = 5.0  # a painting made this many times bigger than it's painted is soft, seen close
_LUMA = np.array([0.299, 0.587, 0.114], np.float32)  # lightness, as YCbCr reckons it
_PLAIN_COLOURS = 8.0  # a style picture whose colours spread less than this (0 to 255)…
_PLAIN_TEXTURE = 3.0  # …and whose grey steps less than this from pixel to pixel is plain
_KUWAHARA = 6  # the oil's squares are this many pixels across where they're worked out
_CARTOON_SMOOTH = 5  # and the cartoon's smoothing


@dataclass(frozen=True, eq=False)
class Style:
    id: str  # "van-gogh", "pencil", "yours-3"; "picture" for a picture's own, not kept
    name: str  # "After Van Gogh"
    kind: Kind
    download: str | None = None  # a painter's network: its download's id
    painting: str | None = None  # a painter's: the painting it learned from
    setting: str | None = None  # a classic one's one setting: "Darkness"
    first: int = 50  # where that setting starts, 0 to 100
    code: Floats | None = None  # a picture's: the 512 numbers MicroAST read it into


PAINTERS: tuple[Style, ...] = (
    Style("van-gogh", "After Van Gogh", "painter", "style-van-gogh-starry-night",
          "Van Gogh's The Starry Night"),
    Style("hokusai", "After Hokusai", "painter", "style-hokusai-great-wave",
          "Hokusai's The Great Wave off Kanagawa"),
    Style("monet", "After Monet", "painter", "style-monet-water-lilies-1915",
          "Monet's Water Lilies (1915)"),
    Style("seurat", "After Seurat", "painter", "style-seurat-gravelines",
          "Seurat's The Channel of Gravelines"),
)  # fmt: skip
CLASSICS: tuple[Style, ...] = (
    Style("pencil", "Pencil sketch", "classic", setting="Darkness"),
    Style("coloured-pencil", "Coloured pencil", "classic", setting="Darkness"),
    Style("oil", "Oil paint", "classic", setting="Brush"),
    Style("cartoon", "Cartoon", "classic", setting="Colours", first=40),
)


@dataclass(frozen=True)
class Painting:
    """The painting step, as the Looks tab asks for it: a style at a strength, in the picture's
    own colours or the style's, with a classic one's setting; on the whole picture or parts."""

    style: Style
    strength: float = 1.0  # 0 to 1: mixed with the picture as it was
    colours: bool = False  # the picture's own colours, the painting's lightness
    setting: int | None = None  # a classic one's, 0 to 100; None: where it starts
    parts: tuple[Part, ...] = ()  # only on these, picked as Select does; none: everywhere

    @property
    def amount(self) -> int:
        """A classic one's setting, as asked for or as it starts."""
        return self.style.first if self.setting is None else self.setting

    @property
    def keeps_colours(self) -> bool:
        """Its colours are the picture's: a classic one's are anyway, so it's said only of a
        painter's or a picture's."""
        return self.colours and self.style.kind != "classic"


def mado_style(style_id: str) -> Style | None:
    """One of Mado's painters or classic means by its id; None when it isn't one."""
    return next((style for style in (*PAINTERS, *CLASSICS) if style.id == style_id), None)


def picture_style(name: str, code: Floats, style_id: str = "picture") -> Style:
    """A picture's own style, by the 512 numbers MicroAST read it into: named after it ("Night
    market style"), or as the owner kept it (`style_id` "yours-3", `name` theirs). Raises
    ValueError for numbers that aren't a style's."""
    values = np.asarray(code, np.float32).ravel()
    if values.size != CODE:
        raise ValueError(f"A picture's style is {CODE} numbers, not {values.size}.")
    if not np.isfinite(values).all():
        raise ValueError("A picture's style has numbers that aren't numbers.")
    named = name if style_id != "picture" else f"{name} style"
    return Style(style_id, named, "picture", code=values)


def code_text(code: Floats) -> str:
    """A picture's style as a recipe carries it: its 512 numbers as 32-bit floats, base64."""
    return base64.b64encode(np.asarray(code, "<f4").tobytes()).decode("ascii")


def code_of(text: str) -> Floats:
    """A picture's style from a recipe's text. Raises ValueError for text that isn't one."""
    try:
        data = base64.b64decode(text.encode("ascii"), validate=True)
    except UnicodeEncodeError, binascii.Error:
        raise ValueError("A picture's style isn't written as Mado writes one.") from None
    if len(data) != CODE * 4:
        raise ValueError(f"A picture's style is {CODE} numbers, not {len(data) // 4}.")
    values = np.frombuffer(data, "<f4").astype(np.float32)
    if not np.isfinite(values).all():
        raise ValueError("A picture's style has numbers that aren't numbers.")
    return values


def label(painting: Painting) -> str:
    """What a new picture's name says of its painting: "After Van Gogh"."""
    return painting.style.name


def phrase(painting: Painting, *, on: str = "") -> str:
    """The painting as History and Save say it, after "with": "After Van Gogh at 80%", where it
    goes (`on`: "on a part"), and ", in the picture's own colours" when they're kept."""
    percent = round(painting.strength * 100)
    said = painting.style.name if percent >= 100 else f"{painting.style.name} at {percent}%"
    said = f"{said} {on}" if on else said
    return f"{said}, in the picture's own colours" if painting.keeps_colours else said


def named_after(stem: str) -> str:
    """What a picture's style is called, after the picture: its name, no longer than `NAMED`."""
    return stem[:NAMED].strip() or "A picture"


def changes(painting: Painting) -> bool:
    return painting.strength > 0


def enlarged(painting: Painting, width: int, height: int) -> str | None:
    """What a picture made `width` by `height` says of a network's painting made `ENLARGED` times
    bigger than it's painted, or more: seen close, its strokes are soft. None otherwise, and for
    a classic means, drawn at the size made."""
    times = max(width, height) / CANVAS
    if painting.style.kind == "classic" or times < ENLARGED:
        return None
    painted = working_size(width, height)
    return (
        f"Painted at {painted[0]} × {painted[1]}, then made {width} × {height}: about "
        f"{round(times)} times bigger, so seen close its strokes are soft. A smaller size on the "
        "Size tab keeps them crisp."
    )


def working_size(width: int, height: int, *, side: int = CANVAS) -> tuple[int, int]:
    """A picture's size as the networks paint it: its long side `side` (the canvas's; a small
    copy's is `SMALL_CANVAS`), its short side in proportion, 4 pixels at least."""
    k = side / max(width, height, 1)
    return (
        min(side, max(4, round(width * k))),
        min(side, max(4, round(height * k))),
    )


def on_canvas(pixels: Pixels, *, side: int = CANVAS) -> tuple[Floats, tuple[int, int]]:
    """A picture at its working size (or smaller) on the networks' square canvas, as they take
    it (1 × 3 × side × side, 0 to 1), in its middle, the rest of the canvas the picture
    mirrored; and where it sits (top, left). Mirrored, its edges carry on as they were, so a
    painting never shows where the canvas began."""
    height, width = pixels.shape[:2]
    top, left = (side - height) // 2, (side - width) // 2
    spread = np.pad(
        pixels.astype(np.float32) / np.float32(255),
        ((top, side - height - top), (left, side - width - left), (0, 0)),
        mode="symmetric",
    )
    return np.ascontiguousarray(spread.transpose(2, 0, 1)[None]), (top, left)


def off_canvas(painted: Floats, at: tuple[int, int], size: tuple[int, int]) -> Pixels:
    """The picture's part of a painted canvas (1 × 3 × side × side, 0 to 1), `size` big, as
    8-bit RGB."""
    top, left = at
    width, height = size
    found = painted[0, :, top : top + height, left : left + width].transpose(1, 2, 0)
    return np.ascontiguousarray((np.clip(found, 0.0, 1.0) * 255 + 0.5).astype(np.uint8))


def mixed(
    painted: Image.Image, picture: Image.Image, strength: float, *, colours: bool
) -> Image.Image:
    """A painting (RGB) at a strength over the picture as it was (RGB, the same size); with
    `colours`, in the picture's own colours: the painting's lightness, the picture's colour."""
    made = painted
    if colours:
        light = painted.convert("YCbCr").getchannel("Y")
        _, blue, red = picture.convert("YCbCr").split()
        made = Image.merge("YCbCr", (light, blue, red)).convert("RGB")
    if strength >= 1.0:
        return made
    return Image.blend(picture, made, max(strength, 0.0))


def classic(image: Image.Image, style: Style, amount: int, *, reach: float) -> Image.Image:
    """A picture (RGB) by one of the classic means at its setting (0 to 100). `reach` is a
    hundredth of the picture made's short side, in this image's pixels."""
    rgb = image.convert("RGB")
    match style.id:
        case "pencil":
            return _pencil(rgb, amount, reach, colour=False)
        case "coloured-pencil":
            return _pencil(rgb, amount, reach, colour=True)
        case "oil":
            return _oil(rgb, amount, reach)
        case "cartoon":
            return _cartoon(rgb, amount, reach)
        case _:
            raise ValueError(f"{style.name} isn't drawn by code.")


def unsuited(pixels: Pixels) -> Literal["small", "plain"] | None:
    """Why a picture can't give a style, or None when it can: smaller than `SMALLEST` on its
    shorter side, or so plain (nearly one colour, nearly no texture) there's no style in it."""
    height, width = pixels.shape[:2]
    if min(height, width) < SMALLEST:
        return "small"
    image = Image.fromarray(pixels).convert("RGB")
    image.thumbnail((256, 256), Image.Resampling.BOX)
    colours = np.asarray(image, np.float32)
    spread = float(colours.reshape(-1, 3).std(axis=0).mean())
    grey = colours @ _LUMA
    steps = (np.abs(np.diff(grey, axis=0)).mean() + np.abs(np.diff(grey, axis=1)).mean()) / 2
    if spread < _PLAIN_COLOURS and float(steps) < _PLAIN_TEXTURE:
        return "plain"
    return None


# The classic means.


def _pencil(image: Image.Image, darkness: int, reach: float, *, colour: bool) -> Image.Image:
    """A pencil sketch: the picture's grey over a blurred negative of it (colour dodge), so only
    where it changes leaves a line, darker as `darkness` goes up; in colour, each colour laid
    lightly on the paper under the lines."""
    grey = image.convert("L")
    negative = ImageOps.invert(grey).filter(ImageFilter.GaussianBlur(max(0.6, 0.8 * reach)))
    light = np.asarray(grey, np.float32) / np.float32(255)
    under = np.asarray(negative, np.float32) / np.float32(255)
    sketch = np.clip(light / np.maximum(1.0 - under, 1e-3), 0.0, 1.0)
    sketch **= np.float32(1.0 + 3.0 * min(max(darkness, 0), 100) / 100)
    if not colour:
        return Image.fromarray(_bytes(sketch), "L").convert("RGB")
    wash = image.filter(ImageFilter.GaussianBlur(max(0.6, 0.6 * reach)))
    tint = 1.0 - 0.55 * (1.0 - np.asarray(wash, np.float32) / np.float32(255))
    return Image.fromarray(_bytes(tint * (0.25 + 0.75 * sketch[..., None])), "RGB")


def _oil(image: Image.Image, brush: int, reach: float) -> Image.Image:
    """Oil paint: a soft Kuwahara filter (each pixel the mean of the four squares round it, each
    weighted by how even it is, so flat parts flatten and edges stay), its squares as wide as
    `brush` says, then brush strokes along the picture's edges caught in light from the top
    left. Worked out where the squares are `_KUWAHARA` pixels across, then made its size."""
    radius = reach * (0.4 + min(max(brush, 0), 100) / 100)
    small, k = _worked(image, radius, _KUWAHARA)
    rgb = np.asarray(small, np.float32) / np.float32(255)
    painted = _kuwahara(rgb, max(1, round(radius * k)))
    light = painted @ _LUMA
    down, across = _slopes(np.asarray(_blurred(light, max(0.6, reach * k)), np.float32))
    along = (np.arctan2(down, across) + np.pi / 2) % np.pi  # a stroke runs along its edge
    quarter = np.round(along / (np.pi / 4)).astype(np.int8) % 4
    strokes = _strokes(light.shape, quarter, reach * k)
    grain_down, grain_across = _slopes(strokes)
    relief = np.clip(-(grain_across + grain_down) * 0.05, -0.06, 0.06).astype(np.float32)
    painted *= (np.float32(1.0) + relief)[..., None]
    made = Image.fromarray(_bytes(painted), "RGB")
    return made if made.size == image.size else made.resize(image.size, Image.Resampling.BICUBIC)


def _cartoon(image: Image.Image, colours: int, reach: float) -> Image.Image:
    """A cartoon: smoothed keeping its edges (a small soft Kuwahara), its lightness in a few
    steps (more as `colours` goes up), each softened at its edge, its colour kept and a little
    fuller, and ink drawn where the smoothed picture darkens across an edge (a difference of
    blurs). After Winnemöller, Olsen and Gooch's video abstraction (2006). Worked out where the
    smoothing reaches `_CARTOON_SMOOTH` pixels, then made its size."""
    radius = reach * 0.6
    small, k = _worked(image, radius, _CARTOON_SMOOTH)
    smooth = _kuwahara(np.asarray(small, np.float32) / np.float32(255), max(1, round(radius * k)))
    shown = Image.fromarray(_bytes(smooth), "RGB")
    ycc = np.asarray(shown.convert("YCbCr"), np.float32) / np.float32(255)
    steps = 3 + round(9 * min(max(colours, 0), 100) / 100)
    step = 1.0 / steps
    light = ycc[..., 0]
    nearest = (np.floor(light / step) + 0.5) * step
    ycc[..., 0] = nearest + (step / 2) * np.tanh((9.0 / step) * (light - nearest))
    ycc[..., 1:] = 0.5 + (ycc[..., 1:] - 0.5) * 1.15
    flat = np.asarray(Image.fromarray(_bytes(ycc), "YCbCr").convert("RGB"), np.float32)
    grey = shown.convert("L")
    sigma = max(0.7, reach * k * 0.3)
    near = np.asarray(grey.filter(ImageFilter.GaussianBlur(sigma)), np.float32)
    far = np.asarray(grey.filter(ImageFilter.GaussianBlur(sigma * 1.6)), np.float32)
    ink = np.clip(((near - far) / 255 + 0.035) / 0.02, 0.0, 1.0)  # 0: ink
    made = Image.fromarray(_bytes(flat / 255 * (0.15 + 0.85 * ink[..., None])), "RGB")
    return made if made.size == image.size else made.resize(image.size, Image.Resampling.BICUBIC)


def _worked(image: Image.Image, radius: float, most: int) -> tuple[Image.Image, float]:
    """The picture as a filter whose squares reach `radius` pixels works on it: made smaller till
    they reach `most` (they need no more to look the same, and it's much quicker), with how much
    smaller."""
    k = min(1.0, most / max(radius, 1e-6))
    if k >= 1.0:
        return image, 1.0
    size = (max(8, round(image.width * k)), max(8, round(image.height * k)))
    return image.resize(size, Image.Resampling.BOX), size[0] / image.width


def _kuwahara(rgb: Floats, radius: int) -> Floats:
    """A soft Kuwahara filter: each pixel the mean of the four (radius + 1)-pixel squares that
    have it at a corner, each weighted by 1 / its variance⁴ (Papari, Petkov and Campisi's soft
    choice, which leaves none of the plain filter's blocks)."""
    height, width = rgb.shape[:2]
    padded = np.pad(rgb, ((radius, radius), (radius, radius), (0, 0)), mode="reflect")
    light = padded @ _LUMA
    channels = np.concatenate([padded, light[..., None], (light * light)[..., None]], axis=2)
    means = _boxed(channels, radius)
    means *= np.float32(1.0 / (radius + 1) ** 2)
    total = np.zeros((height, width, 3), np.float32)
    weights = np.zeros((height, width), np.float32)
    for down in (0, radius):
        for across in (0, radius):
            square = means[down : down + height, across : across + width]
            spread = square[..., 4] - square[..., 3] * square[..., 3]
            np.maximum(spread, 0.0, out=spread)
            spread += np.float32(1e-4)
            spread *= spread
            spread *= spread
            weight = np.float32(1.0) / spread
            total += square[..., :3] * weight[..., None]
            weights += weight
    total /= weights[..., None]
    return total


def _boxed(values: Numbers, radius: int) -> Floats:
    """Sums over every (radius + 1)-pixel square, each at the pixel at its top left: running sums
    along the rows, then down, each a difference of two."""
    across = np.cumsum(values, axis=1, dtype=np.float32)
    rows = np.empty((values.shape[0], values.shape[1] - radius, *values.shape[2:]), np.float32)
    rows[:, 0] = across[:, radius]
    rows[:, 1:] = across[:, radius + 1 :] - across[:, : -radius - 1]
    down = np.cumsum(rows, axis=0, dtype=np.float32)
    found = np.empty((values.shape[0] - radius, *rows.shape[1:]), np.float32)
    found[0] = down[radius]
    found[1:] = down[radius + 1 :] - down[: -radius - 1]
    return found


def _strokes(shape: tuple[int, ...], along: npt.NDArray[np.int8], reach: float) -> Floats:
    """Brush strokes: a fixed noise smeared along each pixel's stroke (across, the two diagonals
    or down), as long as two hundredths of the short side, its spread made 1."""
    height, width = shape[0], shape[1]
    cell = max(1, round(reach * 0.35))
    rows, columns = height // cell + 2, width // cell + 2
    seeds = np.random.default_rng(20261124).random((rows, columns), dtype=np.float32)
    noise = np.asarray(
        Image.fromarray(seeds, "F").resize(
            (columns * cell, rows * cell), Image.Resampling.BILINEAR
        ),
        np.float32,
    )[:height, :width]
    length = max(2, round(reach * 1.6))
    every = max(1, length // 4)
    made = np.zeros((height, width), np.float32)
    for direction, (down, across) in enumerate(((0, 1), (1, 1), (1, 0), (1, -1))):
        smeared = np.zeros((height, width), np.float32)
        for step in range(-length, length + 1, every):
            smeared += np.roll(noise, (step * down, step * across), axis=(0, 1))
        made = np.where(along == direction, smeared, made)
    made -= made.mean()
    made /= made.std() + np.float32(1e-6)
    return made


def _blurred(values: Numbers, sigma: float) -> Image.Image:
    """Values 0 to 1 blurred through Pillow, which does it in C."""
    return Image.fromarray(_bytes(values), "L").filter(ImageFilter.GaussianBlur(sigma))


def _slopes(values: Floats) -> tuple[Floats, Floats]:
    """How fast values change down and across, each pixel."""
    down, across = cast("tuple[Numbers, Numbers]", tuple(np.gradient(values)))
    return down.astype(np.float32), across.astype(np.float32)


def _bytes(values: Numbers) -> Pixels:
    return (np.clip(values, 0.0, 1.0) * 255 + 0.5).astype(np.uint8)
