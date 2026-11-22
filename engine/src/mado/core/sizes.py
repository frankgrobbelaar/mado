"""The sizes a picture can be made for: the screens of the devices people have, prints at 300
dpi, the owner's own screens (remembered as Mado sees them) and any other size. Pure.

Every size has exact pixels. A screen keeps its own way round (a phone is tall, a TV wide); a
print turns to the picture's, as paper can be turned. The device list is generic on purpose, no
makes or models, and kept current with what's sold.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

type Purpose = Literal["phone", "tablet", "laptop", "monitor", "ultrawide", "tv", "print", "screen"]
type Group = Literal["screens", "yours", "prints", "other"]

DPI = 300  # a print's pixels to the inch
MAX_PIXELS = 200_000_000  # the biggest size Mado makes: a 16K print's worth and then some
MAX_SIDE = 30_000
_MM_PER_INCH = 25.4
_REMEMBERED = 6  # the owner's screens kept, newest first


@dataclass(frozen=True)
class Size:
    id: str  # "tv-8k", "print-a4", "yours-3440x1440", "other-5000x3000", "other-20x30cm"
    name: str  # "TV 8K", "A4", "Main screen"
    width: int
    height: int
    group: Group
    purpose: Purpose
    label: str  # what a new picture's name says it was made for: "TV 8K", "A4 print"
    turns: bool = False  # it turns to the picture's way round (a print)


@dataclass(frozen=True)
class Screen:
    """One of the owner's screens, as Mado remembers it."""

    name: str  # "Main screen", "Screen 2"
    width: int
    height: int


SCREENS: tuple[Size, ...] = (
    Size("phone", "Phone", 1290, 2796, "screens", "phone", "Phone"),
    Size("tablet", "Tablet", 2048, 2732, "screens", "tablet", "Tablet"),
    Size("laptop", "Laptop", 2560, 1600, "screens", "laptop", "Laptop"),
    Size("monitor-4k", "Monitor 4K", 3840, 2160, "screens", "monitor", "Monitor 4K"),
    Size("ultrawide", "Ultrawide", 3440, 1440, "screens", "ultrawide", "Ultrawide"),
    Size("tv-8k", "TV 8K", 7680, 4320, "screens", "tv", "TV 8K"),
)


def print_pixels(width_mm: float, height_mm: float, dpi: int = DPI) -> tuple[int, int]:
    """A print's pixels at `dpi`: 10 by 15 cm is 1181 by 1772 at 300."""
    return round(width_mm / _MM_PER_INCH * dpi), round(height_mm / _MM_PER_INCH * dpi)


def _print(key: str, name: str, width_mm: float, height_mm: float) -> Size:
    width, height = print_pixels(width_mm, height_mm)
    return Size(f"print-{key}", name, width, height, "prints", "print", f"{name} print", True)


PRINTS: tuple[Size, ...] = (
    _print("10x15", "10 × 15 cm", 100, 150),
    _print("a4", "A4", 210, 297),
    _print("a3", "A3", 297, 420),
)

_OTHER = re.compile(r"other-(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(cm)?")


class SizeError(ValueError):
    """A size Mado can't make, with a sentence saying why."""


def yours(screens: Iterable[Screen]) -> tuple[Size, ...]:
    """The owner's screens as sizes to make for."""
    return tuple(
        Size(
            f"yours-{screen.width}x{screen.height}",
            screen.name,
            screen.width,
            screen.height,
            "yours",
            "screen",
            f"{screen.width} × {screen.height}",
        )
        for screen in screens
        if _makeable(screen.width, screen.height)
    )


