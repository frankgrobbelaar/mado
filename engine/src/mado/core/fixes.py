"""The quick fixes, by their rules: noise, blur from a shaking camera or a moving subject, JPEG
blocks and dark photos. Each fix's one setting, the words for it, the models it needs and the
order they're made in; and the maths that isn't a model's: a JPEG's own quality from its tables,
how dark a picture is, brightening it (the exposure set from its brightest parts, then a tone
curve that keeps the highlights), local contrast (CLAHE), the smoothing that keeps a brightened
8-bit picture from banding, and the guard that holds the blur model back in flat places. Pure:
numpy only.

The fixes are a step of the recipe, made after the edits and before the picture grows, so noise
and blocks come out first; inside the step, in this order: JPEG blocks (they were made last, by
the saving), then brightening, then noise (the noise brightening brings out too), then blur
(sharpening noise would only make more of it), then local contrast. SCUNet never runs twice: a
dark photo's denoise and the noise fix are one pass, and so are noise and JPEG blocks at Fast.
docs/stack/fixes.md has how each was chosen and what was measured.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import log2
from typing import Literal, cast

import numpy as np
import numpy.typing as npt

from mado.core.masks import box

type Quality = Literal["fast", "best"]
type Floats = npt.NDArray[np.float32]
type Kind = Literal["noise", "blur", "jpeg", "dark"]
type Own = Literal["own"]  # JPEG blocks as hard as each JPEG's own quality says: a batch's

KINDS: tuple[Kind, ...] = ("noise", "blur", "jpeg", "dark")
WHITE = 0.95  # where the brightest 0.5% of a dark photo is put: just under white
BRIGHTEST = 99.5  # that brightest share, as a percentile of the picture's light
MOST_GAIN = 16.0  # four stops at most
MOST_STOPS = 4.0  # and so a picture not measured yet is planned for as if it's that dark
LEAST_STOPS = 1.0  # under a stop dark (its brightest parts within a stop of white), a picture
# isn't: the dark photo fix leaves it as it is (a well-lit picture with no white in it measures 0.6)
CLEAN_STOPS = 2.0  # this many stops dark or more, a dark photo's denoise runs in full
DARK_STOPS = 1.5  # this many stops dark or more, Mado suggests brightening it
BLOCKY = 60  # a JPEG saved at this quality or under, Mado suggests taking its blocks out
DEBAND_GAIN = 4.0  # brightened this many times or more, an 8-bit file's own steps show as bands
DEBAND_REACH = 15  # how far debanding looks round a pixel: the window's half and the mean's radius
GUARD = 31  # the blur model's change is held to the local contrast over this many pixels
SLACK = 2 / 255  # and a little over it
BROKEN = 0.05  # a tile its answer moves this far on average (0 to 1), it broke down on: a mend
# moved one by 0.02 at most on the made-up scenes, a breakdown by 0.38 or more (docs/stack/fixes.md)
_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)  # Rec. 709's weights, in linear light


class FixError(ValueError):
    """A fix step Mado can't make as it's kept, with a sentence saying why."""


@dataclass(frozen=True)
class Fixing:
    """The fix step, as the Fix tab asks for it: each fix off (None) or on at its one setting.
    Noise and blur: how much of the model's change is kept, 0 to 1. JPEG blocks: how hard, 0 to
    1 (at Best, FBCNN's quality setting: 0.7 takes it for a JPEG saved at 30), or "own" (a
    batch's: as hard as each JPEG was squeezed, a picture that isn't a JPEG left as it is), at
    Fast or Best (None: as this PC has the models). Dark: how much local contrast (CLAHE) is laid
    on after it's brightened and cleaned, 0 to 1; the brightening itself is measured, not set."""

    noise: float | None = None
    blur: float | None = None
    jpeg: float | Own | None = None
    jpeg_quality: Quality | None = None
    dark: float | None = None

    @property
    def on(self) -> tuple[Kind, ...]:
        """The fixes that are on, in the order the Fix tab lists them."""
        return tuple(kind for kind in KINDS if getattr(self, kind) is not None)

    @property
    def blocks(self) -> float:
        """How hard JPEG blocks come out: 0 when that fix is off, or still to be set by the
        picture's own quality (`for_picture`)."""
        return 0.0 if self.jpeg is None or self.jpeg == "own" else float(self.jpeg)


