"""Looks: Mado's own, each made by code from tone curves, colour balance, split toning,
saturation and channel mixes as a 33-point table (mado/core/grids.py), and the owner's, which
come as tables too (imported .cube files and kept mixes, mado/own_looks.py). Pure.

Mado's looks have Mado's own names: never a film brand's, a camera maker's or an app's. A look
at a strength is its table mixed with the colours as they were, and fade (a finishing touch that
only changes colours) goes into the same table, so a picture goes through one table, once.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import numpy as np
import numpy.typing as npt

from mado.core.grids import SIDE, Colours, Grid, blended, identity
from mado.core.touches import NAMES, Touches, fade

ORIGINAL = "original"
_LUMA = np.array(
    [0.2126, 0.7152, 0.0722], np.float32
)  # how bright each of red, green and blue looks

type Floats = npt.NDArray[np.float32]
type Points = tuple[tuple[float, float], ...]


@dataclass(frozen=True, eq=False)
class Look:
    id: str  # "warm-film"; the owner's are "yours-3"
    name: str  # "Warm film"
    grid: Grid | None  # None: the picture's own colours (the original)


# Tone and colour, the pieces Mado's looks are made of. Each takes colours (..., 3), 0 to 1.


def _curve(values: Floats, points: Points) -> Floats:
    """A smooth tone curve through `points` (in, out), never turning back on itself (a monotone
    cubic, Fritsch and Carlson's)."""
    xs = np.array([point[0] for point in points], np.float32)
    ys = np.array([point[1] for point in points], np.float32)
    steps = np.diff(xs)
    slopes = np.diff(ys) / steps
    tangents = np.empty_like(xs)
    tangents[0], tangents[-1] = slopes[0], slopes[-1]
    first, second = 2 * steps[1:] + steps[:-1], steps[1:] + 2 * steps[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = (first + second) / (first / slopes[:-1] + second / slopes[1:])
    tangents[1:-1] = np.where(slopes[:-1] * slopes[1:] > 0, mean, 0.0)
    held = np.clip(values, xs[0], xs[-1])
    at = np.clip(np.searchsorted(xs, held, side="right") - 1, 0, len(xs) - 2)
    t = (held - xs[at]) / steps[at]
    t2, t3 = t * t, t * t * t
    out = (2 * t3 - 3 * t2 + 1) * ys[at] + (t3 - 2 * t2 + t) * steps[at] * tangents[at]
    out += (-2 * t3 + 3 * t2) * ys[at + 1] + (t3 - t2) * steps[at] * tangents[at + 1]
    return out.astype(np.float32)


def _tone(colours: Colours, points: Points) -> Colours:
    """The same tone curve on red, green and blue."""
    return _curve(colours, points)


def _channels(colours: Colours, red: Points, green: Points, blue: Points) -> Colours:
    """A tone curve of its own on each of red, green and blue."""
    return np.stack(
        [
            _curve(colours[..., 0], red),
            _curve(colours[..., 1], green),
            _curve(colours[..., 2], blue),
        ],
        axis=-1,
    )


def _light(colours: Colours) -> Floats:
    return (colours @ _LUMA)[..., None].astype(np.float32)


def _saturate(colours: Colours, amount: float) -> Colours:
    """More colour (over 1) or less (under 1), the light kept."""
    light = _light(colours)
    return (light + (colours - light) * np.float32(amount)).astype(np.float32)


def _vibrance(colours: Colours, amount: float) -> Colours:
    """More colour where there's little, less added where there's plenty already."""
    light = _light(colours)
    chroma = colours.max(axis=-1, keepdims=True) - colours.min(axis=-1, keepdims=True)
    boost = 1.0 + np.float32(amount) * (1.0 - np.clip(chroma * 1.6, 0.0, 1.0))
    return (light + (colours - light) * boost).astype(np.float32)


def _balance(
    colours: Colours,
    shadows: tuple[float, float, float] = (0.0, 0.0, 0.0),
    midtones: tuple[float, float, float] = (0.0, 0.0, 0.0),
    highlights: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Colours:
    """Colour pushed into the shadows, mid-tones and highlights (split toning)."""
    light = _light(colours)
    dark, bright = (1.0 - light) ** 2, light**2
    middle = 1.0 - dark - bright
    pushed = colours + dark * np.array(shadows, np.float32)
    pushed += middle * np.array(midtones, np.float32) + bright * np.array(highlights, np.float32)
    return pushed.astype(np.float32)


def _mix(colours: Colours, matrix: tuple[tuple[float, float, float], ...]) -> Colours:
    """Each of red, green and blue made from all three (a channel mixer)."""
    return (colours @ np.array(matrix, np.float32).T).astype(np.float32)


def _grey(colours: Colours, weights: tuple[float, float, float]) -> Floats:
    """Black and white, from red, green and blue in these shares."""
    return (colours @ np.array(weights, np.float32))[..., None].astype(np.float32)


def _gradient(
    light: Floats, stops: tuple[tuple[float, tuple[float, float, float]], ...]
) -> Colours:
    """Light (..., 1) mapped through colours at points along it: duotones and toned prints."""
    places = np.array([stop[0] for stop in stops], np.float32)
    colours = np.array([stop[1] for stop in stops], np.float32)
    flat = light[..., 0]
    return np.stack(
        [np.interp(flat, places, colours[:, channel]) for channel in range(3)], axis=-1
    ).astype(np.float32)


def _turn(colours: Colours, degrees: float) -> Colours:
    """Every colour's hue turned round the line of greys."""
    angle = np.radians(degrees)
    cos, sin = np.cos(angle), np.sin(angle)
    third, root = 1.0 / 3.0, np.sqrt(1.0 / 3.0)
    matrix = (
        (cos + (1 - cos) * third, third * (1 - cos) - root * sin, third * (1 - cos) + root * sin),
        (third * (1 - cos) + root * sin, cos + third * (1 - cos), third * (1 - cos) - root * sin),
        (third * (1 - cos) - root * sin, third * (1 - cos) + root * sin, cos + third * (1 - cos)),
    )
    return _mix(colours, matrix)


# Mado's looks.


def _warm_film(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.04), (0.25, 0.225), (0.5, 0.515), (0.75, 0.79), (1, 0.975)))
    c = _balance(c, shadows=(0.03, 0.008, -0.035), midtones=(0.035, 0.012, -0.035),
                 highlights=(0.06, 0.025, -0.06))  # fmt: skip
    return _saturate(c, 1.1)


def _cool_film(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.03), (0.25, 0.235), (0.5, 0.5), (0.75, 0.77), (1, 0.98)))
    c = _balance(c, shadows=(-0.03, 0.0, 0.045), highlights=(-0.03, 0.005, 0.035))
    return _saturate(c, 0.88)


