"""Restoring old photos, by their rules: the restore step and its words; telling a black-and-white
or toned print (sepia, a cyanotype) from a colour photo, and a colour photo whose colours have
faded; putting colour onto a picture's own light, so its detail stays its own; bringing faded
colours back by classic means (each colour's own levels from the picture itself, then its colour
lifted as much as fading took it); and the scratch detector's canvases and its mask: what it found
at two sizes, united and grown, then what the owner painted and took away. Pure: numpy and Pillow
on values only.

Restoring is a step of the recipe after the edits and before the fixes, on the picture at its own
size: the scratches filled first, then the colour, so the colouring model never sees a scratch.
Faces are left as they are: no face model on Mado's list may ship. docs/stack/restoring.md has
how each was chosen and what was measured.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, cast

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado.core.edits import EditError, Stroke, strokes_from, strokes_json
from mado.core.masks import Brush, Mask, box, stroked

type Floats = npt.NDArray[np.float32]
type Step = Literal["scratches", "colour", "faded"]
type Kind = Literal["grey", "toned", "colour"]  # what a picture's colours are

STEPS: tuple[Step, ...] = ("scratches", "colour", "faded")
DETECTOR = (
    "oldphoto-scratch-detector"  # downloads.json's ids: fetched the first time each is needed
)
COLOURER = "ddcolor-tiny"
FILLER = "lama"
COLOUR_SIZE = 512  # DDColor sees the picture squeezed to this square
# The detector reads the picture grey with its short side at 256, as its authors run it, and at
# 512, where it's surer of thin lines; each on a canvas twice as long as it's high, so one session
# a size serves every picture (a portrait one turned onto it, a panorama fitted by its long side).
CANVASES: dict[int, tuple[int, int]] = {256: (256, 512), 512: (512, 1024)}
SURE = 0.4  # how sure the detector must be for a pixel to be a scratch, as its authors keep it
MASK_SHORT = 768  # the mask is made, grown and painted with the picture's short side this long
GROW = 3  # pixels it's grown by, round, at that size: covers what the detector's coarse cells miss
MUCH = 0.25  # a mask covering this much of the picture or more is said to be a lot to fill
MOST_MASK = 0.5  # and past this, Mado won't fill it: filling would invent most of the picture
GREY_CHROMA = (
    2.3  # colour this faint, in Lab's units, at most (the 99th percentile): black and white
)
TINT_SPREAD = 1.3  # colour its light doesn't explain, at most: one tint, a toned print
_SMALL = 256  # the copy a picture's colours are measured on, its longer side
_CALM = 2  # its colours smoothed over a square this far each way first: a scanner's noise out
_BINS = 16  # lightness bins, for the colour each bin's light doesn't explain
_LOW, _HIGH = 0.5, 99.5  # each colour's own levels: its darkest and brightest half percent
_OWN = 0.75  # how far toward each colour's own levels, from the three's together
_LUMA = np.array([0.299, 0.587, 0.114], np.float32)
# sRGB's primaries in CIE XYZ (D65), and D65's white, as OpenCV's Lab, which DDColor was made with.
_M = np.array(
    [
        [0.412453, 0.357580, 0.180423],
        [0.212671, 0.715160, 0.072169],
        [0.019334, 0.119193, 0.950227],
    ],
    np.float32,
)
_M_INV = np.linalg.inv(_M).astype(np.float32)
_WHITE = np.array([0.950456, 1.0, 1.088754], np.float32)


class RestoreError(ValueError):
    """A restore step Mado can't make as it's kept, with a sentence saying why."""


@dataclass(frozen=True)
class Restoring:
    """The restore step, as the Fix tab asks for it: scratches and dust filled (the owner's
    strokes over what Mado found: painted adds, Alt takes away), a black-and-white or toned
    picture coloured, or faded colours brought back, each off (None) or on at its strength. The
    strokes are tied to the picture's `version` (None: any, a batch's, which has none). A batch's
    step (`each`) colours only the pictures that aren't in colour and brings back only the colours
    of those that are, and never fills scratches: only the owner can tell a scratch from a line
    that belongs in the picture."""

    scratches: tuple[Stroke, ...] | None = None
    colour: float | None = None
    faded: float | None = None
    version: str | None = None
    each: bool = False

    @property
    def on(self) -> tuple[Step, ...]:
        """The steps that are on, in the order they're made."""
        return tuple(step for step in STEPS if getattr(self, step) is not None)