@dataclass(frozen=True)
class FixModel:
    id: str  # downloads.json's id: it's fetched the first time a fix needs it
    file: str
    name: str
    multiple: int  # its height and width must be a multiple of this


SCUNET = FixModel("scunet", "scunet-color-real-psnr.onnx", "SCUNet", 64)
FBCNN = FixModel("fbcnn", "fbcnn-color.onnx", "FBCNN", 8)
NAFNET = FixModel("nafnet", "nafnet-gopro-width32.onnx", "NAFNet", 16)
FIX_MODELS: dict[str, FixModel] = {each.id: each for each in (SCUNET, FBCNN, NAFNET)}


@dataclass(frozen=True)
class Stage:
    """One thing the fix step does, in its order: `amount` is a model's strength, or for
    brightening the stops it brightens by."""

    kind: Literal["blocks", "brighten", "noise", "blur", "contrast"]
    model: FixModel | None
    amount: float


def stages(fixing: Fixing | None, jpeg: Quality, stops: float) -> list[Stage]:
    """What the fix step does to a picture `stops` dark, in order, JPEG blocks at `jpeg`
    (decided); a fix at 0 does nothing, and the dark photo fix nothing to a picture that isn't
    dark (under `LEAST_STOPS`). SCUNet runs once at most, as strong as the strongest fix that
    asks for it: the noise fix, a dark photo's denoise (as much as brightening brought noise out:
    all of it from two stops), JPEG blocks at Fast (twice its strength, so a JPEG saved at 50 or
    under is cleaned in full)."""
    if fixing is None:
        return []
    found: list[Stage] = []
    blocks = fixing.blocks
    if blocks > 0 and jpeg == "best":
        found.append(Stage("blocks", FBCNN, blocks))
    dark = fixing.dark is not None and stops >= LEAST_STOPS
    if dark:
        found.append(Stage("brighten", None, stops))
    clean = max(
        fixing.noise or 0.0,
        min(1.0, 2 * blocks) if jpeg == "fast" else 0.0,
        min(1.0, stops / CLEAN_STOPS) if dark else 0.0,
    )
    if clean > 0:
        found.append(Stage("noise", SCUNET, clean))
    if fixing.blur:
        found.append(Stage("blur", NAFNET, fixing.blur))
    if dark and fixing.dark:
        found.append(Stage("contrast", None, fixing.dark))
    return found


def changing(fixing: Fixing | None, stops: float | None = None) -> tuple[Kind, ...]:
    """The fixes that change a picture `stops` dark, in the Fix tab's order: noise, blur and
    JPEG blocks above 0, and the dark photo fix where it's dark (None: not measured yet, so as
    if it is)."""
    if fixing is None:
        return ()
    dark = fixing.dark is not None and (stops is None or stops >= LEAST_STOPS)
    made = {
        "noise": bool(fixing.noise),
        "blur": bool(fixing.blur),
        "jpeg": fixing.jpeg == "own" or bool(fixing.blocks),
        "dark": dark,
    }
    return tuple(kind for kind in KINDS if made[kind])


def cleans(fixing: Fixing | None, stops: float) -> bool:
    """Whether the fix step leaves a picture `stops` dark clean, so the upscaler keeps its grain
    rather than cleaning it again: the noise fix or JPEG blocks above 0 (as much is taken out as
    the owner asked, and Fast taking more would undo that), or a photo dark enough that its
    denoise runs in full (`CLEAN_STOPS`: under that it takes out only the noise brightening
    brought, and Fast cleans what was there before as it would in any picture)."""
    if fixing is None:
        return False
    dark = fixing.dark is not None and stops >= CLEAN_STOPS
    return bool(fixing.noise) or fixing.blocks > 0 or dark


def strength_for(quality: int) -> float:
    """How hard JPEG blocks come out of a JPEG saved at `quality`: as hard as it was squeezed
    (a JPEG saved at 30, 70%), held to 10% to 90%."""
    return min(0.9, max(0.1, (100 - quality) / 100))


def for_picture(fixing: Fixing | None, saved_at: int | None) -> Fixing | None:
    """A fix step for one picture, a JPEG saved at `saved_at` (None for any other file): JPEG
    blocks asked for by each JPEG's own quality set by it, or left off a picture that isn't a
    JPEG. None when nothing is left on."""
    if fixing is None or fixing.jpeg != "own":
        return fixing
    if saved_at is None:
        found = replace(fixing, jpeg=None, jpeg_quality=None)
    else:
        found = replace(fixing, jpeg=strength_for(saved_at))
    return found if found.on else None


