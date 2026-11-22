"""What a picture is, for choosing how to make it bigger: a photo, a drawing (illustrations,
comics, flat-colour art), pixel art (kept blocky, no AI) or a screenshot (made bigger gently, so
no letters are invented). Guessed from its name, its camera and a small copy of its pixels; the
owner can always say otherwise. Pure.

The clues, in order: a name that says screenshot; a camera in its EXIF (a photo); a tiny
picture of a few colours, or one made bigger by repeating its pixels (pixel art); and how much
of it is flat, exactly one colour across neighbouring pixels, which a camera never makes but
drawings and screens do.
"""

import re
from typing import Literal

import numpy as np
import numpy.typing as npt

type Kind = Literal["photo", "drawing", "pixels", "screenshot"]
type Pixels = npt.NDArray[np.uint8]  # (height, width, 3) RGB

KINDS: tuple[Kind, ...] = ("photo", "drawing", "pixels", "screenshot")
NAMES: dict[Kind, str] = {
    "photo": "Photo",
    "drawing": "Drawing",
    "pixels": "Pixel art",
    "screenshot": "Screenshot",
}

_SCREENSHOT = re.compile(r"screen ?shot|screen capture|capture|snip|schermafbeelding", re.I)
_PIXEL_ART_SIDE = 256  # pixel art this small or smaller is drawn pixel by pixel
_PALETTE = 64  # colours pixel art drawn pixel by pixel keeps to
_FEW_COLOURS = 256
_FLAT_SCREEN = 0.55  # a screenshot: this much flat, in a lossless file
_FLAT_DRAWING = 0.3
# Screens' heights (and widths, for a phone's), as their screenshots come.
_SCREEN_SIDES = frozenset(
    {720, 768, 800, 864, 900, 1024, 1050, 1080, 1200, 1280, 1440, 1600, 1920, 2160, 2560, 2880}
)
_LOSSLESS = frozenset({"PNG", "GIF", "BMP", "TIFF"})


def guess(
    small: Pixels,
    *,
    name: str,
    camera: str | None,
    format_: str | None,
    width: int,
    height: int,
) -> Kind:
    """What a `width` by `height` picture called `name` most likely is, from `small`, a copy of
    it no bigger than a few hundred pixels (or the picture itself, when it's that small),
    shrunk without smoothing, so its pixels stay as they are."""
    if _SCREENSHOT.search(name):
        return "screenshot"
    if camera:
        return "photo"
    colours = colour_count(small)
    flat = flatness(small)
    if max(width, height) <= _PIXEL_ART_SIDE and colours <= _PALETTE:
        return "pixels"
    if colours <= _FEW_COLOURS and repeats(small) >= 2:
        return "pixels"
    lossless = (format_ or "").upper() in _LOSSLESS
    if lossless and flat >= _FLAT_SCREEN and (width in _SCREEN_SIDES or height in _SCREEN_SIDES):
        return "screenshot"
    if flat >= _FLAT_DRAWING:
        return "drawing"
    return "photo"


def colour_count(small: Pixels) -> int:
    """How many different colours the copy holds."""
    packed = (
        small[..., 0].astype(np.uint32) << 16
        | small[..., 1].astype(np.uint32) << 8
        | small[..., 2].astype(np.uint32)
    )
    return int(np.unique(packed).size)


def flatness(small: Pixels) -> float:
    """The share of pixels exactly the colour of the pixel to their right and the one below:
    near nothing in a photo (sensor noise, JPEG), much of a drawing or a screen."""
    if small.shape[0] < 2 or small.shape[1] < 2:
        return 0.0
    right = np.all(small[:-1, :-1] == small[:-1, 1:], axis=2)
    below = np.all(small[:-1, :-1] == small[1:, :-1], axis=2)
    return float(np.mean(right & below))


def repeats(small: Pixels) -> int:
    """The biggest block (2 to 8 pixels square) the picture is made of, when it's a smaller one
    made bigger by repeating each pixel; 1 when it isn't."""
    height, width = small.shape[:2]
    for block in range(8, 1, -1):
        if height % block or width % block or height < block * 4 or width < block * 4:
            continue
        corners = small[::block, ::block]
        grown = np.repeat(np.repeat(corners, block, axis=0), block, axis=1)
        if np.array_equal(grown, small):
            return block
    return 1