def changing(restoring: Restoring | None) -> tuple[Step, ...]:
    """The steps that change a picture: scratches (filled as found and painted), and colour or
    faded colours above 0%."""
    if restoring is None:
        return ()
    made = {
        "scratches": restoring.scratches is not None,
        "colour": bool(restoring.colour),
        "faded": bool(restoring.faded),
    }
    return tuple(step for step in STEPS if made[step])


def for_picture(restoring: Restoring | None, kind: Kind) -> Restoring | None:
    """A restore step for one picture whose colours are `kind`: a batch's colours only one that
    isn't in colour and brings back only one that is; None when nothing is left on. A picture's own
    page does as the owner asks."""
    if restoring is None or not restoring.each:
        return restoring
    found = replace(restoring, colour=None) if kind == "colour" else replace(restoring, faded=None)
    return found if found.on else None


def unchanged(restoring: Restoring) -> str:
    """Why a batch's restore step changes nothing in a picture, in a sentence."""
    if restoring.colour is not None and restoring.faded is None:
        return "It's already in colour, so there was nothing to colour."
    if restoring.faded is not None and restoring.colour is None:
        return "It's black and white or a toned print, so it has no faded colours to bring back."
    return "Restoring is at 0%, so there was nothing to restore."


def models_for(restoring: Restoring | None) -> list[str]:
    """The downloads a restore step needs: the detector and LaMa for scratches, DDColor to colour.
    Faded colours come back by classic means."""
    if restoring is None:
        return []
    found: list[str] = []
    if restoring.scratches is not None:
        found += [DETECTOR, FILLER]
    if restoring.colour:  # at 0% it guesses nothing
        found.append(COLOURER)
    return found


def phrase(restoring: Restoring | None) -> str | None:
    """What restoring did, as History and Save say it: "filled its scratches and dust and
    coloured it"."""
    on = changing(restoring)
    if not on:
        return None
    words = {
        "scratches": "filled its scratches and dust",
        "colour": "coloured it",
        "faded": "brought its faded colours back",
    }
    if restoring is not None and restoring.each and "colour" in on and "faded" in on:
        return f"{words['colour']} or {words['faded']}"  # a batch's: each picture as it needs
    said = [words[step] for step in on]
    return said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"


def label(restoring: Restoring | None) -> str | None:
    """What a new picture's name says of it: "Coloured" when that's all, else "Restored"."""
    on = changing(restoring)
    if not on:
        return None
    return "Coloured" if on == ("colour",) else "Restored"


def detail(restoring: Restoring) -> str:
    """A batch's restore step in words: "Black and white and sepia coloured at 80%, faded colours
    brought back at 60%"."""
    said: list[str] = []
    if restoring.scratches is not None:
        said.append("scratches and dust filled")
    if restoring.colour is not None:
        said.append(f"black and white and sepia coloured{_at(restoring.colour)}")
    if restoring.faded is not None:
        said.append(f"faded colours brought back{_at(restoring.faded)}")
    joined = ", ".join(said)
    return joined[:1].upper() + joined[1:]


def _at(strength: float) -> str:
    percent = round(strength * 100)
    return "" if percent >= 100 else f" at {percent}%"


