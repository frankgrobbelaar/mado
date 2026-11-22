"""Giving a picture its look: through the look's one table (Pillow's Color3DLUT, in C, each colour
mixed from the eight points around it), then its finishing touches, drawn by code where they
fall on the picture made (mado/core/touches.py says their shapes).

Pictures come as Mado reads them (mado/pictures.py): RGB, RGBA or grey, 8 bits a channel, with
their colour profile, which stays with them. A look works on the colours as they're stored, in
the picture's own colour space, so a phone's wide colours stay wide. See-through parts are left
exactly as they were, and a grey picture stays grey unless its look or touches give it colour.

The soft touches (glow, the vignette, a light leak) are worked out on a small grid and laid on
with Pillow's blends, in C; grain goes on a band of rows at a time, so an 8K picture never needs
more than a band's worth of numbers, and a band is where a job can stop; dust is drawn last.
`Placement` says where an image sits in the picture made, so a preview the size of a screen, or a
part of it at full detail, gets the touches the picture saved at full size will. The grain of the
last few previews is kept, so going from look to look doesn't make it again.

A part of a picture ("only on the sky") fits in later as a mask between the picture as it came
and as `styled` gives it back: `Image.composite(styled, original, mask)`.
"""

import math
import threading
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from mado.core import touches as touch
from mado.core.grids import Grid
from mado.core.looks import table
from mado.core.recipe import Styling
from mado.core.touches import Touches
from mado.upscale import StoppedError

type Floats = npt.NDArray[np.float32]

_BAND = 2_000_000  # pixels in a band of rows, for grain
_SOFT = 256  # the soft touches are worked out on a grid this big on its longer side
_GLOW_SIDE = 384  # glow is spread on a copy this big on its short side
_KEPT_GRAIN = 4_000_000  # a preview's grain this big or smaller is kept for the next look
_LIGHT_DUST = (248, 246, 238)  # dust caught by the light, as on a scan of film
_DARK_DUST = (18, 16, 14)


@dataclass(frozen=True)
class Placement:
    """Where an image sits in the picture made: its pixels start at `left`, `top` there (in the
    picture made's pixels), each as big as `scale` of them."""

    width: int  # the picture made
    height: int
    left: float = 0.0
    top: float = 0.0
    scale: float = 1.0

    @classmethod
    def fitted(cls, image: tuple[int, int], made: tuple[int, int]) -> Placement:
        """An image of all of the picture made, made smaller to fit somewhere."""
        return cls(made[0], made[1], scale=made[0] / image[0])


def seed_of(path: Path) -> int:
    """The number a picture's touches grow from: the same each time it's made, so its preview and
    the picture saved get the same grain and dust."""
    return zlib.crc32(str(path).casefold().encode())


def through(image: Image.Image, grid: Grid | None) -> Image.Image:
    """The picture through a look's table, see-through parts kept; as it is with no table."""
    if grid is None:
        return image
    profile = image.info.get("icc_profile")
    shown = _colour(image)
    made = shown.filter(ImageFilter.Color3DLUT(grid.shape[0], grid))
    if isinstance(profile, bytes):
        made.info["icc_profile"] = profile
    return made


def styled(
    image: Image.Image,
    styling: Styling,
    *,
    seed: int,
    placement: Placement | None = None,
    stop: Callable[[], bool] = lambda: False,
) -> Image.Image:
    """The picture with its look at its strength and its finishing touches. `placement` says where
    `image` sits in the picture made (by default it is the picture made). Raises StoppedError
    when `stop` says so, between touches and between grain's bands."""
    at = placement or Placement(image.width, image.height)
    profile = image.info.get("icc_profile")
    grey = image.mode in ("L", "1", "I", "I;16", "F")
    alpha = _alpha(image)
    made = through(image, table(styling.look, styling.strength, styling.touches))
    rgb = _colour(made).convert("RGB")
    if styling.touches.spatial():
        rgb = _touched(rgb, styling.touches, seed, at, stop)
    result: Image.Image = rgb
    if alpha is not None:
        result.putalpha(alpha)
    elif grey and _all_grey(rgb):
        result = rgb.convert("L")
    if isinstance(profile, bytes):
        result.info["icc_profile"] = profile
    return result