def unchanged(fixing: Fixing) -> str:
    """Why fixes on change nothing in a picture, in a sentence, as a batch's line says it: that it
    isn't dark, or isn't a JPEG."""
    dark = fixing.dark is not None
    jpeg = fixing.jpeg == "own"
    if dark and jpeg:
        return "It isn't dark and it isn't a JPEG, so there was nothing to fix."
    if dark:
        return "It isn't dark, so there was nothing to fix."
    if jpeg:
        return "It isn't a JPEG, so it has no JPEG blocks: there was nothing to fix."
    return "The fixes are at 0%, so there was nothing to fix."


def models_for(fixing: Fixing | None, jpeg: Quality) -> list[FixModel]:
    """The models a fix step needs downloaded, whatever the picture: a dark photo's denoise is
    SCUNet's, as most dark photos need it."""
    if fixing is None:
        return []
    found: list[FixModel] = []
    if fixing.jpeg is not None and jpeg == "best":
        found.append(FBCNN)
    if (
        fixing.noise is not None
        or fixing.dark is not None
        or (fixing.jpeg is not None and jpeg == "fast")
    ):
        found.append(SCUNET)
    if fixing.blur is not None:
        found.append(NAFNET)
    return found


def fixing_from(data: object) -> Fixing | None:
    """A fix step as a recipe keeps it (JSON: each fix null or its setting), None with none on.
    Settings are held to 0 to 1. Raises FixError for one that isn't a fix step."""
    if data is None:
        return None
    if not isinstance(data, dict):
        raise FixError("Mado can't read that fix step: take the fixes off and choose them again.")
    kept = cast("dict[str, object]", data)
    noise = _setting(kept.get("noise"), "strength")
    blur = _setting(kept.get("blur"), "strength")
    jpeg: float | Own | None = (
        "own" if _own(kept.get("jpeg")) else _setting(kept.get("jpeg"), "strength")
    )
    dark = _setting(kept.get("dark"), "contrast")
    quality: Quality | None = None
    if isinstance(kept.get("jpeg"), dict):
        asked = cast("dict[str, object]", kept["jpeg"]).get("quality")
        quality = "fast" if asked == "fast" else "best" if asked == "best" else None
    found = Fixing(noise=noise, blur=blur, jpeg=jpeg, jpeg_quality=quality, dark=dark)
    return found if found.on else None


def _own(value: object) -> bool:
    """A JPEG blocks setting with its strength left to each JPEG's own quality (null)."""
    return isinstance(value, dict) and cast("dict[str, object]", value).get("strength", 0) is None


