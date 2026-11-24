"""Depth, by its rules: how near each part of a picture is, as Depth Anything V2 Small reads it,
and the three tools made from it: portrait blur (a lens's depth of field, from a point in focus),
fog (haze that thickens with distance) and tilt-shift (a band in focus and blur growing away from
it, as a miniature looks). Each tool's settings and words, and the maths that isn't the model's:
the square it reads, its numbers made 0 to 1, a flat picture told apart, the circle each point
blurs to, the layers a lens blur is made in, the fog's light and the band. Pure: numpy only.

Nearness: the model gives each point a number that grows the nearer it is (inverse depth, at a
scale of its own); Mado makes it 0 for the farthest to 1 for the nearest, each picture its own.

A lens blur is made in layers by nearness, nearest first (docs/stack/depth.md): each layer
blurred by its own circle, round highlights boosted so they bloom into discs, what's behind a
nearer layer carried on under it (so the background never takes the subject's colour), and a
layer in focus left to the picture itself, joined at full size where it's sharp.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import numpy.typing as npt

from mado.core.masks import box

type Floats = npt.NDArray[np.float32]
type Quality = Literal["fast", "best"]
type Kind = Literal["portrait", "fog", "tilt"]

KINDS: tuple[Kind, ...] = ("portrait", "fog", "tilt")
READ = 518  # the square the model reads a picture at, the whole of it squeezed (as SAM does)
# A picture is flat (a scan, a screenshot: no depth to speak of) when the model's numbers spread
# little for their size (its 2nd to 98th percentile, over their mean) and have no edges where
# nearness jumps (its 99th percentile of change from pixel to pixel, over their mean): measured on
# made-up pages, screens and scenes (docs/stack/depth.md). A subject in front of a wall has an edge.
FLAT_SPREAD = 1.2
FLAT_EDGES = 0.03
_EDGE_SHARE = 99.5  # the percentile of change from pixel to pixel an edge is told by
APERTURES = (1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0)  # a lens's stops, widest first
APERTURE = 2.8  # portrait blur starts here
LENS = 0.03  # at f/1.4, a point a whole nearness from the focus blurs to a disc this much of the
# picture's shorter side out from its middle (its radius)
TILT = 0.02  # tilt-shift's blur at full strength, at the band's farthest: a radius, of the same
FOG = 3.2  # fog's thickness at full density: the farthest point shows exp(-FOG) of itself
SHARP = 0.6  # a circle smaller than this (pixels across the copy blurred) is in focus
_SOFT = 1.0  # and in focus fades out over this many pixels more
WORK = 1024  # a blur is worked out on a copy this many pixels on its longer side
_LAYERS = 12  # at most, nearest first
_STEP = 1.6  # pixels between neighbouring layers' circles, at most
_BOOST = 2.0  # how much brighter the brightest places get before they're blurred, so they bloom
_BRIGHT = (0.9, 0.99)  # brightness (0 to 1, as stored) where the boost starts and is whole
_BIG = 5.0  # a circle this big (pixels) or more is blurred as a disc on a smaller copy
_LIFT = 0.12  # tilt-shift lifts its colours this much, as a miniature's paint
_SAME = 0.15  # nearer or farther than the subject by this, and fading over as much more, isn't it
_FIRM = (0.3, 0.7)  # a subject's mask is all of it above the second and none of it below the first
_PEAK = (0.25, 0.5)  # a bright place blooms whole while this much of what's round it is bright,
# none from the second
_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


class DepthError(ValueError):
    """A depth step Mado can't make as it's kept, with a sentence saying why."""


@dataclass(frozen=True)
class Portrait:
    """Portrait blur: in focus at a point (fractions across and down the picture; None, its
    subject), blurred as a lens at `aperture` would, the subject's edges found at Fast or Best
    (None: as this PC suits)."""

    focus: tuple[float, float] | None = None
    aperture: float = APERTURE
    quality: Quality | None = None


@dataclass(frozen=True)
class Fog:
    """Haze, thicker the farther: `density` 0 to 1, in a colour (None: the picture's own, the
    light of its farthest places)."""

    density: float = 0.5
    colour: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class TiltShift:
    """A band kept in focus (its middle and height, fractions of the picture's height) and blur
    growing away from it, at `strength` 0 to 1."""

    centre: float = 0.55
    height: float = 0.2
    strength: float = 0.6


@dataclass(frozen=True)
class Depthing:
    """The depth step: each tool off (None) or on with its settings."""

    portrait: Portrait | None = None
    fog: Fog | None = None
    tilt: TiltShift | None = None

    @property
    def on(self) -> tuple[Kind, ...]:
        """The tools that are on, in the Depth tab's order."""
        return tuple(kind for kind in KINDS if getattr(self, kind) is not None)


# The step, as a recipe keeps it, and its words.


def depthing_from(data: object) -> Depthing | None:
    """A depth step as a recipe keeps it (JSON: each tool null or its settings), None with none
    on. Raises DepthError for one that isn't a depth step."""
    if data is None:
        return None
    if not isinstance(data, dict):
        raise DepthError(_UNREADABLE)
    kept = cast("dict[str, object]", data)
    portrait = _portrait(kept.get("portrait"))
    fog = _fog(kept.get("fog"))
    tilt = _tilt(kept.get("tilt"))
    found = Depthing(portrait, fog, tilt)
    return found if found.on else None


def _portrait(value: object) -> Portrait | None:
    if value is None:
        return None
    kept = _dict(value)
    focus = kept.get("focus")
    point: tuple[float, float] | None = None
    if focus is not None:
        if not isinstance(focus, list) or len(cast("list[object]", focus)) != 2:
            raise DepthError(_UNREADABLE)
        x, y = cast("list[object]", focus)
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            raise DepthError(_UNREADABLE)
        point = (_fraction(x), _fraction(y))
    aperture = kept.get("aperture", APERTURE)
    if not isinstance(aperture, int | float):
        raise DepthError(_UNREADABLE)
    quality = kept.get("quality")
    return Portrait(
        point,
        min(max(float(aperture), APERTURES[0]), APERTURES[-1]),
        "fast" if quality == "fast" else "best" if quality == "best" else None,
    )


def _fog(value: object) -> Fog | None:
    if value is None:
        return None
    kept = _dict(value)
    density = kept.get("density", 0.5)
    if not isinstance(density, int | float):
        raise DepthError(_UNREADABLE)
    return Fog(_fraction(density), _colour(kept.get("colour")))


def _tilt(value: object) -> TiltShift | None:
    if value is None:
        return None
    kept = _dict(value)
    numbers = [kept.get(name, default) for name, default in _TILT_DEFAULTS]
    if not all(isinstance(each, int | float) for each in numbers):
        raise DepthError(_UNREADABLE)
    centre, height, strength = (float(cast("float", each)) for each in numbers)
    return TiltShift(_fraction(centre), min(max(height, 0.02), 0.9), _fraction(strength))


_TILT_DEFAULTS = (("centre", 0.55), ("height", 0.2), ("strength", 0.6))


def _dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DepthError(_UNREADABLE)
    return cast("dict[str, object]", value)


def _fraction(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _colour(value: object) -> tuple[int, int, int] | None:
    """A colour as "#rrggbb"; None (the picture's own) for anything else."""
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
        except ValueError:
            return None
    return None


def depthing_json(depthing: Depthing | None) -> dict[str, object] | None:
    """A depth step as a recipe keeps it."""
    if depthing is None:
        return None
    portrait, fog, tilt = depthing.portrait, depthing.fog, depthing.tilt
    return {
        "portrait": None
        if portrait is None
        else {
            "focus": list(portrait.focus) if portrait.focus else None,
            "aperture": portrait.aperture,
            "quality": portrait.quality,
        },
        "fog": None
        if fog is None
        else {
            "density": fog.density,
            "colour": "#{:02x}{:02x}{:02x}".format(*fog.colour) if fog.colour else None,
        },
        "tilt": None
        if tilt is None
        else {"centre": tilt.centre, "height": tilt.height, "strength": tilt.strength},
    }


def stop_words(aperture: float) -> str:
    """An aperture as a lens says it: "f/2.8", "f/2", "f/11"."""
    return f"f/{aperture:g}"


def phrase(depthing: Depthing | None) -> str | None:
    """The depth tools as History and Save say them, after "with": "portrait blur at f/2.8,
    fog and tilt-shift"."""
    if depthing is None or not depthing.on:
        return None
    said: list[str] = []
    if depthing.portrait is not None:
        said.append(f"portrait blur at {stop_words(depthing.portrait.aperture)}")
    if depthing.fog is not None:
        said.append("fog")
    if depthing.tilt is not None:
        said.append("tilt-shift")
    return said[0] if len(said) == 1 else f"{', '.join(said[:-1])} and {said[-1]}"


def label(depthing: Depthing | None) -> str | None:
    """What a new picture's name says of the depth tools: "Portrait blur", "Fog", "Tilt-shift",
    or "Depth" for more than one."""
    if depthing is None or not depthing.on:
        return None
    if len(depthing.on) > 1:
        return "Depth"
    only = next(iter(depthing.on))
    return {"portrait": "Portrait blur", "fog": "Fog", "tilt": "Tilt-shift"}[only]


def detail(depthing: Depthing) -> str:
    """The depth tools as a batch's steps say them: "portrait blur at f/2.8 on each subject,
    fog at 50%, tilt-shift at 60%"."""
    said: list[str] = []
    if depthing.portrait is not None:
        said.append(f"portrait blur at {stop_words(depthing.portrait.aperture)} on each subject")
    if depthing.fog is not None:
        said.append(f"fog at {round(depthing.fog.density * 100)}%")
    if depthing.tilt is not None:
        said.append(f"tilt-shift at {round(depthing.tilt.strength * 100)}%")
    text = ", ".join(said)
    return text[:1].upper() + text[1:]


_UNREADABLE = "Mado can't read that depth step: turn the depth tools off and choose them again."


# What the model reads, and what it gives.


def readable(pixels: npt.NDArray[np.uint8]) -> Floats:
    """A picture's colours (READ square, RGB) as the model takes them: 0 to 1, less ImageNet's
    mean, over its spread, as 1 × 3 × READ × READ."""
    values = (pixels.astype(np.float32) / 255.0 - _MEAN) / _STD
    return np.ascontiguousarray(values.transpose(2, 0, 1)[None], dtype=np.float32)


_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


@dataclass(frozen=True)
class Read:
    """What the model read of a picture: its nearness, 0 (the farthest) to 1 (the nearest), at
    the model's square; and how deep the picture is: how much the model's own numbers spread for
    their size, and how sharply they jump at its edges."""

    near: Floats
    spread: float
    edges: float

    @property
    def flat(self) -> bool:
        """A flat picture (a scan, a screenshot): no depth to speak of."""
        return flat_reading(self.spread, self.edges)


def flat_reading(spread: float, edges: float) -> bool:
    """Whether the model's numbers say a picture is flat: they spread little and never jump."""
    return spread < FLAT_SPREAD and edges < FLAT_EDGES


def nearness(raw: Floats) -> Read:
    """The model's numbers (bigger is nearer, at its own scale) made 0 to 1 by the picture's own
    2nd and 98th percentiles, and how deep it is by them (`Read`)."""
    low, high = (float(v) for v in np.percentile(raw, [2, 98]))
    mean = max(float(raw.mean()), 1e-6)
    rows, columns = np.gradient(raw.astype(np.float32))
    edges = float(np.percentile(np.hypot(rows, columns), _EDGE_SHARE)) / mean
    if high - low < 1e-6:
        return Read(np.zeros_like(raw, dtype=np.float32), 0.0, 0.0)
    near = np.clip((raw - low) / (high - low), 0.0, 1.0).astype(np.float32)
    return Read(near, (high - low) / mean, edges)


def placed(
    near: Floats,
    canvas: tuple[float, float, float, float],
    picture: tuple[int, int],
    size: tuple[int, int],
) -> Floats:
    """The nearness of a whole picture (`picture` its width and height; the model's square, or
    any size) on what's made of it, `size` (width, height) big: `canvas` is the part of the
    picture made (x, y, width, height in its pixels: a crop, or more than all of it when its
    edges were extended, where what's at its edge carries on)."""
    x, y, across, down = canvas
    width, height = size
    rows, columns = near.shape
    u = (x + (np.arange(width, dtype=np.float32) + 0.5) * across / width) / picture[0]
    v = (y + (np.arange(height, dtype=np.float32) + 0.5) * down / height) / picture[1]
    xs: Floats = np.clip(u * columns - 0.5, 0, columns - 1).astype(np.float32)
    ys: Floats = np.clip(v * rows - 0.5, 0, rows - 1).astype(np.float32)
    return lerp(near, ys, xs)


def on_canvas(
    point: tuple[float, float],
    canvas: tuple[float, float, float, float],
    picture: tuple[int, int],
) -> tuple[float, float]:
    """A point on the picture (fractions across and down) as fractions of what's made of it
    (`canvas`, as `placed` takes it), held inside it."""
    x, y, across, down = canvas
    u = (point[0] * picture[0] - x) / max(across, 1e-6)
    v = (point[1] * picture[1] - y) / max(down, 1e-6)
    return _fraction(u), _fraction(v)


def middle_of(mask: Floats) -> tuple[float, float]:
    """Where a mask's weight is (0 to 1 each), as fractions across and down; the middle with
    none."""
    height, width = mask.shape
    total = float(mask.sum())
    if total <= 0:
        return 0.5, 0.5
    columns: Floats = mask.sum(axis=0, dtype=np.float32)
    rows: Floats = mask.sum(axis=1, dtype=np.float32)
    across = float(np.dot(columns, np.arange(width, dtype=np.float32))) / total
    down = float(np.dot(rows, np.arange(height, dtype=np.float32))) / total
    return (across + 0.5) / width, (down + 0.5) / height


def at_point(near: Floats, point: tuple[float, float], reach: float = 0.01) -> float:
    """How near the picture is at a point (fractions across and down): the middle of its
    neighbours `reach` of the picture out each way, so a click a pixel off a thin edge holds."""
    height, width = near.shape
    x, y = point[0] * (width - 1), point[1] * (height - 1)
    rx, ry = max(1, round(reach * width)), max(1, round(reach * height))
    left, right = max(int(x) - rx, 0), min(int(x) + rx + 1, width)
    top, bottom = max(int(y) - ry, 0), min(int(y) + ry + 1, height)
    return float(np.median(near[top:bottom, left:right]))


def subject_near(near: Floats, mask: Floats) -> float | None:
    """How near the subject is (`mask`, 0 to 1, the nearness's size): the middle of what's
    surely it; None where there's no subject to speak of."""
    sure = mask > 0.6
    if np.count_nonzero(sure) < max(16, sure.size // 1000):
        return None
    return float(np.median(near[sure]))


def firm(mask: Floats) -> Floats:
    """A subject's mask (0 to 1) made firm: a cut-out model's fades over a few pixels each side
    of an edge the picture draws crisply, and the lens would blur that fringe, so what's mostly
    the subject is all of it and what's mostly not none of it; hair's in-between stays between."""
    low, high = _FIRM
    return np.clip((mask - low) / (high - low), 0.0, 1.0).astype(np.float32)


def subject_only(near: Floats, mask: Floats, at: float) -> Floats:
    """The subject's mask with what isn't as near as it taken out: a cut-out model also picks
    things far away (a sun in the sky), which mustn't be kept sharp or out of the fog with it."""
    agree = np.clip(1.0 - (np.abs(near - at) - _SAME) / _SAME, 0.0, 1.0)
    return (mask * agree).astype(np.float32)


def behind_subject(near: Floats, mask: Floats, reach: int = 6) -> Floats:
    """The nearness of what's behind the subject (`mask`, 0 to 1): round its edge, what's beyond
    it carried in, never nearer than the model said, so the model's soft edge round the subject
    never smears what's behind it; far into it, where nothing beyond reaches, as the model said."""
    outside = ((1.0 - mask) ** 2).astype(np.float32)
    weight = box(outside, reach)
    carried = box((near * outside).astype(np.float32), reach) / np.maximum(weight, 1e-3)
    return np.where(weight > 1e-3, np.minimum(near, carried), near).astype(np.float32)


def with_subject(behind: Floats, mask: Floats, at: float) -> Floats:
    """The nearness with the subject's edges made the mask's (crisp where the picture is, soft in
    hair): the subject at its own nearness `at`, and what's behind it round it."""
    return (mask * at + (1.0 - mask) * behind).astype(np.float32)


# Portrait blur.


def f_radius(aperture: float, short: int) -> float:
    """How far (pixels, a radius) a point a whole nearness from the focus blurs at `aperture` on
    a picture `short` pixels on its shorter side."""
    return LENS * (APERTURES[0] / aperture) * short


def layers(focus: float, most: float) -> list[tuple[float, float]]:
    """The layers a lens blur is made in, nearest first: each one's nearness and the circle (a
    radius, in pixels) it blurs to, `most` a whole nearness from the focus. One is exactly at the
    focus, so what's in focus is wholly in it; the rest close enough that neighbours' circles
    differ by `_STEP` at most, and no more than `_LAYERS`."""
    reach = most * max(focus, 1 - focus)
    count = int(np.clip(np.ceil(reach / _STEP) + 1, 3, _LAYERS))
    centres = {round(float(near), 6) for near in np.linspace(1.0, 0.0, count)}
    gap = 1.0 / (count - 1)
    centres = {near for near in centres if abs(near - focus) > gap / 3}
    centres.add(round(focus, 6))
    return [(near, abs(near - focus) * most) for near in sorted(centres, reverse=True)]


def membership(near: Floats, centres: Sequence[float], at: int) -> Floats:
    """How much of each point belongs to layer `at` (of layers at `centres`, nearest first): a
    tent between its neighbours, so every point's shares add up to 1 (past the first and last,
    all theirs)."""
    rising = list(reversed(centres))  # farthest first, as the tent's steps rise
    return tent(near, rising, len(centres) - 1 - at)


@dataclass(frozen=True)
class Blurred:
    """A lens blur worked out on a copy: what the blur shows beyond what's in focus (`behind`,
    linear light), the colour of what's blurred in front of each point's own layer (`front`), and
    how much of each point that covers (`nearer`): joined with the picture at its own size by
    `joined`."""

    behind: Floats  # height × width × 3, linear light
    front: Floats  # height × width × 3, linear light
    nearer: Floats  # height × width, 0 to 1


def lens_blur(lin: Floats, near: Floats, focus: float, most: float) -> Blurred:
    """A picture (linear light, height × width × 3) blurred as a lens focused at nearness
    `focus`, a point a whole nearness away blurring `most` pixels out (a radius on this copy):
    in layers, nearest first, each blurred by its own circle, its brightest places boosted to
    bloom, what's behind a nearer layer carried on under it. A layer in focus isn't blurred: the
    picture itself shows there, joined at full size (`joined`). Each layer is worked out only
    where it is, and as far round it as it blurs."""
    height, width = near.shape
    plan = layers(focus, most)
    centres = [centre for centre, _ in plan]
    acc = np.zeros((height, width, 3), np.float32)
    cover = np.zeros((height, width), np.float32)
    front = np.zeros((height, width, 3), np.float32)
    nearer = np.zeros((height, width), np.float32)
    solid = np.zeros((height, width), np.float32)  # the layers in front, as shares of each point
    light = bright(lin, most / 2)
    for at, (_centre, radius) in enumerate(plan):
        share = membership(near, centres, at)
        found = _bounds(share, 0)
        if found is None:
            continue
        top, bottom, left, right = found
        # What's blurred in front of this point's own layer: its colour and how much it covers.
        here = (slice(top, bottom), slice(left, right))
        front[here] += share[here][..., None] * acc[here]
        nearer[here] += share[here] * cover[here]
        if radius < SHARP:  # in focus: the picture itself shows here
            solid[here] += share[here]
            continue
        reach = int(np.ceil(radius)) + 2
        top, left = max(top - reach, 0), max(left - reach, 0)
        bottom, right = min(bottom + reach, height), min(right + reach, width)
        area = (slice(top, bottom), slice(left, right))
        mine, seen = share[area], lin[area]
        boost = 1.0 + _BOOST * min(1.0, radius / 6.0) * light[area]
        packed = np.concatenate(
            [seen * (boost * mine)[..., None], mine[..., None], (mine + solid[area])[..., None]],
            axis=-1,
        ).astype(np.float32)
        blurred = spread(packed, radius)
        weight = blurred[..., 3]
        held = np.clip(blurred[..., 4], 0.0, 1.0)
        own = np.where(
            (weight > 1e-3)[..., None], blurred[..., :3] / np.maximum(weight, 1e-3)[..., None], seen
        )
        open_ = 1.0 - cover[area]
        acc[area] += (open_ * held)[..., None] * own
        cover[area] += open_ * held
        solid[area] += mine
    behind = acc + (1.0 - cover)[..., None] * lin  # nothing blurred reaches: the picture itself
    shown_front = np.where(
        (nearer > 1e-3)[..., None], front / np.maximum(nearer, 1e-3)[..., None], behind
    )
    return Blurred(behind.astype(np.float32), shown_front.astype(np.float32), nearer)


def _bounds(values: Floats, margin: int) -> tuple[int, int, int, int] | None:
    """The rows and columns (top, bottom, left, right; ends past the last) where any value isn't
    0, `margin` more round them; None when all are."""
    rows = np.flatnonzero(values.any(axis=1))
    if rows.size == 0:
        return None
    columns = np.flatnonzero(values.any(axis=0))
    height, width = values.shape
    return (
        max(int(rows[0]) - margin, 0),
        min(int(rows[-1]) + 1 + margin, height),
        max(int(columns[0]) - margin, 0),
        min(int(columns[-1]) + 1 + margin, width),
    )


def in_focus(radius: Floats) -> Floats:
    """How sharp each point stays, by the circle it blurs to (pixels on the copy blurred): whole
    under `SHARP`, fading out over `_SOFT` more."""
    return np.clip(1.0 - (radius - SHARP) / _SOFT, 0.0, 1.0).astype(np.float32)


def joined(picture: Floats, sharp: Floats, behind: Floats, front: Floats, nearer: Floats) -> Floats:
    """The picture (0 to 1 as stored, its own size) with a lens blur worked out on a copy (each
    part made this size and turned back from linear light): where it's in focus (`sharp`) the
    picture itself, under what's blurred in front of it; elsewhere the blur."""
    keep = sharp * (1.0 - nearer)
    seen = sharp[..., None] * front + (1.0 - sharp)[..., None] * behind
    return (keep[..., None] * picture + (1.0 - keep)[..., None] * seen).astype(np.float32)


def bright(lin: Floats, reach: float) -> Floats:
    """Where a picture is bright enough to bloom when blurred `reach` pixels out, 0 to 1: bright,
    and small beside the blur (a lamp, the sun, a glint), as a lens draws those as discs of light
    while blur only dims them; a pale sky or a white wall, bright all round, isn't."""
    stored = linear_to_stored(np.clip(lin @ _LUMA, 0.0, 1.0))
    low, high = _BRIGHT
    t = np.clip((stored - low) / (high - low), 0.0, 1.0)
    lit = (stored > low).astype(np.float32)
    round_it = box(lit, max(2, round(reach)))
    small = np.clip(1.0 - (round_it - _PEAK[0]) / (_PEAK[1] - _PEAK[0]), 0.0, 1.0)
    return (t * t * (3 - 2 * t) * small).astype(np.float32)


# Blurring by a disc, as a lens does.


def disc(radius: float) -> Floats:
    """A lens's blur: a disc `radius` pixels out from its middle, its edge smooth to a pixel."""
    reach = max(1, int(np.ceil(radius)))
    ys, xs = np.mgrid[-reach : reach + 1, -reach : reach + 1].astype(np.float32)
    shape = np.clip(radius + 0.5 - np.hypot(xs, ys), 0.0, 1.0)
    return (shape / shape.sum()).astype(np.float32)


def spread(values: Floats, radius: float) -> Floats:
    """Values (height × width, or × channels) blurred as a lens blurs: by a disc `radius` pixels
    out. A small one is two boxes (a disc and two boxes look the same that small); a big one is a
    disc on a copy made smaller first, so it's about as quick however big, and made this size
    again."""
    if radius < 0.5:
        return values.astype(np.float32, copy=True)
    if radius < _BIG:
        half = max(1, round(radius / 1.6))
        return box(box(values, half), half)
    step = max(1, int(radius // 3))
    small = shrunk(values, step)
    blurred = convolved(small, disc(radius / step))
    return grown(blurred, step, values.shape[:2])


def shrunk(values: Floats, step: int) -> Floats:
    """Values made `step` times smaller each way by the mean of each square (the edges repeated
    to fill the last ones)."""
    if step <= 1:
        return values.astype(np.float32, copy=True)
    height, width = values.shape[:2]
    rows, columns = -(-height // step), -(-width // step)
    pad = [(0, rows * step - height), (0, columns * step - width)] + [(0, 0)] * (values.ndim - 2)
    padded = np.pad(values, pad, mode="edge")
    shape = (rows, step, columns, step, *values.shape[2:])
    return padded.reshape(shape).mean(axis=(1, 3), dtype=np.float32)


def grown(values: Floats, step: int, size: tuple[int, int]) -> Floats:
    """Values made from `shrunk` back to `size` (height, width), smoothly (each output pixel
    between the four nearest it, as Pillow's bilinear)."""
    if step <= 1:
        return values[: size[0], : size[1]].astype(np.float32, copy=True)
    height, width = size
    down = (np.arange(height, dtype=np.float32) + 0.5) / step - 0.5
    across = (np.arange(width, dtype=np.float32) + 0.5) / step - 0.5
    ys: Floats = np.clip(down, 0, values.shape[0] - 1).astype(np.float32)
    xs: Floats = np.clip(across, 0, values.shape[1] - 1).astype(np.float32)
    return lerp(values, ys, xs)


def lerp(values: Floats, ys: Floats, xs: Floats) -> Floats:
    """Values sampled on a grid of rows `ys` and columns `xs` (fractional places), each between
    the four nearest."""
    y0 = np.floor(ys).astype(np.int64)
    x0 = np.floor(xs).astype(np.int64)
    y1 = np.minimum(y0 + 1, values.shape[0] - 1)
    x1 = np.minimum(x0 + 1, values.shape[1] - 1)
    fy = (ys - y0).astype(np.float32)
    fx = (xs - x0).astype(np.float32)
    if values.ndim == 3:
        fy, fx = fy[:, None, None], fx[None, :, None]
    else:
        fy, fx = fy[:, None], fx[None, :]
    top = values[y0][:, x0] * (1 - fx) + values[y0][:, x1] * fx
    bottom = values[y1][:, x0] * (1 - fx) + values[y1][:, x1] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.float32)


def convolved(values: Floats, kernel: Floats) -> Floats:
    """Values spread by a kernel (its middle at its middle), by the fast Fourier transform, the
    edges mirrored so nothing wraps round."""
    reach = kernel.shape[0] // 2
    pad = [(reach, reach), (reach, reach)] + [(0, 0)] * (values.ndim - 2)
    padded = np.pad(values, pad, mode="reflect" if min(values.shape[:2]) > reach else "edge")
    height, width = padded.shape[:2]
    placed = np.zeros((height, width), np.float32)
    placed[: kernel.shape[0], : kernel.shape[1]] = kernel
    placed = np.roll(placed, (-reach, -reach), axis=(0, 1))
    shape = np.fft.rfft2(placed)
    if values.ndim == 3:
        shape = shape[..., None]
    spread_ = np.fft.irfft2(
        np.fft.rfft2(padded, axes=(0, 1)) * shape, s=(height, width), axes=(0, 1)
    )
    return spread_[reach : reach + values.shape[0], reach : reach + values.shape[1]].astype(
        np.float32
    )


# Light: a picture's stored values in linear light and back, by tables (quick at any size).

_TO_LINEAR = np.where(
    np.arange(256) / 255.0 <= 0.04045,
    np.arange(256) / 255.0 / 12.92,
    ((np.arange(256) / 255.0 + 0.055) / 1.055) ** 2.4,
).astype(np.float32)
_FROM = 4096  # the table back from linear light has this many steps
_TO_STORED = np.where(
    np.linspace(0, 1, _FROM) <= 0.0031308,
    12.92 * np.linspace(0, 1, _FROM),
    1.055 * np.linspace(0, 1, _FROM) ** (1 / 2.4) - 0.055,
).astype(np.float32)


def to_linear(pixels: npt.NDArray[np.uint8]) -> Floats:
    """8-bit stored values (sRGB's curve; Display P3 has the same) in linear light, 0 to 1."""
    return _TO_LINEAR[pixels]


def linear_to_stored(lin: Floats) -> Floats:
    """Linear light (0 to 1) as stored values, 0 to 1."""
    at = np.clip(lin, 0.0, 1.0) * (_FROM - 1)
    return _TO_STORED[(at + 0.5).astype(np.int32)]


def to_bytes(stored: Floats) -> npt.NDArray[np.uint8]:
    return (np.clip(stored, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


# Fog.


def fog_clear(near: Floats, density: float) -> Floats:
    """How much of each point shows through the fog (`density` 0 to 1): all of the nearest, less
    and less the farther, as haze thickens with distance (by the square of how far: what's near
    the camera stays clear)."""
    far = 1.0 - near
    return np.exp(-FOG * density * far * far).astype(np.float32)


def own_haze(lin: Floats, near: Floats) -> Floats:
    """The picture's own haze: the light of its farthest places (its farthest twentieth), made
    paler, as distance makes a sky or a far hill; linear light, 3 values."""
    cut = float(np.percentile(near, 5))
    far = lin[near <= cut + 1e-6]
    seen = far.mean(axis=0) if far.size else lin.reshape(-1, 3).mean(axis=0)
    return (0.55 * seen + 0.45 * np.float32(0.85)).astype(np.float32)


def fogged(lin: Floats, near: Floats, density: float, haze: Floats) -> Floats:
    """A picture (linear light) in fog of `density`, of light `haze` (linear, 3 values)."""
    clear = fog_clear(near, density)[..., None]
    return (lin * clear + haze * (1.0 - clear)).astype(np.float32)


# Tilt-shift.


def tilt_radius(
    rows: int,
    columns: int,
    tilt: TiltShift,
    short: int,
    span: tuple[float, float] = (0.0, 1.0),
) -> Floats:
    """The circle (a radius, pixels on a picture `short` on its shorter side) each row of a
    `rows`-high picture blurs to: none inside the band, growing smoothly away from it to its
    most at the farther of the picture's top and foot. Every column alike. The band is placed
    on the whole picture, as it's dragged; the rows are `span` of its height (where they start
    and how much of it, as `span_of` gives), so a crop keeps it where it was."""
    top, part = span
    y = top + (np.arange(rows, dtype=np.float32) + 0.5) / rows * part
    half = tilt.height / 2
    reach = max(tilt.centre - half, 1.0 - (tilt.centre + half), 1e-3)
    away = np.clip((np.abs(y - tilt.centre) - half) / reach, 0.0, 1.0)
    most = TILT * tilt.strength * short
    return np.broadcast_to((away**1.5 * most)[:, None], (rows, columns)).astype(np.float32)


def span_of(
    canvas: tuple[float, float, float, float], picture: tuple[int, int]
) -> tuple[float, float]:
    """Where what's made of a picture (`canvas`, as `placed` takes it) starts down the picture
    and how much of its height it is, as fractions of it."""
    _x, y, _across, down = canvas
    height = max(picture[1], 1)
    return y / height, down / height


def stack_blur(lin: Floats, radius: Floats) -> Floats:
    """A picture (linear light) blurred by a circle that changes from place to place (`radius`,
    pixels): blurred copies at a few circles, each place between the two nearest its own, the
    brightest places boosted to bloom as a lens's do."""
    most = float(radius.max())
    if most < SHARP:
        return lin.astype(np.float32, copy=True)
    steps = [0.0, 1.0]
    while steps[-1] < most:
        steps.append(steps[-1] * 1.6)
    light = bright(lin, most / 2)
    out = np.zeros_like(lin)
    for at, here in enumerate(steps):
        share = tent(radius, steps, at)
        if not share.any():
            continue
        if here < SHARP:
            out += share[..., None] * lin
            continue
        boosted = (lin * (1.0 + _BOOST * min(1.0, here / 6.0) * light)[..., None]).astype(
            np.float32
        )
        out += share[..., None] * spread(boosted, here)
    return out.astype(np.float32)


def tent(values: Floats, steps: Sequence[float], at: int) -> Floats:
    """How much of each value goes to step `at` of rising `steps`: all of it on the step, fading
    to none at the steps either side, so each value's shares add up to 1 (below the first step
    and past the last, all to them)."""
    here = steps[at]
    below = steps[at - 1] if at > 0 else None
    above = steps[at + 1] if at + 1 < len(steps) else None
    rising = (
        np.ones_like(values)
        if below is None
        else np.clip((values - below) / (here - below), 0.0, 1.0)
    )
    falling = (
        np.ones_like(values)
        if above is None
        else np.clip((above - values) / (above - here), 0.0, 1.0)
    )
    return np.where(values <= here, rising, falling).astype(np.float32)


def lifted(lin: Floats, amount: float = _LIFT) -> Floats:
    """Colours made a little richer, each pixel's light kept, as a miniature's paint: tilt-shift's
    finish."""
    light = (lin @ _LUMA)[..., None]
    return np.clip(light + (1.0 + amount) * (lin - light), 0.0, 1.0).astype(np.float32)