def _colour(image: Image.Image) -> Image.Image:
    """The picture in RGB, or RGBA when it has see-through parts: what the table takes."""
    if image.mode in ("RGB", "RGBA"):
        return image
    if "A" in image.getbands() or "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


def _alpha(image: Image.Image) -> Image.Image | None:
    if image.mode == "RGBA":
        return image.getchannel("A")
    if "A" in image.getbands() or "transparency" in image.info:
        return image.convert("RGBA").getchannel("A")
    return None


def _all_grey(image: Image.Image) -> bool:
    pixels = np.asarray(image)
    return bool(
        np.array_equal(pixels[..., 0], pixels[..., 1])
        and np.array_equal(pixels[..., 1], pixels[..., 2])
    )


def _touched(
    image: Image.Image, touches: Touches, seed: int, at: Placement, stop: Callable[[], bool]
) -> Image.Image:
    """The touches on the picture (RGB), in the order light would meet them: glow, the vignette,
    a light leak, grain, then dust on top."""
    if touches.glow > 0:
        image = ImageChops.screen(image, _glow(image, at, touches.glow))
    if touches.vignette > 0:
        kept = _soft(
            image.size, at, lambda x, y: touch.vignette(_centred(x), _centred(y), touches.vignette)
        )
        image = ImageChops.multiply(image, kept.convert("RGB"))
    if touches.leak > 0:
        leak = touch.leak(seed)
        aspect = at.width / at.height
        light = _soft(
            image.size, at, lambda x, y: touch.leak_light(x, y, aspect, leak, touches.leak)
        )
        # The leak's light in its colour: each of red, green and blue its share of it.
        coloured = [
            light.point([round(level * share) for level in range(256)]) for share in leak.colour
        ]
        image = ImageChops.screen(image, Image.merge("RGB", coloured))
    if stop():
        raise StoppedError
    if touches.grain > 0:
        image = _grained(image, seed, touches.grain, at, stop)
    if touches.dust > 0:
        _dust(image, seed, touches.dust, at)
    return image


def _places(start: float, pixels: range, scale: float, total: int) -> Floats:
    """Where these pixels' middles fall in the picture made, as fractions of it."""
    middles = (
        np.arange(pixels.start, pixels.stop, dtype=np.float32) + np.float32(0.5)
    ) * np.float32(scale)
    return ((middles + np.float32(start)) / np.float32(total)).astype(np.float32)


def _centred(places: Floats) -> Floats:
    """Fractions of the picture made (0 to 1) as reaches from its middle (-1 to 1)."""
    return (places * np.float32(2) - np.float32(1)).astype(np.float32)