def _setting(value: object, name: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise FixError("Mado can't read that fix step: take the fixes off and choose them again.")
    found = cast("dict[str, object]", value).get(name, 1.0 if name == "strength" else 0.0)
    if not isinstance(found, int | float):
        raise FixError("Mado can't read that fix step: take the fixes off and choose them again.")
    return min(max(float(found), 0.0), 1.0)


def fixing_json(fixing: Fixing | None) -> dict[str, object] | None:
    """A fix step as a recipe keeps it."""
    if fixing is None:
        return None
    return {
        "noise": None if fixing.noise is None else {"strength": fixing.noise},
        "blur": None if fixing.blur is None else {"strength": fixing.blur},
        "jpeg": None
        if fixing.jpeg is None
        else {
            "quality": fixing.jpeg_quality,
            "strength": None if fixing.jpeg == "own" else fixing.jpeg,
        },
        "dark": None if fixing.dark is None else {"contrast": fixing.dark},
    }


def phrase(fixing: Fixing | None, stops: float | None = None) -> str | None:
    """What the fixes did to a picture `stops` dark (None: not measured, so as asked), as
    History and Save say it: "took out noise and JPEG blocks, brightened it and mended the
    blur"."""
    on = changing(fixing, stops)
    if not on:
        return None
    took = [word for kind, word in (("noise", "noise"), ("jpeg", "JPEG blocks")) if kind in on]
    said: list[str] = []
    if took:
        said.append("took out " + " and ".join(took))
    if "dark" in on:
        said.append("brightened it")
    if "blur" in on:
        said.append("mended the blur")
    return said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"


def label(fixing: Fixing | None, stops: float | None = None) -> str | None:
    """What a new picture's name says the fixes made of it, `stops` dark (None: as asked):
    "Cleaned" (noise or JPEG blocks taken out), "Sharpened", "Brightened", or "Fixed" for more
    than one kind."""
    on = changing(fixing, stops)
    if not on:
        return None
    kinds = {"Cleaned" if kind in ("noise", "jpeg") else kind for kind in on}
    if len(kinds) > 1:
        return "Fixed"
    return {"Cleaned": "Cleaned", "blur": "Sharpened", "dark": "Brightened"}[kinds.pop()]


def detail(fixing: Fixing, jpeg: Quality | None) -> str:
    """The fixes as a batch's steps say them: "Noise at 80%, JPEG blocks at Best, brightened"."""
    said: list[str] = []
    if fixing.noise is not None:
        said.append(f"noise at {round(fixing.noise * 100)}%")
    if fixing.jpeg is not None:
        model = {"fast": "Fast", "best": "Best"}.get(jpeg or "", "as this PC has it")
        hard = (
            "as each JPEG was saved" if fixing.jpeg == "own" else f"at {round(fixing.jpeg * 100)}%"
        )
        said.append(f"JPEG blocks {hard}, {model}")
    if fixing.dark is not None:
        lifted = f" with {round(fixing.dark * 100)}% local contrast" if fixing.dark > 0 else ""
        said.append(f"brightened{lifted}")
    if fixing.blur is not None:
        said.append(f"blur at {round(fixing.blur * 100)}%")
    joined = ", ".join(said)
    return joined[:1].upper() + joined[1:]


# A JPEG's own quality, from its tables.

# The tables the JPEG standard gives (Annex K), in the order Pillow reads them: row by row. Every
# JPEG made by libjpeg's quality setting (Pillow, most apps) is one of these, scaled.
_LUMA_TABLE = (
    *(16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55),
    *(14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62),
    *(18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92),
    *(49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99),
)
_CHROMA_TABLE = (
    *(17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99),
    *(24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99, 99, 99, 99),
    *((99,) * 32),
)


def _scaled(table: Sequence[int], quality: int) -> npt.NDArray[np.int64]:
    """A standard table at a libjpeg quality, as libjpeg scales it (baseline: 1 to 255)."""
    scale = 5000 // quality if quality < 50 else 200 - 2 * quality
    values = (np.array(table, np.int64) * scale + 50) // 100
    return np.clip(values, 1, 255)


_STANDARD = [(q, _scaled(_LUMA_TABLE, q), _scaled(_CHROMA_TABLE, q)) for q in range(1, 101)]


def jpeg_quality(tables: Mapping[int, Sequence[int]]) -> int | None:
    """The quality a JPEG was saved at (1 to 100), from its quantization tables (Pillow's
    `quantization`): the standard tables' quality nearest them. None without tables."""
    luma = tables.get(0)
    if luma is None or len(luma) != 64:
        return None
    seen = np.array(luma, np.int64)
    chroma = tables.get(1)
    seen_chroma = np.array(chroma, np.int64) if chroma is not None and len(chroma) == 64 else None
    best, error = 0, None
    for quality, standard, standard_chroma in _STANDARD:
        off = float(np.abs(seen - standard).sum())
        if seen_chroma is not None:
            off += float(np.abs(seen_chroma - standard_chroma).sum()) / 2
        if error is None or off <= error:  # ties: the higher quality, as the tables allow it
            best, error = quality, off
    return best


def blocks_suggested(quality: int | None) -> bool:
    """Whether Mado suggests taking JPEG blocks out: a JPEG saved at `BLOCKY` or under."""
    return quality is not None and quality <= BLOCKY


# Dark photos, by classic means.


def linear(values: Floats, *, back: bool = False) -> Floats:
    """sRGB's values in linear light (Display P3 has the same curve), or `back` again."""
    if back:
        clipped = np.clip(values, 0.0, 1.0)
        return np.where(
            clipped <= 0.0031308, 12.92 * clipped, 1.055 * clipped ** (1 / 2.4) - 0.055
        ).astype(np.float32)
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4).astype(
        np.float32
    )


def luminance(lin: Floats) -> Floats:
    """Each pixel's light, from its colours in linear light."""
    return (lin @ _LUMA).astype(np.float32)