def resolve(size_id: str, screens: Sequence[Screen] = ()) -> Size:
    """The size an id names: one of the screens or prints, one of the owner's screens, or any
    other ("other-5000x3000" in pixels, "other-20x30cm" printed at 300 dpi)."""
    for size in (*SCREENS, *PRINTS, *yours(screens)):
        if size.id == size_id:
            return size
    if size_id.startswith("yours-"):
        found = re.fullmatch(r"yours-(\d+)x(\d+)", size_id)
        if found:  # a screen Mado no longer remembers: its size is in its name
            width, height = int(found[1]), int(found[2])
            return _checked(
                Size(
                    size_id,
                    f"{width} × {height}",
                    width,
                    height,
                    "yours",
                    "screen",
                    f"{width} × {height}",
                )
            )
    found = _OTHER.fullmatch(size_id)
    if found is None:
        raise SizeError("Mado doesn't know that size.")
    first, second, cm = float(found[1]), float(found[2]), found[3] is not None
    if cm:
        width, height = print_pixels(first * 10, second * 10)
        name = f"{_number(first)} × {_number(second)} cm"
        return _checked(Size(size_id, name, width, height, "other", "print", f"{name} print", True))
    width, height = round(first), round(second)
    name = f"{width} × {height}"
    return _checked(Size(size_id, name, width, height, "other", "screen", name))


def turned(size: Size, picture_width: int, picture_height: int) -> tuple[int, int]:
    """The pixels made for a picture: a print turns to the picture's way round (landscape or
    portrait); a screen stays as it is."""
    width, height = size.width, size.height
    landscape = picture_width > picture_height
    if size.turns and picture_width != picture_height and (width > height) != landscape:
        return height, width
    return width, height


def shape_name(width: int, height: int) -> str | None:
    """A shape as people say it, "16:9", "4:3", "9:19.5", "21:9" or "1:1", when it's one people
    know (screens' and cameras'); None for any other, such as paper's."""
    ratio = width / height
    for long, short in _SHAPES:
        if abs(ratio - long / short) / (long / short) < 0.03:
            return f"{_number(long)}:{_number(short)}"
        if abs(ratio - short / long) / (short / long) < 0.03:
            return f"{_number(short)}:{_number(long)}"
    return None


# Shapes people know, long side first: screens' and cameras'.
_SHAPES: tuple[tuple[float, float], ...] = (
    (1, 1),
    (5, 4),
    (4, 3),
    (3, 2),
    (16, 10),
    (16, 9),
    (2, 1),
    (19.5, 9),
    (21, 9),
)


def remember(kept: Sequence[Screen], seen: Sequence[tuple[int, int, bool]]) -> list[Screen]:
    """The owner's screens after Mado sees this PC's (`seen`: each one's width, height and
    whether it's the main one): new sizes join at the front, named "Main screen" for the main
    one and "Screen 2", "Screen 3"… for the rest, and a size already kept keeps its name. Only
    the size matters for a picture, so two screens the same size are one. The newest few are
    kept."""
    names = {screen.name for screen in kept}
    sizes = {(screen.width, screen.height) for screen in kept}
    fresh: list[Screen] = []
    ordered = sorted(seen, key=lambda each: not each[2])  # the main one first
    for width, height, main in ordered:
        if not _makeable(width, height) or (width, height) in sizes:
            continue
        name = "Main screen" if main and "Main screen" not in names else _next_name(names)
        names.add(name)
        sizes.add((width, height))
        fresh.append(Screen(name, width, height))
    return [*fresh, *kept][:_REMEMBERED]


def _next_name(taken: set[str]) -> str:
    number = 2
    while f"Screen {number}" in taken:
        number += 1
    return f"Screen {number}"


def _makeable(width: int, height: int) -> bool:
    """Whether Mado makes pictures this big: at least 16 pixels each way, and no bigger than
    `_checked` allows."""
    try:
        _checked(Size("", "", width, height, "yours", "screen", ""))
    except SizeError:
        return False
    return True


def _checked(size: Size) -> Size:
    if size.width < 16 or size.height < 16:
        raise SizeError("That's too small to make: pick at least 16 pixels each way.")
    if size.width > MAX_SIDE or size.height > MAX_SIDE or size.width * size.height > MAX_PIXELS:
        raise SizeError(
            "That's bigger than Mado makes: at most 30,000 pixels a side and 200 megapixels."
        )
    return size


def _number(value: float) -> str:
    """12 as "12", 19.5 as "19.5", the square root of two as "1.41"."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
