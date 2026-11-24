"""Restoring old photos (docs/stack/restoring.md): scratches and dust found by Microsoft's old-photo
detector and filled by LaMa, a black-and-white or toned picture coloured by DDColor, and faded
colours brought back by classic means; on the picture as its edits leave it, at its own size.

What's worked out is kept, as the edits' masks are: what the detector found on a picture as its
edits leave it, in memory and in the cache (`cache/edits`, by the picture and its version, so it
goes with the edits' masks after a month); the picture with its scratches filled, for the owner's
latest strokes; DDColor's colours for it; and its levels. Colour and faded colours are laid on
wherever the picture is shown or saved, from what's kept: on a small copy for the stage, a part at
full detail, or the whole picture a band of rows at a time, so a strength moved never waits for a
model. Nothing here touches the picture's file.
"""

import hashlib
import itertools
import json
import logging
import threading
import time
import zlib
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image

from mado.ai import DETECTOR, DETECTOR_FILE, ERASE_SIZE, Ai, Fill, Timer
from mado.core.edits import strokes_json
from mado.core.hardware import Place
from mado.core.masks import Mask
from mado.core.restore import (
    CANVASES,
    MOST_MASK,
    Levels,
    Restoring,
    canvas_for,
    coloured,
    covers,
    faded_back,
    found_mask,
    grey_input,
    levels_of,
    marked,
    mask_size,
    uncanvassed,
)
from mado.extend import grain
from mado.upscale import Pixels, StoppedError, bled

log = logging.getLogger(__name__)

FILL_SHORT = 768  # scratches are filled on a copy with its short side this long at most: as good
# inside the scratches as filling at 1536 or the picture's own size, on made-up 12 MP prints, and
# 2.6 and 6.7 times as quick (docs/stack/restoring.md)
_STRIDE = 448  # LaMa's squares step this far, overlapping by the rest of its 512
_ROWS = 512  # rows laid on at a time over the whole picture
_LEVELS = 1024  # the copy faded colours' levels are measured on, its longer side
_FILLED = 60_000_000  # pixels of pictures with their scratches filled kept in memory at most
_KEPT = 16  # what the detector found, DDColor's colours and the levels: kept for this many
_LOCKS = 64


class RestoringError(Exception):
    """Restoring Mado can't do, with a sentence saying why."""


@dataclass(frozen=True)
class Found:
    """What the detector found on a picture, as a mask at the mask's size (grown), and how
    finding it went: its seconds, where it ran and how long it waited for the graphics card
    (all nothing when it was kept)."""

    mask: Mask
    seconds: float = 0.0
    place: Place | None = None
    waited: float = 0.0


@dataclass(frozen=True)
class Prepared:
    """A picture ready to be shown or saved restored: as its edits leave it with its scratches
    filled, and what laying colour or faded colours on any part of it takes."""

    picture: Image.Image
    restoring: Restoring
    ab: npt.NDArray[np.float32] | None  # DDColor's colours at its square, when colouring
    levels: Levels | None  # faded colours' levels, when bringing them back
    filled: float  # how much of the picture was filled: 0 without scratches