def restoring_from(data: object) -> Restoring | None:
    """A restore step as a recipe keeps it (JSON), None with nothing on. Strengths are held to 0
    to 1. Raises RestoreError for one that isn't a restore step."""
    if data is None:
        return None
    if not isinstance(data, dict):
        raise RestoreError(_UNREAD)
    kept = cast("dict[str, object]", data)
    scratches: tuple[Stroke, ...] | None = None
    if kept.get("scratches") is not None:
        asked = kept["scratches"]
        if not isinstance(asked, dict):
            raise RestoreError(_UNREAD)
        try:
            scratches = strokes_from(cast("dict[str, object]", asked).get("strokes"))
        except EditError:
            raise RestoreError(_UNREAD) from None
    version = kept.get("version")
    found = Restoring(
        scratches=scratches,
        colour=_strength(kept.get("colour")),
        faded=_strength(kept.get("faded")),
        version=version if isinstance(version, str) and version else None,
        each=kept.get("each") is True,
    )
    return found if found.on else None


def _strength(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RestoreError(_UNREAD)
    found = cast("dict[str, object]", value).get("strength", 1.0)
    if not isinstance(found, int | float):
        raise RestoreError(_UNREAD)
    return min(max(float(found), 0.0), 1.0)


def restoring_json(restoring: Restoring | None) -> dict[str, object] | None:
    """A restore step as a recipe keeps it."""
    if restoring is None:
        return None
    return {
        "version": restoring.version,
        "scratches": None
        if restoring.scratches is None
        else {"strokes": strokes_json(restoring.scratches)},
        "colour": None if restoring.colour is None else {"strength": restoring.colour},
        "faded": None if restoring.faded is None else {"strength": restoring.faded},
        "each": restoring.each,
    }


_UNREAD = "Mado can't read that restore step: turn restoring off and choose it again."


# What a picture's colours are.


@dataclass(frozen=True)
class Colours:
    """What a picture's colours are: black and white, one tint (a toned print: sepia's warm
    brown, or another, a cyanotype's blue), or a colour photo. Whether a colour photo has faded
    isn't measured: a misty morning or a scene with no black in it measures as faded as a print
    gone pale (docs/stack/restoring.md). `chroma` is its colour's strength (Lab's units, the 99th
    percentile) and `spread` the colour its light doesn't explain."""

    kind: Kind
    tone: Literal["sepia", "toned"] | None
    chroma: float
    spread: float


def colours_of(rgb: Floats, shown: npt.NDArray[np.bool_] | None = None) -> Colours:
    """What a picture's colours are, from a copy of it (0 to 1, height × width × 3; made smaller
    here when it's big, so grain averages away), its see-through parts left out (`shown`). A toned
    print's colour follows its light: at one lightness, one colour. A colour photo's doesn't: at
    one lightness, a red boat and a green field."""
    small, seen = _smaller(rgb, shown)
    found = lab(small)
    # A scanner's colour noise is pixel to pixel; a tint follows the light smoothly, and a colour
    # photo's colours are bigger than a few pixels: so the colours are smoothed a little first.
    found[..., 1:] = box(np.ascontiguousarray(found[..., 1:]), _CALM)
    pixels = found.reshape(-1, 3)[seen.ravel()] if seen is not None else found.reshape(-1, 3)
    if pixels.shape[0] == 0:
        pixels = found.reshape(-1, 3)
    chroma_each = np.hypot(pixels[:, 1], pixels[:, 2])
    chroma = float(np.percentile(chroma_each, 99))
    spread = _unexplained(pixels)
    if chroma < GREY_CHROMA:
        return Colours("grey", None, chroma, spread)
    if spread < TINT_SPREAD:
        a, b = float(pixels[:, 1].mean()), float(pixels[:, 2].mean())
        hue = float(np.degrees(np.arctan2(b, a))) % 360
        tone: Literal["sepia", "toned"] = "sepia" if 20 <= hue <= 110 else "toned"
        return Colours("toned", tone, chroma, spread)
    return Colours("colour", None, chroma, spread)


def _smaller(
    rgb: Floats, shown: npt.NDArray[np.bool_] | None
) -> tuple[Floats, npt.NDArray[np.bool_] | None]:
    height, width = rgb.shape[:2]
    scale = _SMALL / max(height, width)
    if scale >= 1:
        return rgb, shown
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    channels = [
        np.asarray(
            Image.fromarray(rgb[..., c].astype(np.float32), "F").resize(size, Image.Resampling.BOX)
        )
        for c in range(3)
    ]
    small = np.stack(channels, axis=-1).astype(np.float32)
    if shown is None:
        return small, None
    seen = Image.fromarray(shown.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)
    return small, np.asarray(seen) == 255  # only what's wholly shown


def _unexplained(pixels: Floats) -> float:
    """The colour a picture's light doesn't explain: in each band of lightness, how far its
    colours lie from that band's own (Lab's a and b), weighed by how much of the picture each band
    holds. A toned print's is a grain's worth; a colour photo's, its colours."""
    light = pixels[:, 0]
    bins = np.clip((light / 100 * _BINS).astype(np.intp), 0, _BINS - 1)
    total, weight = 0.0, 0
    for at in range(_BINS):
        inside = pixels[bins == at, 1:]
        count = int(inside.shape[0])
        if count < 20:
            continue
        apart = inside - inside.mean(axis=0)
        total += count * float(np.sqrt((apart**2).sum(axis=1).mean()))
        weight += count
    return total / weight if weight else 0.0


# Lab, as OpenCV and so DDColor have it: lightness 0 to 100, a and b about -128 to 127.


def lab(rgb: Floats) -> Floats:
    """sRGB, 0 to 1 (… × 3), as CIE Lab (D65)."""
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = (linear.astype(np.float32) @ _M.T) / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    y = xyz[..., 1]
    light = np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([light, a, b], axis=-1).astype(np.float32)


def lightness(rgb: Floats) -> Floats:
    """A picture's lightness alone (Lab's L), 0 to 100."""
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    y: Floats = (linear.astype(np.float32) @ _M[1]).astype(np.float32)
    light: Floats = np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y).astype(np.float32)
    return light