def brightening(luma: Floats) -> tuple[float, float]:
    """How much a picture's light (linear, 0 to 1) is multiplied by, and the white its tone
    curve rolls off into: its brightest 0.5% put just under white, within 1 to 16 times. Never
    the average: a night scene's lights are bright already, so it stays a night scene, where
    putting its average at middle grey pushed it four stops."""
    brightest = float(np.percentile(luma, BRIGHTEST))
    gain = float(np.clip(WHITE / max(brightest, 1e-4), 1.0, MOST_GAIN))
    white = float(np.percentile(luma * gain, 99.9))
    return gain, white


def dark_suggested(stops: float) -> bool:
    """Whether Mado suggests brightening a picture that wants `stops` stops more light."""
    return stops >= DARK_STOPS


def stops_of(gain: float) -> float:
    return log2(gain) if gain > 0 else 0.0


def toned(lin: Floats, white: float) -> Floats:
    """The extended Reinhard tone curve on each pixel's light (colours kept in proportion):
    as it was in the shadows, rolling off so `white` lands on white."""
    y = luminance(lin)
    roll = max(white, 1.0) ** 2
    toned_y = y * (1 + y / roll) / (1 + y)
    scale = np.where(y > 1e-6, toned_y / np.maximum(y, 1e-6), 1.0).astype(np.float32)
    return np.clip(lin * scale[..., None], 0.0, 1.0).astype(np.float32)


def debanded(values: Floats, window: int = 15, radius: int = 8, limit: float = 2.0) -> Floats:
    """An 8-bit picture's own steps (levels 0 to 255, height × width × colours) smoothed where
    it's flat to within a level or two, so brightened a lot they don't show as bands: each pixel
    moved toward the mean of its square `radius` out each way, all the way where its neighbourhood
    (`window` across) is one level flat, not at all where it spans `limit` levels or more. Edges
    and texture keep every level they had, and a grey picture stays grey."""
    light = values.mean(axis=-1).astype(np.float32)
    spread = local_range(light, window)
    weight = np.clip((limit - spread) / limit, 0.0, 1.0)[..., None].astype(np.float32)
    smooth = box(values.astype(np.float32), radius)
    return (values + weight * (smooth - values)).astype(np.float32)


@dataclass(frozen=True)
class Clahe:
    """Contrast-limited local equalisation, worked out once on a small copy of the whole
    picture: each tile's table of lightness levels, and how big a tile is there."""

    luts: Floats  # tiles down × tiles across × 256
    tile_height: float
    tile_width: float


def clahe_luts(lightness: npt.NDArray[np.uint8], tiles: int = 8, clip: float = 2.0) -> Clahe:
    """CLAHE's tables from a picture's lightness (0 to 255), as OpenCV makes them: a grid of
    tiles, each one's histogram clipped at `clip` times its mean and what's over spread evenly,
    its levels then laid out by how many pixels are darker."""
    height, width = lightness.shape
    pad_y, pad_x = (-height) % tiles, (-width) % tiles
    padded = np.pad(lightness, ((0, pad_y), (0, pad_x)), mode="reflect")
    tile_h, tile_w = padded.shape[0] // tiles, padded.shape[1] // tiles
    luts = np.zeros((tiles, tiles, 256), np.float32)
    limit = max(1, int(clip * tile_h * tile_w / 256))
    for i in range(tiles):
        for j in range(tiles):
            part = padded[i * tile_h : (i + 1) * tile_h, j * tile_w : (j + 1) * tile_w]
            hist = np.bincount(part.ravel(), minlength=256).astype(np.int64)
            over = int(np.maximum(hist - limit, 0).sum())
            hist = np.minimum(hist, limit) + over // 256
            hist[: over % 256] += 1
            below: npt.NDArray[np.float64] = np.cumsum(hist).astype(np.float64)
            levels: npt.NDArray[np.float64] = np.rint(below * (255.0 / (tile_h * tile_w)))
            luts[i, j] = np.clip(levels, 0, 255)
    return Clahe(luts, float(tile_h), float(tile_w))