class Restorer:
    def __init__(self, ai: Ai, folder: Path) -> None:
        """`folder`: where what the detector found is kept (the data folder's `cache/edits`,
        beside the edits' masks)."""
        self._ai = ai
        self._folder = folder
        self._lock = threading.Lock()
        self._making = [threading.RLock() for _ in range(_LOCKS)]
        self._found: OrderedDict[str, Mask] = OrderedDict()
        self._filled: OrderedDict[str, tuple[Image.Image, float]] = OrderedDict()
        self._ab: OrderedDict[str, npt.NDArray[np.float32]] = OrderedDict()
        self._levels: OrderedDict[str, Levels] = OrderedDict()

    def ready(self) -> bool:
        """Whether the scratch detector is downloaded."""
        return self._ai.restore_file(DETECTOR, DETECTOR_FILE) is not None

    def found(self, state: Image.Image, key: str, at: str, *, keep: bool = True) -> Found:
        """What the detector finds on the picture as its edits leave it (`state`; `key` names
        the picture and its version, `at` it with its edits): grey, at two sizes, at the mask's
        size, united and grown. Kept unless `keep` is off (a batch's picture). Raises ModelError
        when the detector isn't there or can't run."""
        size = mask_size(state.width, state.height)
        name = f"scratches-{at}"
        kept = self._kept_mask(name, key, size)
        if kept is not None:
            return Found(kept)
        with self._making[hash(key) % _LOCKS]:
            kept = self._kept_mask(name, key, size)
            if kept is not None:
                return Found(kept)
            began = time.perf_counter()
            timer = Timer()
            find, place = self._ai.scratch_finder(timer)
            colours, _alpha = _split(state)
            grey = Image.fromarray(colours, "RGB").convert("L")
            small = np.asarray(grey.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0))
            answers: list[npt.NDArray[np.float32]] = []
            for short in CANVASES:
                canvas, used, turned = canvas_for(small, short)
                answers.append(uncanvassed(find(canvas), used, turned))
            mask = found_mask(answers, size)
            if keep:
                self._keep_mask(name, key, mask)
            return Found(mask, time.perf_counter() - began, place, timer.waited)

    def mask(
        self, state: Image.Image, key: str, at: str, restoring: Restoring, *, keep: bool = True
    ) -> Mask:
        """What Mado fills: what the detector found with the owner's strokes over it."""
        found = self.found(state, key, at, keep=keep).mask
        return marked(found, restoring.scratches or ())

    def prepared(
        self,
        state: Image.Image,
        key: str,
        at: str,
        restoring: Restoring,
        *,
        stop: Callable[[], bool] = lambda: False,
        keep: bool = True,
    ) -> Prepared:
        """The picture as its edits leave it (`state`) ready to be restored: its scratches filled
        as found and painted, DDColor's colours guessed from it once they're filled, and its
        levels measured. Raises RestoringError for a mask over most of the picture, ModelError
        when a model can't run, StoppedError when stopped between models."""
        picture, filled = state, 0.0
        if restoring.scratches is not None:
            picture, filled = self._scratches_filled(state, key, at, restoring, stop, keep)
        made = _made(at, restoring)
        ab = None
        if restoring.colour:  # at 0% there's nothing to guess
            if stop():
                raise StoppedError
            ab = self._colours(picture, made, keep)
        levels = self._levels_of(picture, made, keep) if restoring.faded else None
        return Prepared(picture, restoring, ab, levels, filled)

    def shown(
        self, prepared: Prepared, part: Image.Image, box: tuple[float, float, float, float]
    ) -> Image.Image:
        """A part of the prepared picture (`part`, any size: a small copy, a part at full
        detail, a band of rows), which shows `box` of it (left, top, right, bottom, in its
        pixels), with its colour and faded colours laid on. See-through parts stay as they
        are; a black-and-white picture stays so unless it's coloured."""
        restoring = prepared.restoring
        colouring = bool(restoring.colour) and prepared.ab is not None
        fading = bool(restoring.faded) and prepared.levels is not None
        if not colouring and not fading:
            return part
        profile = part.info.get("icc_profile")
        colours, alpha = _split(part)
        rgb: npt.NDArray[np.float32] = (colours / np.float32(255)).astype(np.float32)
        if colouring and prepared.ab is not None:
            ab = _ab_over(prepared.ab, prepared.picture.size, part.size, box)
            rgb = coloured(rgb, ab, restoring.colour or 0.0)
        if fading and prepared.levels is not None:
            rgb = faded_back(rgb, prepared.levels, restoring.faded or 0.0)
        made = Image.fromarray(np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")
        if alpha is not None:
            made.putalpha(Image.fromarray(alpha, "L"))
        elif part.mode in ("L", "LA", "I", "I;16", "1", "F") and not colouring:
            made = made.convert("L")
        # A grey picture's own profile is for grey: coloured, it's in sRGB, as DDColor's are.
        if isinstance(profile, bytes) and (not colouring or _rgb(profile)):
            made.info["icc_profile"] = profile
        return made

    def whole(self, prepared: Prepared, *, stop: Callable[[], bool] = lambda: False) -> Image.Image:
        """The whole picture restored, laid on a band of rows at a time (so a huge scan never
        holds its colours as floats all at once)."""
        picture = prepared.picture
        restoring = prepared.restoring
        if not restoring.colour and not restoring.faded:
            return picture
        width, height = picture.size
        bands: list[Image.Image] = []
        for top in range(0, height, _ROWS):
            if stop():
                raise StoppedError
            bottom = min(top + _ROWS, height)
            band = picture.crop((0, top, width, bottom))
            band.info = dict(picture.info)
            bands.append(self.shown(prepared, band, (0, top, width, bottom)))
        mode = bands[0].mode
        made = Image.new(mode, (width, height))
        for at, band in zip(range(0, height, _ROWS), bands, strict=True):
            made.paste(band, (0, at))
        profile = bands[0].info.get("icc_profile")
        if isinstance(profile, bytes):
            made.info["icc_profile"] = profile
        return made

    # What each step does.

    def _scratches_filled(
        self,
        state: Image.Image,
        key: str,
        at: str,
        restoring: Restoring,
        stop: Callable[[], bool],
        keep: bool,
    ) -> tuple[Image.Image, float]:
        name = _made(at, restoring)
        with self._lock:
            kept = self._filled.get(name)
            if kept is not None:
                self._filled.move_to_end(name)
                return kept
        mask = self.mask(state, key, at, restoring, keep=keep)
        share = covers(mask)
        if share > MOST_MASK:
            raise RestoringError(too_much(share))
        if stop():
            raise StoppedError
        fill, _place = self._ai.eraser("best")  # LaMa: MI-GAN can't fill thin lines
        colours, alpha = _split(state)
        made = Image.fromarray(fill_scratches(colours, mask, fill, stop=stop), "RGB")
        if alpha is not None:
            made.putalpha(Image.fromarray(alpha, "L"))
        elif state.mode in ("L", "LA", "I", "I;16", "1", "F"):
            made = made.convert("L")
        profile = state.info.get("icc_profile")
        if isinstance(profile, bytes):
            made.info["icc_profile"] = profile
        if keep:
            with self._lock:
                self._filled[name] = (made, share)
                self._filled.move_to_end(name)
                while len(self._filled) > 1 and _pixels_kept(self._filled) > _FILLED:
                    self._filled.popitem(last=False)
        return made, share

    def _colours(self, picture: Image.Image, name: str, keep: bool) -> npt.NDArray[np.float32]:
        with self._lock:
            kept = self._ab.get(name)
            if kept is not None:
                self._ab.move_to_end(name)
                return kept
        colour, _place = self._ai.colourer()
        colours, _alpha = _split(picture)
        square = Image.fromarray(colours, "RGB").resize(
            (ERASE_SIZE, ERASE_SIZE), Image.Resampling.BILINEAR, reducing_gap=3.0
        )
        ab = colour(
            grey_input((np.asarray(square, np.float32) / np.float32(255)).astype(np.float32))
        )
        if keep:
            self._keep(self._ab, name, ab)
        return ab

    def _levels_of(self, picture: Image.Image, name: str, keep: bool) -> Levels:
        with self._lock:
            kept = self._levels.get(name)
            if kept is not None:
                return kept
        scale = min(1.0, _LEVELS / max(picture.size))
        size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
        small = picture if scale >= 1 else picture.resize(size, Image.Resampling.BOX)
        colours, alpha = _split(small)
        shown = None if alpha is None else alpha > 0
        levels = levels_of((colours / np.float32(255)).astype(np.float32), shown)
        if keep:
            self._keep(self._levels, name, levels)
        return levels

    # What's kept.

    def _keep[T](self, kept: OrderedDict[str, T], name: str, value: T) -> None:
        with self._lock:
            kept[name] = value
            kept.move_to_end(name)
            while len(kept) > _KEPT:
                kept.popitem(last=False)

    def _kept_mask(self, name: str, key: str, size: tuple[int, int]) -> Mask | None:
        shape = (size[1], size[0])
        with self._lock:
            found = self._found.get(name)
            if found is not None and found.shape == shape:
                self._found.move_to_end(name)
                return found
        path = self._path(name, key)
        try:
            with Image.open(path) as kept:
                found = np.asarray(kept.convert("L"))
            path.touch()
        except OSError:
            return None
        if found.shape != shape:
            return None  # found again
        self._keep(self._found, name, found)
        return found

    def _keep_mask(self, name: str, key: str, mask: Mask) -> None:
        self._keep(self._found, name, mask)
        path = self._path(name, key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_name(path.name + ".partial")
            Image.fromarray(mask, "L").save(partial, format="PNG", compress_level=1)
            partial.replace(path)
        except OSError as error:  # kept in memory all the same; it can be found again
            log.warning("Mado couldn't keep what it found in %s: %s", path.parent, error)

    def _path(self, name: str, key: str) -> Path:
        picture, _, version = key.rpartition("|")
        folder = hashlib.sha256(picture.encode()).hexdigest()[:16]
        return self._folder / folder / version / f"{name}.png"


def too_much(share: float) -> str:
    """Why a mask covering `share` of the picture isn't filled, in a sentence."""
    return (
        f"The mask covers {round(share * 100)}% of the picture: Mado fills scratches and dust, "
        "not most of a picture. Take some of the mask away, then fill it."
    )


def fill_scratches(
    pixels: Pixels,
    mask: Mask,
    fill: Fill,
    *,
    short: int = FILL_SHORT,
    stop: Callable[[], bool] = lambda: False,
) -> Pixels:
    """A picture (height × width × 3) with what the mask covers (at any size, 0 to 255) filled
    by LaMa: on a copy with its short side `short` long at most, in 512 squares stepping across
    what the mask holds, each filled from what's round it; then laid back only where the mask is,
    made the picture's size, with grain like the picture's so a fill doesn't show as smooth. The
    rest of the picture is never touched."""
    if not (mask >= 128).any():
        return pixels
    height, width = pixels.shape[:2]
    scale = min(1.0, short / min(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    small = (
        pixels
        if scale >= 1
        else np.asarray(Image.fromarray(pixels).resize(size, Image.Resampling.LANCZOS))
    )
    hole = np.asarray(Image.fromarray(mask, "L").resize(size, Image.Resampling.BILINEAR)) > 0
    drawn = _drawn(small, hole, fill, stop)
    strength = grain(pixels)
    out = np.empty_like(pixels)
    soft = Image.fromarray(mask, "L")
    drawn_image = Image.fromarray(drawn)
    for top in range(0, height, _ROWS):
        if stop():
            raise StoppedError
        bottom = min(top + _ROWS, height)
        rows = bottom - top
        box = (0.0, top * size[1] / height, float(size[0]), bottom * size[1] / height)
        back = np.asarray(
            drawn_image.resize((width, rows), Image.Resampling.BICUBIC, box=box), np.float32
        )
        mask_box = (
            0.0,
            top * mask.shape[0] / height,
            float(mask.shape[1]),
            bottom * mask.shape[0] / height,
        )
        weight = (
            np.asarray(
                soft.resize((width, rows), Image.Resampling.BILINEAR, box=mask_box), np.float32
            )[..., None]
            / 255
        )
        if strength > 0:
            noise = np.random.default_rng(zlib.crc32(f"{top},{width}".encode())).normal(
                0.0, strength, (rows, width, 1)
            )
            back += noise.astype(np.float32)
        band = pixels[top:bottom].astype(np.float32)
        out[top:bottom] = np.clip(band + weight * (back - band) + 0.5, 0, 255).astype(np.uint8)
    return out


def _drawn(
    small: Pixels, hole: npt.NDArray[np.bool_], fill: Fill, stop: Callable[[], bool]
) -> Pixels:
    """The copy with its hole filled, a 512 square at a time where the hole is: each square
    fills the part of the hole nearer its middle than any other's, so every pixel is drawn by the
    square that sees most round it."""
    height, width = small.shape[:2]
    side = ERASE_SIZE
    padded, held = small, hole
    if height < side or width < side:  # a small picture: mirrored out to a square
        pad = ((0, max(0, side - height)), (0, max(0, side - width)))
        padded = np.pad(small, (*pad, (0, 0)), mode="symmetric")
        held = np.pad(hole, pad)
    rows, columns = padded.shape[:2]
    filled = padded.copy()
    for y, top, bottom in _owned(rows, side):
        for x, left, right in _owned(columns, side):
            mine = held[top:bottom, left:right]
            if not mine.any():
                continue
            if stop():
                raise StoppedError
            square = np.ascontiguousarray(padded[y : y + side, x : x + side])
            inside = np.ascontiguousarray(held[y : y + side, x : x + side])
            made = fill(square, inside)
            here = made[top - y : bottom - y, left - x : right - x]
            kept = filled[top:bottom, left:right]
            kept[mine] = here[mine]
    return np.ascontiguousarray(filled[:height, :width])


def fill_squares(width: int, height: int, short: int = FILL_SHORT) -> int:
    """How many of LaMa's squares cover the copy a `width` by `height` picture is filled on: as
    many as it takes when its scratches cross all of it."""
    scale = min(1.0, short / max(1, min(width, height)))
    across, down = max(1, round(width * scale)), max(1, round(height * scale))
    return len(_owned(max(across, ERASE_SIZE), ERASE_SIZE)) * len(
        _owned(max(down, ERASE_SIZE), ERASE_SIZE)
    )


def _owned(length: int, side: int) -> list[tuple[int, int, int]]:
    """The squares along a side `length` long, `_STRIDE` apart, the last ending at its end: where
    each starts, and the part of the side nearer its middle than any other's (from, to)."""
    if length <= side:
        return [(0, 0, length)]
    starts = [*range(0, length - side, _STRIDE), length - side]
    middles = [start + side / 2 for start in starts]
    edges = [0, *(round((a + b) / 2) for a, b in itertools.pairwise(middles)), length]
    return [(start, edges[at], edges[at + 1]) for at, start in enumerate(starts)]


def _ab_over(
    ab: npt.NDArray[np.float32],
    picture: tuple[int, int],
    size: tuple[int, int],
    box: tuple[float, float, float, float],
) -> npt.NDArray[np.float32]:
    """DDColor's colours (at its square) over a part of the picture, `size` big: smoothly, as
    colour has little detail of its own."""
    width, height = picture
    rows, columns = ab.shape[1:]
    left, top, right, bottom = box
    square = (
        left * columns / width,
        top * rows / height,
        right * columns / width,
        bottom * rows / height,
    )
    channels = [
        np.asarray(Image.fromarray(ab[c], "F").resize(size, Image.Resampling.BILINEAR, box=square))
        for c in range(2)
    ]
    return np.stack(channels, axis=-1).astype(np.float32)


def _split(image: Image.Image) -> tuple[Pixels, npt.NDArray[np.uint8] | None]:
    """A picture's colours, what its see-through parts hide carried in from what shows, and its
    see-through parts apart (None for a solid picture)."""
    if image.mode in ("P", "PA", "La", "RGBa") or "transparency" in image.info:
        image = image.convert("RGBA")
    pixels: Pixels = np.asarray(image.convert("RGB"))
    if "A" not in image.getbands():
        return pixels, None
    alpha = np.asarray(image.getchannel("A"))
    return bled(pixels, alpha), alpha


def _rgb(profile: bytes) -> bool:
    """Whether a colour profile is for colour pictures (a grey picture's can't go on one
    coloured)."""
    return len(profile) >= 20 and profile[16:20] == b"RGB "


def _made(at: str, restoring: Restoring) -> str:
    """The name of the picture as its edits (`at`) and its scratches leave it: unfilled (none)
    is another picture from filled as found with nothing painted (no strokes), so what's
    worked out from one is never used for the other."""
    scratches = None if restoring.scratches is None else strokes_json(restoring.scratches)
    return _named(at, {"scratches": scratches})


def _named(at: str, what: object) -> str:
    text = json.dumps({"at": at, "what": what}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _pixels_kept(kept: OrderedDict[str, tuple[Image.Image, float]]) -> int:
    return sum(image.width * image.height for image, _share in kept.values())