def rgb_of(found: Floats) -> Floats:
    """CIE Lab (D65) as sRGB, 0 to 1, what falls outside it held to its edge."""
    light, a, b = found[..., 0], found[..., 1], found[..., 2]
    fy: Floats = ((light + 16) / 116).astype(np.float32)
    fx: Floats = (fy + a / 500).astype(np.float32)
    fz: Floats = (fy - b / 200).astype(np.float32)

    def back(t: Floats) -> Floats:
        return np.where(t > 0.206893, t**3, (t - 16 / 116) / 7.787).astype(np.float32)

    y = np.where(light > 8, fy**3, light / 903.3)
    xyz = np.stack([back(fx), y.astype(np.float32), back(fz)], axis=-1) * _WHITE
    linear = np.clip(xyz.astype(np.float32) @ _M_INV.T, 0.0, 1.0)
    srgb = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)
    return np.clip(srgb, 0.0, 1.0).astype(np.float32)


# Colouring: DDColor guesses colours from the picture's light, at its own size; they go onto the
# picture's own light at its full size, so its detail stays its own.


def grey_input(rgb: Floats) -> Floats:
    """A picture as DDColor sees it: squeezed to its square, its colours taken out (its Lab
    lightness alone, as grey), 0 to 1, as 1 × 3 × 512 × 512."""
    eight = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    squeezed = Image.fromarray(eight, "RGB").resize(
        (COLOUR_SIZE, COLOUR_SIZE), Image.Resampling.BILINEAR
    )
    light = lightness(np.asarray(squeezed, np.float32) / np.float32(255))
    zeros = np.zeros_like(light)
    grey = rgb_of(np.stack([light, zeros, zeros], axis=-1))
    return np.ascontiguousarray(grey.transpose(2, 0, 1)[None], dtype=np.float32)


