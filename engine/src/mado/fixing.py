"""Fixing a picture (docs/stack/fixes.md): JPEG blocks, darkness, noise and blur taken out, in that
order, at the picture's own size, before it grows.

The models run a tile at a time, as the upscaler does (mado/upscale.py, its answer the tile's own
size): FBCNN for JPEG blocks at Best, SCUNet for noise (and JPEG blocks at Fast, and the noise a
dark photo's brightening brings out), NAFNet for blur, its answer always held by the guard
(mado/core/fixes.py). Brightening and local contrast are numpy, a band of rows at a time, so a
huge picture needs little memory.

What the dark photo fix takes from the whole picture (how dark it is, local contrast's tables) is
measured once on a small copy of it (`Measure`), so a part made alone for a preview at full detail
comes out as the same part of the whole picture saved. A preview of all of it makes only the
brightening and local contrast (`light_only`): noise, blur and blocks are too small to judge on a
copy that size, and their models would take seconds to minutes over all of it.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from PIL import Image

from mado.ai import Ai, Timer
from mado.core.fixes import (
    DEBAND_GAIN,
    DEBAND_REACH,
    FBCNN,
    NAFNET,
    SCUNET,
    Clahe,
    Fixing,
    Quality,
    Stage,
    brightening,
    clahe_luts,
    contrasted,
    debanded,
    light_of,
    lightness_of,
    linear,
    luminance,
    stages,
    stops_of,
    toned,
)
from mado.core.framing import Box
from mado.upscale import Pixels, StoppedError, through_model

_SMALL = 1024  # the copy the whole picture is measured on, this many pixels on its longer side
_ROWS = 256  # rows brightened, or given local contrast, at a time
MARGIN = 96  # pixels of the picture round a part fixed alone, so its edges see what's beside

type Told = Callable[[int, int], None]  # done, of how many


@dataclass(frozen=True)
class Measure:
    """What the fixes take from the whole picture: its size, how much it's brightened by (its
    gain, and the white its tone curve rolls off into), and local contrast's tables, worked out
    on a small copy of it brightened."""

    width: int
    height: int
    gain: float
    white: float
    clahe: Clahe
    small: tuple[int, int]  # the small copy's size, across and down

    @property
    def stops(self) -> float:
        """How many stops brighter it's made: 0 for a picture that isn't dark."""
        return stops_of(self.gain)


def measure(image: Image.Image) -> Measure:
    """How dark a picture is, and its local contrast's tables, from a small copy of it (its
    see-through parts left out), made straight from it: a copy at full size first would take
    hundreds of megabytes of a big one."""
    scale = min(1.0, _SMALL / max(image.width, image.height))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    small = image if size == image.size else image.resize(size, Image.Resampling.BOX)
    rgb = np.asarray(small.convert("RGB"), np.float32) / 255.0
    lin = linear(rgb)
    light = luminance(lin)
    seen = light
    if "A" in small.getbands():
        shown = np.asarray(small.getchannel("A")) > 0
        seen = light[shown] if shown.any() else light
    gain, white = brightening(seen)
    brightened = toned(lin * gain, white)
    lightness = np.clip(np.rint(lightness_of(luminance(brightened))), 0, 255).astype(np.uint8)
    return Measure(image.width, image.height, gain, white, clahe_luts(lightness), small.size)


def fixed(
    pixels: Pixels,
    fixing: Fixing,
    measured: Measure | None,
    jpeg: Quality,
    ai: Ai,
    *,
    at: tuple[float, float] = (0.0, 0.0),
    step: float = 1.0,
    told: Told = lambda _done, _total: None,
    stop: Callable[[], bool] = lambda: False,
    timer: Timer | None = None,
    light_only: bool = False,
) -> Pixels:
    """`pixels` (a part of the picture, `at` its first pixel's place in it, a pixel `step` of the
    picture's: 1 at full size, more on a smaller copy) with the fixes made, JPEG blocks at `jpeg`
    (decided), a dark photo's as `measured` (None without the dark photo fix); `light_only`, only
    its brightening and local contrast. `told` hears as each tile or band is done; `stop` stops
    it before the next (StoppedError). Raises ModelError when a model can't run where it
    should."""
    made = stages(fixing, jpeg, measured.stops if measured is not None else 0.0)
    if light_only:
        made = [stage for stage in made if stage.model is None]
    if not made:
        return pixels
    height, width = pixels.shape[:2]
    weights = [_weight(stage, width, height) for stage in made]
    total = sum(weights)
    done = 0

    def heard(within: int, of: int, weight: int) -> None:
        told(done + round(weight * within / max(of, 1)), total)

    out = pixels
    for stage, weight in zip(made, weights, strict=True):
        if stop():
            raise StoppedError
        match stage.kind:
            case "brighten" if measured is not None:
                out = _brightened(out, measured, stop)
            case "contrast" if measured is not None:
                out = _contrasted(out, measured, at, step, stage.amount, stop)
            case "brighten" | "contrast":  # never: only a dark photo's, which is measured
                pass
            case "blocks" | "noise" | "blur":
                out = _through(
                    out,
                    stage,
                    ai,
                    timer,
                    told=lambda within, of, weight=weight: heard(within, of, weight),
                    stop=stop,
                )
        done += weight
        told(done, total)
    return out


def _weight(stage: Stage, width: int, height: int) -> int:
    """A stage's share of the work: a model's tiles, or a numpy pass as about a tile's worth
    of a big picture."""
    if stage.model is None:
        return max(1, width * height // 4_000_000)
    return max(1, width * height // (300 * 300))


def _through(
    pixels: Pixels,
    stage: Stage,
    ai: Ai,
    timer: Timer | None,
    *,
    told: Told,
    stop: Callable[[], bool],
) -> Pixels:
    """A model's stage, a tile at a time: FBCNN told how hard, SCUNet's and NAFNet's answers
    kept as strongly as asked, NAFNet's held by the guard."""
    height, width = pixels.shape[:2]
    if stage.model is FBCNN:
        tiling = ai.fixer(FBCNN, timer, qf=stage.amount)
    elif stage.model is NAFNET:
        tiling = ai.fixer(NAFNET, timer, strength=stage.amount, guard=True)
    else:
        tiling = ai.fixer(SCUNET, timer, strength=stage.amount)
    return through_model(
        pixels, Box(0, 0, width, height), (width, height), tiling, told=told, stop=stop
    )


def _brightened(pixels: Pixels, measured: Measure, stop: Callable[[], bool]) -> Pixels:
    """Brightened in linear light by the picture's gain, then its tone curve, a band of rows at a
    time. Brightened four times or more, its own 8-bit steps are smoothed first where it's flat,
    so a smooth dark sky doesn't band (each band read with the rows round it, so it's smoothed as
    the whole picture is)."""
    height = pixels.shape[0]
    out = np.empty_like(pixels)
    smooth = measured.gain >= DEBAND_GAIN
    for top in range(0, height, _ROWS):
        if stop():
            raise StoppedError
        bottom = min(top + _ROWS, height)
        if smooth:
            above, below = max(top - DEBAND_REACH, 0), min(bottom + DEBAND_REACH, height)
            read = debanded(pixels[above:below].astype(np.float32))
            band = read[top - above : bottom - above]
        else:
            band = pixels[top:bottom].astype(np.float32)
        lin = linear(np.clip(band / 255.0, 0.0, 1.0)) * measured.gain
        made = linear(toned(lin, measured.white), back=True)
        out[top:bottom] = np.clip(np.rint(made * 255.0), 0, 255).astype(np.uint8)
    return out


def _contrasted(
    pixels: Pixels,
    measured: Measure,
    at: tuple[float, float],
    step: float,
    amount: float,
    stop: Callable[[], bool],
) -> Pixels:
    """Local contrast (CLAHE) on lightness, `amount` of it, each pixel's change made in linear
    light so its colour stays; the tables are the whole picture's, so a part is lifted as the
    whole is."""
    height = pixels.shape[0]
    out = np.empty_like(pixels)
    across = measured.small[0] / measured.width
    down = measured.small[1] / measured.height
    for top in range(0, height, _ROWS):
        if stop():
            raise StoppedError
        band = pixels[top : top + _ROWS].astype(np.float32) / 255.0
        lin = linear(band)
        light = luminance(lin)
        lightness = lightness_of(light)
        where = (at[0] * across, (at[1] + top * step) * down, step * across, step * down)
        lifted = contrasted(lightness, measured.clahe, where)
        mixed = (lightness + np.float32(amount) * (lifted - lightness)).astype(np.float32)
        ratio = (light_of(mixed) / np.maximum(light, 1e-6)).astype(np.float32)
        made = linear(np.clip(lin * ratio[..., None], 0.0, 1.0).astype(np.float32), back=True)
        out[top : top + _ROWS] = np.clip(np.rint(made * 255.0), 0, 255).astype(np.uint8)
    return out