def _faded(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.13), (0.5, 0.53), (1, 0.92)))
    c = _saturate(c, 0.7)
    return _balance(c, highlights=(0.02, 0.01, -0.01))


def _teal_and_orange(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.0), (0.25, 0.2), (0.5, 0.5), (0.75, 0.81), (1, 1.0)))
    c = _balance(c, shadows=(-0.07, 0.025, 0.07), highlights=(0.07, 0.02, -0.06))
    return _vibrance(c, 0.3)


def _silver(c: Colours) -> Colours:
    grey = _grey(c, (0.27, 0.62, 0.11))
    grey = _tone(grey, ((0, 0.01), (0.25, 0.19), (0.5, 0.5), (0.75, 0.82), (1, 0.99)))
    return np.repeat(grey, 3, axis=-1)


def _golden_hour(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.03), (0.5, 0.56), (1, 1.0)))
    c = _balance(c, shadows=(0.04, 0.015, -0.03), midtones=(0.08, 0.04, -0.07),
                 highlights=(0.05, 0.03, -0.08))  # fmt: skip
    return _vibrance(c, 0.3)


def _night_neon(c: Colours) -> Colours:
    c = _turn(c, -18)
    c = _tone(c, ((0, 0.0), (0.25, 0.17), (0.5, 0.48), (0.75, 0.82), (1, 1.0)))
    c = _balance(c, shadows=(0.02, -0.03, 0.11), highlights=(0.06, -0.04, 0.05))
    return _saturate(c, 1.4)


def _duotone(c: Colours) -> Colours:
    light = _tone(_grey(c, (0.3, 0.59, 0.11)), ((0, 0.0), (0.3, 0.24), (0.7, 0.78), (1, 1.0)))
    return _gradient(light, ((0.0, (0.09, 0.11, 0.3)), (1.0, (0.99, 0.82, 0.62))))


def _bold_colour(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.0), (0.25, 0.21), (0.5, 0.5), (0.75, 0.8), (1, 1.0)))
    c = _vibrance(c, 0.45)
    return _saturate(c, 1.12)