def coloured(rgb: Floats, ab: Floats, strength: float) -> Floats:
    """A picture (or a band of it, 0 to 1) with colours (Lab's a and b, at its size) put onto its
    own lightness, mixed at `strength` with the colours it had: a black-and-white picture's none, a
    sepia print's brown."""
    if strength <= 0:
        return rgb
    found = lab(rgb)
    own = found[..., 1:]
    mixed = own + np.float32(strength) * (ab - own)
    joined: Floats = np.concatenate([found[..., :1], mixed], axis=-1).astype(np.float32)
    return rgb_of(joined)


# Faded colours back, by classic means: levels from the picture itself, each colour's darkest and
# brightest half percent set to black and white (the levels lost and the cast gone at once), taken
# three quarters of the way from the three colours' levels together, which keep a scene's own
# colour (a sunset's warmth isn't a cast). Measured on made-up faded prints, three quarters took
# the cast out where halfway left half of it, came as near the truth, and nearer for prints faded
# most (docs/stack/restoring.md).


@dataclass(frozen=True)
class Levels:
    """Each colour's black and white, from the picture itself."""

    low: tuple[float, float, float]
    high: tuple[float, float, float]


def levels_of(rgb: Floats, shown: npt.NDArray[np.bool_] | None = None) -> Levels:
    """The levels faded colours come back by, from a copy of the picture (0 to 1), its see-through
    parts left out (`shown`)."""
    pixels = rgb.reshape(-1, 3) if shown is None else rgb[shown]
    if pixels.shape[0] == 0:
        pixels = rgb.reshape(-1, 3)
    low = np.percentile(pixels, _LOW, axis=0)
    high = np.percentile(pixels, _HIGH, axis=0)
    return Levels(
        (float(low[0]), float(low[1]), float(low[2])),
        (float(high[0]), float(high[1]), float(high[2])),
    )


def _stretched(rgb: Floats, low: Floats, high: Floats) -> Floats:
    return np.clip((rgb - low) / np.maximum(high - low, 0.05), 0.0, 1.0).astype(np.float32)


def faded_back(rgb: Floats, levels: Levels, strength: float) -> Floats:
    """A faded colour picture (or a band of it, 0 to 1) with its colours brought back by its
    levels, mixed at `strength` with it as it was."""
    if strength <= 0:
        return rgb
    low = np.array(levels.low, np.float32)
    high = np.array(levels.high, np.float32)
    own = _stretched(rgb, low, high)
    together = _stretched(rgb, low.mean(keepdims=True), high.mean(keepdims=True))
    made = together + np.float32(_OWN) * (own - together)
    return (rgb + np.float32(strength) * (made - rgb)).astype(np.float32)


# Scratches: the detector's canvases, and the mask.


def canvas_for(grey: npt.NDArray[np.uint8], short: int) -> tuple[Floats, tuple[int, int], bool]:
    """A picture (grey, 0 to 255, at the mask's size) as the detector reads it at `short`: its
    short side that long (its long side a multiple of 16, as the authors run it), resized as
    PyTorch does, without smoothing; a portrait one turned on its side, a panorama fitted by its
    long side; laid on the canvas, mirrored out to fill it; its values -1 to 1. Also where on the
    canvas the picture is (rows, columns) and whether it was turned."""
    turned = grey.shape[0] > grey.shape[1]
    lying = grey.T if turned else grey
    height, width = lying.shape
    rows, columns = CANVASES[short]
    if width / height <= columns / rows:
        used = (rows, min(columns, max(16, round(width / height * rows / 16) * 16)))
    else:
        used = (max(1, round(height * columns / width)), columns)
    values: Floats = ((lying.astype(np.float32) / 255 - 0.5) / 0.5).astype(np.float32)
    resized = _bilinear(values, *used)
    canvas = np.pad(resized, ((0, rows - used[0]), (0, columns - used[1])), mode="symmetric")
    return np.ascontiguousarray(canvas[None, None], dtype=np.float32), used, turned


