"""Finishing touches, after a look: grain, a vignette, glow, fade, a light leak and dust, each
with its own amount (0 is off, 100 the most), all drawn by code. Pure: the shapes and numbers
they're made of; mado/looks.py lays them on a picture.

Every touch is placed and sized in the picture made, relative to its short side, and seeded by
the picture, so a preview the size of a screen shows what the picture saved at full size will:
the same grain, the same specks of dust in the same places, the same leak of light.
"""

from dataclasses import dataclass, fields
from typing import Literal

import numpy as np
import numpy.typing as npt

type Touch = Literal["grain", "vignette", "glow", "fade", "leak", "dust"]
type Floats = npt.NDArray[np.float32]

ORDER: tuple[Touch, ...] = ("grain", "vignette", "glow", "fade", "leak", "dust")
NAMES: dict[Touch, str] = {
    "grain": "Grain",
    "vignette": "Vignette",
    "glow": "Glow",
    "fade": "Fade",
    "leak": "Light leak",
    "dust": "Dust",
}

GRAIN_CELLS = 1400  # grain's specks across the picture made's short side
_GRAIN = 0.11  # grain's spread at 100, in mid-grey
_VIGNETTE = 0.55  # how dark a vignette's corners get at 100
_FADE_BLACK = 0.16  # where black lifts to at 100
_FADE_WHITE = 0.06  # how far white comes down at 100
GLOW_REACH = 0.025  # how far glow spreads, a share of the short side
_GLOW = 0.65  # glow's strength at 100
_GLOW_FROM = 0.62  # glow comes from colours brighter than this
_SPECKS = 160  # specks of dust at 100 on a square picture; more on a wider one
_HAIRS = 6


@dataclass(frozen=True)
class Touches:
    """Each touch's amount, 0 (off) to 100."""

    grain: int = 0
    vignette: int = 0
    glow: int = 0
    fade: int = 0
    leak: int = 0
    dust: int = 0

    def on(self) -> list[Touch]:
        """The touches turned on, in the order they're listed."""
        return [touch for touch in ORDER if self.amount(touch) > 0]

    def amount(self, touch: Touch) -> int:
        found: int = getattr(self, touch)
        return found

    def spatial(self) -> bool:
        """Whether any touch is drawn across the picture, rather than only changing colours (as
        fade does, which goes into the look's table)."""
        return any(self.amount(touch) > 0 for touch in ORDER if touch != "fade")


NONE = Touches()


def named(amounts: dict[str, int]) -> Touches:
    """Touches from their amounts by name, each held to 0 to 100; names it doesn't know left out."""
    known = {field.name for field in fields(Touches)}
    return Touches(**{name: min(max(int(value), 0), 100) for name, value in amounts.items()
                      if name in known})  # fmt: skip


def words(touches: Touches) -> str:
    """The touches turned on, as a list reads: "grain 20, vignette 35"."""
    return ", ".join(f"{NAMES[touch].lower()} {touches.amount(touch)}" for touch in touches.on())


def fade(values: Floats, amount: int) -> Floats:
    """Fade: black lifted and white brought down a little, as an old print's are."""
    share = np.float32(amount / 100)
    black = _FADE_BLACK * share
    white = 1.0 - _FADE_WHITE * share
    return (black + values * (white - black)).astype(np.float32)


def grain_cell(short: float) -> float:
    """How big a speck of grain is, in pixels of a picture made `short` pixels on its short
    side."""
    return max(short, 1.0) / GRAIN_CELLS


def noise(seed: int, rows: range, columns: range) -> Floats:
    """Grain's specks for these rows and columns of its cells: each a fixed number for the seed
    and its place, spread about 0 like a bell (three 10-bit numbers from one hash, added), so any
    part of the picture gets the same grain however much of it is asked for."""
    row = np.arange(rows.start, rows.stop, dtype=np.int64).astype(np.uint32)[:, None]
    column = np.arange(columns.start, columns.stop, dtype=np.int64).astype(np.uint32)[None, :]
    with np.errstate(over="ignore"):  # a hash wraps round on purpose (murmur3's finish)
        mixed = row * np.uint32(0x8DA6B343) ^ column * np.uint32(0xD8163841)
        mixed ^= np.uint32(seed & 0xFFFFFFFF)
        mixed ^= mixed >> np.uint32(16)
        mixed *= np.uint32(0x85EBCA6B)
        mixed ^= mixed >> np.uint32(13)
        mixed *= np.uint32(0xC2B2AE35)
        mixed ^= mixed >> np.uint32(16)
    ten = np.uint32(0x3FF)
    total = (mixed & ten) + ((mixed >> np.uint32(10)) & ten) + ((mixed >> np.uint32(20)) & ten)
    # Three numbers from 0 to 1023 added: about 1534.5 on average, spread about 512.
    return ((total.astype(np.float32) - np.float32(1534.5)) / np.float32(511.5)).astype(np.float32)


def grain_weights(amount: int) -> Floats:
    """How far grain moves a pixel, in levels of 255, by how light it is (0 to 255): strongest in
    the mid-tones, as film's is, fainter in shadow and highlight. The same in red, green and
    blue, so grey stays grey."""
    light = np.arange(256, dtype=np.float32) / np.float32(255)
    weight = 0.35 + 0.65 * (1.0 - (2.0 * light - 1.0) ** 2)
    return (weight * np.float32(_GRAIN * amount / 100 * 255)).astype(np.float32)