def _sepia_print(c: Colours) -> Colours:
    light = _tone(_grey(c, (0.3, 0.59, 0.11)), ((0, 0.0), (0.5, 0.52), (1, 1.0)))
    return _gradient(
        light,
        (
            (0.0, (0.12, 0.08, 0.05)),
            (0.5, (0.56, 0.42, 0.29)),
            (1.0, (0.98, 0.94, 0.85)),
        ),
    )


def _moody_blue(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.02), (0.25, 0.17), (0.5, 0.42), (0.75, 0.7), (1, 0.93)))
    c = _saturate(c, 0.72)
    return _balance(c, shadows=(-0.02, 0.01, 0.06), midtones=(-0.02, 0.005, 0.03))


def _cross_processed(c: Colours) -> Colours:
    c = _channels(
        c,
        red=((0, 0.0), (0.25, 0.17), (0.5, 0.52), (0.75, 0.86), (1, 1.0)),
        green=((0, 0.02), (0.25, 0.22), (0.5, 0.53), (0.75, 0.83), (1, 1.0)),
        blue=((0, 0.14), (0.5, 0.46), (1, 0.76)),
    )
    return _saturate(c, 1.12)


def _soft_pastel(c: Colours) -> Colours:
    c = _tone(c, ((0, 0.17), (0.5, 0.6), (1, 0.97)))
    c = _saturate(c, 0.82)
    return _balance(c, shadows=(-0.01, 0.03, 0.02), highlights=(0.03, 0.0, 0.02))


_MADE: tuple[tuple[str, str, Callable[[Colours], Colours] | None], ...] = (
    (ORIGINAL, "Original", None),
    ("warm-film", "Warm film", _warm_film),
    ("cool-film", "Cool film", _cool_film),
    ("faded", "Faded", _faded),
    ("teal-and-orange", "Teal and orange", _teal_and_orange),
    ("silver", "Silver", _silver),
    ("golden-hour", "Golden hour", _golden_hour),
    ("night-neon", "Night neon", _night_neon),
    ("duotone", "Duotone", _duotone),
    ("bold-colour", "Bold colour", _bold_colour),
    ("sepia-print", "Sepia print", _sepia_print),
    ("moody-blue", "Moody blue", _moody_blue),
    ("cross-processed", "Cross-processed", _cross_processed),
    ("soft-pastel", "Soft pastel", _soft_pastel),
)


@cache
def _grid(look_id: str) -> Grid | None:
    made = next(each[2] for each in _MADE if each[0] == look_id)
    if made is None:
        return None
    grid = np.clip(made(identity(SIDE)), 0.0, 1.0).astype(np.float32)
    grid.flags.writeable = False  # shared by every picture: never changed in place
    return grid


def built_in() -> list[Look]:
    """Mado's looks, in the order the Looks tab lists them, the original first."""
    return [Look(look_id, name, _grid(look_id)) for look_id, name, _made in _MADE]


def mado_look(look_id: str) -> Look | None:
    """One of Mado's looks by its id; None when it isn't one."""
    for each_id, name, _made in _MADE:
        if each_id == look_id:
            return Look(each_id, name, _grid(each_id))
    return None


def table(look: Look, strength: float, touches: Touches) -> Grid | None:
    """The one table a picture goes through for a look at `strength` (0 to 1) with its touches'
    fade; None when it leaves every colour as it was."""
    shown = look.grid is not None and strength > 0
    if not shown and touches.fade <= 0:
        return None
    grid = blended(look.grid, strength) if look.grid is not None and shown else identity(SIDE)
    if touches.fade > 0:
        grid = fade(grid, touches.fade)
    return np.clip(grid, 0.0, 1.0).astype(np.float32)


def changes(look: Look, strength: float, touches: Touches) -> bool:
    """Whether a look at `strength` with these touches changes the picture at all."""
    return (look.grid is not None and strength > 0) or bool(touches.on())


def label(look: Look, strength: float, touches: Touches) -> str:
    """What a new picture's name says of its look: "Warm film"; with only touches, the one
    ("Grain") or "Finishing touches"."""
    if look.grid is not None and strength > 0:
        return look.name
    on = touches.on()
    return NAMES[on[0]] if len(on) == 1 else "Finishing touches"


def phrase(look: Look, strength: float, touches: Touches) -> str:
    """The look as History and Save say it, after "with": "Warm film at 60%", "Warm film";
    with only touches, "grain" or "finishing touches"."""
    if look.grid is not None and strength > 0:
        percent = round(strength * 100)
        return look.name if percent >= 100 else f"{look.name} at {percent}%"
    return label(look, strength, touches).lower()