def uncanvassed(answer: Floats, used: tuple[int, int], turned: bool) -> Floats:
    """What the detector said of the picture itself, off its canvas, the picture's own way
    round."""
    found = answer[: used[0], : used[1]]
    return np.ascontiguousarray(found.T if turned else found)


def _bilinear(values: Floats, rows: int, columns: int) -> Floats:
    """Resized as PyTorch's bilinear does, corners not aligned, without smoothing first."""
    height, width = values.shape
    ys = np.clip((np.arange(rows) + 0.5) * height / rows - 0.5, 0, height - 1)
    xs = np.clip((np.arange(columns) + 0.5) * width / columns - 0.5, 0, width - 1)
    y0, x0 = np.floor(ys).astype(np.intp), np.floor(xs).astype(np.intp)
    y1, x1 = np.minimum(y0 + 1, height - 1), np.minimum(x0 + 1, width - 1)
    fy = (ys - y0).astype(np.float32)[:, None]
    fx = (xs - x0).astype(np.float32)[None, :]
    top = values[y0][:, x0] * (1 - fx) + values[y0][:, x1] * fx
    bottom = values[y1][:, x0] * (1 - fx) + values[y1][:, x1] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.float32)


def mask_size(width: int, height: int) -> tuple[int, int]:
    """The size the mask is made, grown and painted at: the picture with its short side
    `MASK_SHORT` long (as the detector was measured), or its own size when it's smaller."""
    short = min(width, height)
    if short <= MASK_SHORT:
        return width, height
    scale = MASK_SHORT / short
    if width <= height:
        return MASK_SHORT, max(1, round(height * scale))
    return max(1, round(width * scale)), MASK_SHORT


def found_mask(answers: Sequence[Floats], size: tuple[int, int]) -> Mask:
    """What the detector found at its sizes (each answer the picture's way round, 0 to 1), as one
    mask `size` big: each made that size cell for cell, a pixel in it where any is sure enough,
    then grown round by `GROW`."""
    width, height = size
    found = np.zeros((height, width), bool)
    for answer in answers:
        rows, columns = answer.shape
        across = np.arange(width) * columns // width
        down = np.arange(height) * rows // height
        found |= answer[down][:, across] >= SURE
    return grown_round(found.astype(np.uint8) * 255, GROW)


def grown_round(mask: Mask, radius: int) -> Mask:
    """A mask grown outward round each of its pixels by `radius` (a disc, not a square)."""
    solid = mask >= 128
    if radius <= 0:
        return solid.astype(np.uint8) * 255
    height, width = solid.shape
    padded = np.pad(solid, radius)
    grown = np.zeros_like(solid)
    reach = radius * (radius + 1)
    for dy in range(-radius, radius + 1):
        half = int(np.floor(np.sqrt(reach - dy * dy)))
        for dx in range(-half, half + 1):
            grown |= padded[radius + dy : radius + dy + height, radius + dx : radius + dx + width]
    return grown.astype(np.uint8) * 255


def marked(found: Mask, strokes: Sequence[Stroke]) -> Mask:
    """What Mado found with the owner's strokes drawn over it, in order, at its size: painting
    adds, Alt takes away (what was found too)."""
    height, width = found.shape
    short = min(width, height)
    brushes = [
        Brush(
            tuple((x * width, y * height) for x, y in stroke.points),
            stroke.size * short,
            stroke.take,
        )
        for stroke in strokes
    ]
    return stroked(brushes, (width, height), onto=found) if brushes else found


def covers(mask: Mask) -> float:
    """How much of the picture a mask covers, 0 to 1."""
    return float(np.count_nonzero(mask >= 128)) / max(mask.size, 1)
