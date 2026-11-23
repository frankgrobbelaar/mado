"""Camera RAW in Mado's words, from what its RAW reader (LibRaw, mado/libraw.py) says of a file:
which way up it goes, the part of the sensor it shows (the RAW's own crop), its size as shown,
whether the preview the camera kept inside it will do for a copy or the picture is developed,
and what the reader's errors mean. Pure.

LibRaw's flip is dcraw's: 4 swaps rows and columns, 2 turns rows over, 1 turns columns over, in
that order, as it lays the stored picture out upright (EXIF's 6, a quarter clockwise, is its 6;
EXIF's 8 its 5).
"""

from dataclasses import dataclass
from typing import Literal

type Box = tuple[int, int, int, int]  # left, top, width, height
type Size = tuple[int, int]
type Way = Literal["preview", "half", "full"]
type Kind = Literal["unknown", "damaged", "memory", "other"]

# The camera's preview stands in for copies up to this size: thumbnails, and a burst's sharpness.
# The view the size of a screen and anything bigger are developed, so a picture's page and its
# tabs show what Save makes.
PREVIEW_UP_TO = 1024
SHAPE = 0.01  # how far a preview's shape can be from the picture's and be the same picture
_NONE = 0xFFFF  # LibRaw's word for a crop that isn't set
_EXIF = {0: 1, 1: 2, 2: 4, 3: 3, 4: 5, 5: 8, 6: 6, 7: 7}  # LibRaw's flip to EXIF's orientation


@dataclass(frozen=True)
class Inset:
    """The RAW's own crop as LibRaw keeps it: on the sensor, margins and all."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class Problem:
    kind: Kind
    sentence: str


def orientation(flip: int) -> int:
    """LibRaw's flip as EXIF's orientation, 1 to 8: a flip it doesn't know is upright."""
    return _EXIF.get(flip, 1)


def shown_crop(
    inset: Inset | None, *, width: int, height: int, left_margin: int = 0, top_margin: int = 0
) -> Box | None:
    """The RAW's own crop (a DNG's default crop, a camera's own) inside the picture LibRaw
    develops, `width` by `height`, kept within it; None when it has none, it's the whole picture,
    or it would keep less than half of either side, which no camera means."""
    if inset is None or inset.left >= _NONE or inset.top >= _NONE:
        return None
    if inset.width <= 0 or inset.height <= 0:
        return None
    left, top = inset.left - left_margin, inset.top - top_margin
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(width, left + inset.width), min(height, top + inset.height)
    if (x1 - x0) * 2 < width or (y1 - y0) * 2 < height:
        return None
    if (x0, y0, x1, y1) == (0, 0, width, height):
        return None
    return x0, y0, x1 - x0, y1 - y0


def turned_box(box: Box, size: Size, flip: int) -> Box:
    """A part of the stored picture (`size` big) where it lands once LibRaw has laid the picture
    out upright by `flip`."""
    x, y, w, h = box
    width, height = size
    corners: list[tuple[int, int]] = []
    for row, column in ((y, x), (y + h - 1, x + w - 1)):
        if flip & 2:
            row = height - 1 - row
        if flip & 1:
            column = width - 1 - column
        corners.append((column, row) if flip & 4 else (row, column))
    rows = [row for row, _ in corners]
    columns = [column for _, column in corners]
    return min(columns), min(rows), max(columns) - min(columns) + 1, max(rows) - min(rows) + 1


def developed_size(width: int, height: int, crop: Box | None, flip: int) -> Size:
    """The picture's size as shown: its crop, turned upright."""
    w, h = (crop[2], crop[3]) if crop is not None else (width, height)
    return (h, w) if flip & 4 else (w, h)


def same_shape(a: Size, b: Size) -> bool:
    if min(*a, *b) <= 0:
        return False
    return abs((a[0] / a[1]) / (b[0] / b[1]) - 1) <= SHAPE


def preview_turn(stored: Size, shown: Size, flip: int) -> int | None:
    """How to lay the camera's preview (`stored` big, as kept in the file) out upright: the
    picture's own flip, or none when the camera kept it upright already; None when its shape is
    the picture's neither way, so it isn't the whole picture."""
    flip = flip if 0 <= flip <= 7 else 0
    turned = (stored[1], stored[0]) if flip & 4 else stored
    if same_shape(turned, shown):
        return flip
    if flip & 4 and same_shape(stored, shown):
        return 0
    return None


def wanted(preview: Size | None, shown: Size, longest: int | None) -> Way:
    """How a copy `longest` pixels on its longer side (None: full size) is made: from the
    camera's preview (upright, `preview` big) when it's that big and the picture's shape, for a
    small copy; else developed, at half size when that's big enough."""
    if longest is None:
        return "full"
    need = min(longest, max(shown))
    if (
        longest <= PREVIEW_UP_TO
        and preview is not None
        and max(preview) >= need
        and same_shape(preview, shown)
    ):
        return "preview"
    return "half" if max(shown) // 2 >= need else "full"


def problem(code: int, stage: Literal["open", "unpack", "develop"], said: str = "") -> Problem:
    """What one of LibRaw's errors means, in a sentence: a RAW it doesn't know, one damaged, one
    too big for the memory free, or anything else with LibRaw's own words."""
    match code:
        case -2 | -8 if stage == "open":
            return Problem(
                "unknown",
                "Mado's RAW reader doesn't know this kind of RAW file yet (a camera newer than "
                "it, say), or it isn't one. Mado left it exactly as it is.",
            )
        case -2 | -8:
            return Problem(
                "unknown",
                "Mado's RAW reader can read its details but not its picture: it's packed in a "
                "way the reader doesn't know yet, as some newer cameras' and phones' are (a DNG "
                "compressed with JPEG XL, say). Mado left it exactly as it is.",
            )
        case -100008 | -100009:
            return Problem(
                "damaged",
                "The file is damaged or was only half copied: Mado's RAW reader stopped partway "
                "through it. Mado left it exactly as it is.",
            )
        case -100007 | -100012 | -100013 | 12:  # 12: ENOMEM, as its picture's copy says it
            return Problem(
                "memory",
                "It's too big to develop with the memory free now. Close other apps, then try "
                "again.",
            )
        case _:
            words = f": {said}" if said else ""
            return Problem(
                "other",
                f"Mado's RAW reader couldn't read it (LibRaw's error {code}{words}). Mado left "
                "it exactly as it is.",
            )
