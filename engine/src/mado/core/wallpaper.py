"""The wallpaper studio's rules: the owner's monitors as Windows arranges them, a picture for each
or one laid across them all with a gap for their bezels, where each part is cut, how it's made,
and the day's pictures for the daily change. Pure.

Geometry is in pixels. The monitors' are Windows' own desktop pixels: how Windows' display
settings place them, and how its own span lays a picture across them. The parts' are the
picture's, as it's shown (turned upright); a part reaches past the picture where its edges are
extended.
"""

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from mado.core.framing import Box, Frame, Shape, frame
from mado.core.kind import Kind
from mado.core.models import Model, Quality
from mado.core.recipe import PAINTED, Method, how, warning, way

type Layout = Literal["each", "across"]

ALL = "*"  # one across all: the picks' and the studio's key for every monitor at once
GAP_MOST = 200  # pixels left for the bezels between two monitors, at most
ZOOM_MOST = 4.0  # the nearest a part comes in: a quarter of the biggest crop across
_SQUARE = 0.05  # a picture or monitor this near square suits either way round


@dataclass(frozen=True)
class Monitor:
    """A monitor as Windows has it now."""

    id: str  # Windows' own name for it: its device path
    name: str  # its own name ("Studio 27"), or "Screen 2" where it gives none
    number: int  # the number Windows' display settings give it
    x: int  # where it sits in Windows' arrangement, in its pixels
    y: int
    width: int  # its pixels, the way it's turned
    height: int
    scale: float = 1.0  # Windows' scale for it: 1.25 for 125%
    rotation: int = 0  # 0, 90, 180 or 270
    main: bool = False


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class Cut:
    """Where the owner cut a picture: the part's middle, as fractions of the picture across and
    down (None: around its subject, as Mado found it), and how near it comes (1: the biggest part
    with the monitor's shape)."""

    x: float | None = None
    y: float | None = None
    zoom: float = 1.0


@dataclass(frozen=True)
class Part:
    """A monitor's part of a picture, in the picture's pixels; `frame` is what it's cut from,
    whose canvas is extended once when its edges are drawn, so parts laid across share it."""

    monitor: Monitor
    box: Box
    frame: Frame


@dataclass(frozen=True)
class Made:
    """How a part is made: `scale` times bigger (or smaller), its way, its model, the words for
    them and what it can't make look real."""

    scale: float
    method: Method
    model: Model | None
    how: str
    warning: str | None


@dataclass(frozen=True)
class Candidate:
    """A picture the daily change could show: its size as it's shown, and the day it last did."""

    id: int
    width: int
    height: int
    shown: str | None  # "2026-11-22"; None: never


def key_of(monitor_id: str) -> str:
    """A monitor's short name, the same however Windows writes its device path."""
    return hashlib.blake2b(monitor_id.casefold().encode(), digest_size=5).hexdigest()


def arrangement(monitors: Iterable[Monitor]) -> str:
    """The monitors as they're arranged, in a word that changes once any one's pixels, place or
    turn does (a wallpaper made for them is made again then). Windows' scale doesn't change a
    wallpaper's pixels, nor does a name."""
    each = sorted(f"{key_of(m.id)}:{m.x},{m.y},{m.width}x{m.height},{m.rotation}" for m in monitors)
    return hashlib.blake2b("|".join(each).encode(), digest_size=8).hexdigest()


def ordered(monitors: Iterable[Monitor]) -> list[Monitor]:
    """The main monitor first, then by the number Windows gives them."""
    return sorted(monitors, key=lambda each: (not each.main, each.number, each.id))


def spread(monitors: Sequence[Monitor], gap: int) -> dict[str, Rect]:
    """Each monitor's place (by its id) with `gap` pixels between neighbours for their bezels.
    Every line where two monitors meet side by side moves the monitors at and past it across by
    a gap, and every line where they meet one above the other moves those at and below it down,
    so monitors in a column or a row keep their line."""
    across = sorted(
        {
            b.x
            for a in monitors
            for b in monitors
            if a.x + a.width == b.x and _meet(a.y, a.height, b.y, b.height)
        }
    )
    down = sorted(
        {
            b.y
            for a in monitors
            for b in monitors
            if a.y + a.height == b.y and _meet(a.x, a.width, b.x, b.width)
        }
    )
    return {
        each.id: Rect(
            each.x + gap * sum(line <= each.x for line in across),
            each.y + gap * sum(line <= each.y for line in down),
            each.width,
            each.height,
        )
        for each in monitors
    }


def _meet(start: int, length: int, other: int, other_length: int) -> bool:
    """Whether two edges share some length, not only a corner."""
    return min(start + length, other + other_length) > max(start, other)


def bounds(rects: Iterable[Rect]) -> Rect:
    """The smallest rectangle holding every one."""
    found = list(rects)
    left, top = min(r.x for r in found), min(r.y for r in found)
    right, bottom = max(r.right for r in found), max(r.bottom for r in found)
    return Rect(left, top, right - left, bottom - top)