def contrasted(lightness: Floats, clahe: Clahe, at: tuple[float, float, float, float]) -> Floats:
    """Lightness (0 to 255) through CLAHE's tables, each pixel blended between the four tile
    centres round it. `at`: where the part is on the small copy the tables came from, its first
    pixel's place across and down and how far a pixel moves each way, so any part is lifted as
    the whole picture is."""
    height, width = lightness.shape
    tiles_down, tiles_across = clahe.luts.shape[:2]
    x0, y0, step_x, step_y = at
    columns: npt.NDArray[np.float64] = np.arange(width, dtype=np.float64)
    rows: npt.NDArray[np.float64] = np.arange(height, dtype=np.float64)
    xs: npt.NDArray[np.float64] = (x0 + (columns + 0.5) * step_x) / clahe.tile_width - 0.5
    ys: npt.NDArray[np.float64] = (y0 + (rows + 0.5) * step_y) / clahe.tile_height - 0.5
    left = np.clip(np.floor(xs).astype(np.intp), 0, tiles_across - 1)
    top = np.clip(np.floor(ys).astype(np.intp), 0, tiles_down - 1)
    right = np.clip(left + 1, 0, tiles_across - 1)
    bottom = np.clip(top + 1, 0, tiles_down - 1)
    fx: Floats = np.clip(xs - left, 0, 1).astype(np.float32)[None, :]
    fy: Floats = np.clip(ys - top, 0, 1).astype(np.float32)[:, None]
    level = np.clip(np.round(lightness), 0, 255).astype(np.intp)
    a = clahe.luts[top[:, None], left[None, :], level]
    b = clahe.luts[top[:, None], right[None, :], level]
    c = clahe.luts[bottom[:, None], left[None, :], level]
    d = clahe.luts[bottom[:, None], right[None, :], level]
    return ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy).astype(np.float32)


def lightness_of(lin_y: Floats) -> Floats:
    """CIE lightness, 0 to 255 (L* × 2.55), from light in linear light."""
    star = np.where(lin_y > 0.008856, 116 * np.cbrt(np.maximum(lin_y, 0)) - 16, 903.3 * lin_y)
    return (star * 2.55).astype(np.float32)


def light_of(lightness: Floats) -> Floats:
    """Light in linear light from CIE lightness (0 to 255)."""
    star = lightness / 2.55
    return np.where(star > 8, ((star + 16) / 116) ** 3, star / 903.3).astype(np.float32)


# The blur model's guard.


def local_range(values: Floats, window: int) -> Floats:
    """Each value's square of neighbours `window` across, from brightest to darkest (the edges
    repeat outward): by doubling runs, so as quick for a wide square as a small one."""
    highest = _running(values, window, np.maximum)
    lowest = _running(values, window, np.minimum)
    return (highest - lowest).astype(np.float32)


def _running(values: Floats, window: int, pick: np.ufunc) -> Floats:
    out = values
    for axis in (0, 1):
        moved = np.moveaxis(out, axis, 0)
        count = moved.shape[0]
        before = window // 2
        padded = np.concatenate(
            [np.repeat(moved[:1], before, 0), moved, np.repeat(moved[-1:], window - 1 - before, 0)]
        )
        span = 1
        while span * 2 <= window:
            padded = pick(padded[:-span], padded[span:])
            span *= 2
        rest = window - span
        if rest:
            padded = pick(padded[: padded.shape[0] - rest], padded[rest:])
        out = np.moveaxis(padded[:count], 0, axis)
    return np.ascontiguousarray(out, np.float32)


def guarded(before: Floats, after: Floats, window: int = GUARD, slack: float = SLACK) -> Floats:
    """The blur model's answer (1 × 3 × height × width, 0 to 1) with each pixel's change held
    to the local contrast of what it was given (its light's range over `window` square, and
    `slack` more). Sharpening makes edges crisper, and a flat place has none, so what the model
    invents there is held back: trained on photos that never had a flat area, it returns
    -275 to 690 on a flat grey square. A tile it broke down on comes back as it was: one its
    answer moved by `BROKEN` or more on average (colours anywhere, as beside a road's straight
    line), where a mend moves a tile by a few levels."""
    if float(np.abs(after - before).mean()) >= BROKEN:
        return before.astype(np.float32)
    light = before[0, 0] * 0.299 + before[0, 1] * 0.587 + before[0, 2] * 0.114
    allowed = (local_range(light.astype(np.float32), window) + slack)[None, None]
    change = np.clip(after - before, -allowed, allowed)
    return np.clip(before + change, 0.0, 1.0).astype(np.float32)