def _soft(
    size: tuple[int, int], at: Placement, shade: Callable[[Floats, Floats], Floats]
) -> Image.Image:
    """A soft touch's share of light (0 to 1, as 0 to 255) for each pixel of an image `size` big:
    `shade` worked out on a small grid over it (from places as fractions of the picture made,
    across and down), then made the image's size smoothly."""
    width, height = size
    k = min(1.0, _SOFT / max(width, height))
    small = (max(2, round(width * k)), max(2, round(height * k)))
    # A small grid's pixel spans this many of the image's, each `at.scale` of the picture made's.
    across = _places(at.left, range(small[0]), width / small[0] * at.scale, at.width)
    down = _places(at.top, range(small[1]), height / small[1] * at.scale, at.height)
    shares = np.clip(shade(across[None, :], down[:, None]) * 255 + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(shares, "L").resize(size, Image.Resampling.BILINEAR)


def _glow(image: Image.Image, at: Placement, amount: int) -> Image.Image:
    """The glow's light, spread as far as glow reaches in the picture made and at its strength:
    the bright parts of a small copy, blurred, made the picture's size."""
    k = min(1.0, _GLOW_SIDE / min(image.size))
    small = image.resize(
        (max(1, round(image.width * k)), max(1, round(image.height * k))), Image.Resampling.BOX
    )
    light = touch.glow_light(np.asarray(small).astype(np.float32) / np.float32(255))
    share = touch.glow_share(amount)
    lit = Image.fromarray(np.clip(light * 255 * share + 0.5, 0, 255).astype(np.uint8), "RGB")
    spread = touch.GLOW_REACH * min(at.width, at.height) / at.scale * k
    return lit.filter(ImageFilter.GaussianBlur(max(spread, 0.5))).resize(
        image.size, Image.Resampling.BILINEAR
    )


def _grained(
    image: Image.Image, seed: int, amount: int, at: Placement, stop: Callable[[], bool]
) -> Image.Image:
    """Grain added a band of rows at a time: the same in red, green and blue, strongest in the
    mid-tones (mado/core/touches.py)."""
    width, height = image.size
    pixels = np.asarray(image).copy()
    light = np.asarray(image.convert("L"))
    weights = touch.grain_weights(amount)
    field = _kept_field(seed, at, width, height)
    rows = max(16, _BAND // max(width, 1))
    for top in range(0, height, rows):
        if stop():
            raise StoppedError
        bottom = min(top + rows, height)
        specks = field[top:bottom] if field is not None else _field(seed, at, top, bottom, width)
        added = np.rint(specks * weights[light[top:bottom]]).astype(np.int16)
        band = pixels[top:bottom].astype(np.int16) + added[..., None]
        pixels[top:bottom] = np.clip(band, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels, "RGB")


_fields: dict[tuple[object, ...], Floats] = {}
_fields_lock = threading.Lock()


def _kept_field(seed: int, at: Placement, width: int, height: int) -> Floats | None:
    """A preview's grain, kept for the next look tried on it (the last few); None for a picture
    too big to keep it for, whose grain is made a band at a time."""
    if width * height > _KEPT_GRAIN:
        return None
    key = (seed, at, width, height)
    with _fields_lock:
        found = _fields.get(key)
    if found is not None:
        return found
    made = _field(seed, at, 0, height, width)
    made.flags.writeable = False
    with _fields_lock:
        if len(_fields) >= 4:
            _fields.pop(next(iter(_fields)))
        _fields[key] = made
    return made


def _field(seed: int, at: Placement, top: int, bottom: int, width: int) -> Floats:
    """Grain's specks for rows `top` to `bottom`: its cells in the picture made, resized to the
    band's pixels exactly, so bands, previews and parts all meet the same grain."""
    cell = touch.grain_cell(min(at.width, at.height))
    x0, x1 = at.left / cell, (at.left + width * at.scale) / cell
    y0, y1 = (at.top + top * at.scale) / cell, (at.top + bottom * at.scale) / cell
    first_row, first_column = math.floor(y0) - 2, math.floor(x0) - 2
    rows = range(first_row, math.ceil(y1) + 2)
    columns = range(first_column, math.ceil(x1) + 2)
    cells = Image.fromarray(touch.noise(seed, rows, columns), "F")
    box = (x0 - first_column, y0 - first_row, x1 - first_column, y1 - first_row)
    made = cells.resize((width, bottom - top), Image.Resampling.BICUBIC, box=box)
    return np.asarray(made, np.float32)


def _dust(image: Image.Image, seed: int, amount: int, at: Placement) -> None:
    """Specks of dust and the odd hair, drawn where they fall on the picture made: light ones as
    a scan of film shows them, dark ones as a print's."""
    short = min(at.width, at.height)
    masks = {True: Image.new("L", image.size, 0), False: Image.new("L", image.size, 0)}
    pens = {light: ImageDraw.Draw(mask) for light, mask in masks.items()}
    for speck in touch.specks(seed, amount, at.width / at.height):
        pen = pens[speck.light]
        if speck.hair:
            line = [
                ((x * at.width - at.left) / at.scale, (y * at.height - at.top) / at.scale)
                for x, y in speck.hair
            ]
            thick = speck.size * short / at.scale
            shade = round(255 * speck.opacity * min(1.0, thick))
            pen.line(line, fill=shade, width=max(1, round(thick)))
            continue
        x = (speck.x * at.width - at.left) / at.scale
        y = (speck.y * at.height - at.top) / at.scale
        radius = speck.size * short / at.scale
        if not (-radius <= x <= image.width + radius and -radius <= y <= image.height + radius):
            continue
        if radius < 0.75:  # smaller than a pixel: one pixel, as faint as it's small
            pen.point((x, y), fill=round(255 * speck.opacity * (radius / 0.75) ** 2))
        else:
            pen.polygon(touch.corners(speck, x, y, radius), fill=round(255 * speck.opacity))
    for light, mask in masks.items():
        if mask.getbbox() is None:
            continue
        soft = mask.filter(ImageFilter.GaussianBlur(0.6))
        image.paste(_LIGHT_DUST if light else _DARK_DUST, mask=soft)