def framed(
    width: int,
    height: int,
    target: tuple[int, int],
    shape: Shape,
    cut: Cut,
    focus: tuple[float, float],
) -> Frame:
    """The frame of a `width` by `height` picture for a `target` of pixels: cropped, the biggest
    part with the target's shape made `cut.zoom` times nearer, its middle where the owner moved
    it (else around the subject, `focus`), held inside the picture; or extended, all of the
    picture in the middle of a canvas with the target's shape."""
    if shape == "extend":
        return frame(width, height, *target, "extend")
    biggest = frame(width, height, *target, "crop")
    zoom = min(max(cut.zoom, 1.0), ZOOM_MOST)
    kept_width, kept_height = biggest.kept.width / zoom, biggest.kept.height / zoom
    middle_x = (cut.x if cut.x is not None else focus[0]) * width
    middle_y = (cut.y if cut.y is not None else focus[1]) * height
    kept = Box(
        _held(middle_x - kept_width / 2, 0.0, width - kept_width),
        _held(middle_y - kept_height / 2, 0.0, height - kept_height),
        kept_width,
        kept_height,
    )
    share = 1 - (kept_width * kept_height) / (width * height)
    sides = biggest.sides if zoom == 1.0 or biggest.sides != "none" else "sides"
    return Frame("crop", kept, kept, sides, max(share, 0.0))


def part_for(
    monitor: Monitor,
    size: tuple[int, int],
    shape: Shape,
    cut: Cut,
    focus: tuple[float, float],
) -> Part:
    """One for each: the monitor's part of a picture `size` big, with the monitor's own shape."""
    made = framed(*size, (monitor.width, monitor.height), shape, cut, focus)
    return Part(monitor, made.canvas, made)


def parts_across(
    monitors: Sequence[Monitor],
    gap: int,
    size: tuple[int, int],
    shape: Shape,
    cut: Cut,
    focus: tuple[float, float],
) -> list[Part]:
    """One across all: a picture `size` big laid over the monitors as they sit, `gap` pixels
    between them for the bezels, each monitor's part where it falls; the main one first."""
    places = spread(monitors, gap)
    whole = bounds(places.values())
    made = framed(*size, (round(whole.width), round(whole.height)), shape, cut, focus)
    return [
        Part(each, laid_across(made.canvas, whole, places[each.id]), made)
        for each in ordered(monitors)
    ]


def laid_across(canvas: Box, whole: Rect, place: Rect) -> Box:
    """The part of `canvas` (in the picture's pixels) that falls on `place`, the canvas laid over
    `whole` (in the monitors' pixels)."""
    across, down = canvas.width / whole.width, canvas.height / whole.height
    return Box(
        canvas.x + (place.x - whole.x) * across,
        canvas.y + (place.y - whole.y) * down,
        place.width * across,
        place.height * down,
    )


def made(
    part: Part,
    width: int,
    height: int,
    kind: Kind,
    quality: Quality,
    *,
    guessed: bool,
    clean: bool = True,
) -> Made:
    """How a part of a `width` by `height` picture is made at exactly its monitor's pixels: as
    the Size tab makes a picture, and as honest about what looks painted."""
    scale = part.monitor.width / part.box.width
    method, model = way(scale, kind, quality, clean)
    return Made(
        scale, method, model, how(method, kind, guessed), warning(method, scale, width, height)
    )


def suits(width: int, height: int, target_width: int, target_height: int) -> bool:
    """Whether a picture suits a monitor (or the whole arrangement): its way round (a square, or
    a square monitor, either way), and enough pixels that, cropped to the monitor's shape, it's
    made less than `PAINTED` times bigger, as beyond that it looks painted."""
    if width <= 0 or height <= 0:
        return False
    either = _square(width, height) or _square(target_width, target_height)
    if not either and (width > height) != (target_width > target_height):
        return False
    kept = frame(width, height, target_width, target_height, "crop").kept
    return target_width / kept.width < PAINTED


def picks(
    candidates: Sequence[Candidate],
    monitors: Sequence[Monitor],
    layout: Layout,
    gap: int,
    day: str,
) -> dict[str, int]:
    """The day's pictures: for each monitor (by its id, the main one first), or for all of them
    at once (`ALL`), a candidate that suits it, the one not shown for longest (never shown first),
    so none is shown again till every one that suits has been. Ties go the same way all day and
    another way the next. One for each puts no picture on two monitors while another suits; a
    monitor nothing suits is left as it is."""
    if layout == "across":
        whole = bounds(spread(monitors, gap).values())
        target = (round(whole.width), round(whole.height))
        chosen = _longest_unshown(candidates, target, day, ALL, set())
        return {ALL: chosen.id} if chosen is not None else {}
    found: dict[str, int] = {}
    used: set[int] = set()
    for monitor in ordered(monitors):
        target = (monitor.width, monitor.height)
        chosen = _longest_unshown(candidates, target, day, key_of(monitor.id), used)
        if chosen is None:
            chosen = _longest_unshown(candidates, target, day, key_of(monitor.id), set())
        if chosen is not None:
            found[monitor.id] = chosen.id
            used.add(chosen.id)
    return found


def _longest_unshown(
    candidates: Sequence[Candidate],
    target: tuple[int, int],
    day: str,
    salt: str,
    used: set[int],
) -> Candidate | None:
    suited = [
        each
        for each in candidates
        if each.id not in used and suits(each.width, each.height, *target)
    ]
    if not suited:
        return None
    return min(suited, key=lambda each: (each.shown or "", _tie(day, salt, each.id)))


def _tie(day: str, salt: str, picture: int) -> str:
    """A tie broken the same way all day, another way the next."""
    return hashlib.blake2b(f"{day}|{salt}|{picture}".encode(), digest_size=8).hexdigest()


def _square(width: int, height: int) -> bool:
    return abs(width - height) / max(width, height) < _SQUARE


def _held(value: float, low: float, high: float) -> float:
    return min(max(value, low), max(high, low))