def vignette(across: Floats, down: Floats, amount: int) -> Floats:
    """How much of its light each place keeps, from its place in the picture made (-1 to 1 each
    way from the middle): all of it in the middle, darker towards the corners, softly."""
    reach = np.sqrt(across**2 + down**2) / np.sqrt(np.float32(2.0))  # 1 at a corner
    fall = np.clip((reach - 0.35) / 0.75, 0.0, 1.0)
    fall = fall * fall * (3.0 - 2.0 * fall)  # smooth
    return (1.0 - np.float32(_VIGNETTE * amount / 100) * fall).astype(np.float32)


def glow_light(values: Floats) -> Floats:
    """What glows: the bright parts, softly, before they're spread."""
    light = values.max(axis=-1, keepdims=True)
    rise = np.clip((light - _GLOW_FROM) / (1.0 - _GLOW_FROM), 0.0, 1.0)
    return (values * rise).astype(np.float32)


def glow_share(amount: int) -> float:
    return _GLOW * amount / 100


@dataclass(frozen=True)
class Leak:
    """A leak of warm light coming in at the picture's edge, as on film the camera let light
    onto: its middle (fractions of the picture made, just past an edge), how far it reaches (a
    share of the long side) and its colour."""

    x: float
    y: float
    reach: float
    colour: tuple[float, float, float]


_LEAK_COLOURS = ((1.0, 0.42, 0.16), (1.0, 0.55, 0.22), (0.98, 0.32, 0.24))


def leak(seed: int) -> Leak:
    """Where the picture's light leak comes in: from the left or the right, somewhere along it."""
    rng = np.random.default_rng(seed ^ 0x1EA4)
    side = float(rng.choice([-0.12, 1.12]))
    colour = _LEAK_COLOURS[int(rng.integers(len(_LEAK_COLOURS)))]
    return Leak(side, float(rng.uniform(0.15, 0.85)), float(rng.uniform(0.45, 0.7)), colour)


def leak_light(across: Floats, down: Floats, aspect: float, at: Leak, amount: int) -> Floats:
    """How much of the leak's light falls on each place (`across` and `down` as fractions of the
    picture made, `aspect` its width over its height): most at its edge, fading softly."""
    long = max(aspect, 1.0)
    dx = (across - at.x) * aspect / long
    dy = (down - at.y) / long
    reach = np.float32(at.reach)
    fall = np.exp(-(dx**2 * 2.2 + dy**2) / (reach * reach))
    return (fall * np.float32(0.85 * amount / 100)).astype(np.float32)


@dataclass(frozen=True)
class Speck:
    """A speck of dust or a hair, in the picture made: where (fractions of it), how big (a share
    of its short side), light or dark, and how much it shows. A speck's outline is uneven, as
    dust is (how far out each of its corners reaches); a hair is a few points to join."""

    x: float
    y: float
    size: float
    light: bool
    opacity: float
    outline: tuple[float, ...] = ()
    hair: tuple[tuple[float, float], ...] = ()


def corners(speck: Speck, x: float, y: float, radius: float) -> list[tuple[float, float]]:
    """A speck's uneven outline around `x`, `y`, `radius` across."""
    count = len(speck.outline)
    return [
        (
            x + radius * reach * float(np.cos(2 * np.pi * index / count)),
            y + radius * reach * float(np.sin(2 * np.pi * index / count)),
        )
        for index, reach in enumerate(speck.outline)
    ]


def specks(seed: int, amount: int, aspect: float) -> list[Speck]:
    """The dust on the picture made: the same specks for the same seed, more as `amount` grows
    (the first ones always kept), and more on a wider picture, as there's more of it."""
    if amount <= 0:
        return []
    rng = np.random.default_rng(seed ^ 0xD057)
    area = max(aspect, 1.0 / aspect)
    total = round(_SPECKS * area)
    found: list[Speck] = []
    for _ in range(total):
        size = float(rng.uniform(0.0006, 0.0026) * (1.0 + 2.0 * rng.random() ** 6))
        found.append(
            Speck(
                x=float(rng.random()),
                y=float(rng.random()),
                size=size,
                light=bool(rng.random() < 0.65),
                opacity=float(rng.uniform(0.35, 0.85)),
                outline=tuple(float(each) for each in rng.uniform(0.55, 1.15, 7)),
            )
        )
    hairs: list[Speck] = []
    for _ in range(_HAIRS):
        x, y = float(rng.random()), float(rng.random())
        turn = float(rng.uniform(0, 2 * np.pi))
        length = float(rng.uniform(0.01, 0.035))
        points = [(x, y)]
        for _ in range(5):
            turn += float(rng.normal(0, 0.6))
            points.append(
                (
                    points[-1][0] + float(np.cos(turn)) * length / 5 / aspect,
                    points[-1][1] + float(np.sin(turn)) * length / 5,
                )
            )
        light = bool(rng.random() < 0.65)
        hairs.append(Speck(x, y, 0.0005, light, 0.7, hair=tuple(points)))
    shown = round(total * amount / 100)
    return found[:shown] + hairs[: round(_HAIRS * amount / 100)]
