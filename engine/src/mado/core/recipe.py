"""What the owner asked for (a recipe) and what Mado does to make it (a plan): the shape, the
way of making it bigger, the model, how many tiles, what it waits for and the honest word on
what it can't do. Pure.

The ways of making a picture bigger: the AI model, four times bigger, then resized exactly to
the size made ("ai"); pixel art grown by repeating its pixels ("pixels"); a screenshot resized
smoothly, so no letters are invented ("smooth"); and a picture already big enough, only resized
down ("shrink"). Four times bigger looks real; much more than that from a small picture looks
painted, and the plan says so.
"""

from dataclasses import dataclass
from typing import Literal

from mado.core.framing import Frame, Shape, frame, note
from mado.core.kind import NAMES, Kind
from mado.core.models import SCALE, Model, Quality, model_for
from mado.core.quality import phrase
from mado.core.sizes import Size, turned

type Method = Literal["ai", "pixels", "smooth", "shrink"]

_PAINTED = 6.0  # this many times bigger or more, from the part kept, looks painted


@dataclass(frozen=True)
class Recipe:
    size: Size
    shape: Shape = "crop"
    focus: tuple[float, float] | None = None  # the owner's point to crop around, as fractions
    kind: Kind | None = None  # None: as Mado guesses
    quality: Quality | None = None  # None: as this PC starts on
    clean: bool = True  # noise and JPEG blocks out first (Fast's strong model)


@dataclass(frozen=True)
class Plan:
    width: int  # the size made, turned to the picture's way round for a print
    height: int
    frame: Frame
    focus: tuple[float, float]  # the point the crop is around
    focus_found: bool  # Mado found it (the owner didn't say)
    note: str  # what the shape does
    kind: Kind
    kind_guessed: bool
    quality: Quality
    method: Method
    model: Model | None
    scale: float  # from the part kept to the size made
    how: str  # "Made with the photo model, guessed from the picture."
    warning: str | None  # what it can't make look real


def plan(
    recipe: Recipe,
    width: int,
    height: int,
    *,
    guessed_kind: Kind,
    found_focus: tuple[float, float],
    starts_on: dict[Literal["photo", "drawing"], Quality],
) -> Plan:
    """How a `width` by `height` picture (as it's shown) is made to `recipe`. `guessed_kind` is
    what Mado takes it for, `found_focus` where it found the subject, and `starts_on` the
    quality each kind starts on here."""
    target = turned(recipe.size, width, height)
    focus = recipe.focus or found_focus
    made = frame(width, height, *target, recipe.shape, focus)
    kind = recipe.kind or guessed_kind
    quality = recipe.quality or starts_on["drawing" if kind == "drawing" else "photo"]
    scale = target[0] / made.canvas.width
    method: Method
    model: Model | None = None
    if scale <= 1.0:
        method = "shrink"
    elif kind == "pixels":
        method = "pixels"
    elif kind == "screenshot":
        method = "smooth"
    else:
        method = "ai"
        model = model_for(kind, quality, recipe.clean)
    phrase_ = _phrase(recipe.size)
    return Plan(
        width=target[0],
        height=target[1],
        frame=made,
        focus=focus,
        focus_found=recipe.focus is None,
        note=note(made, phrase_, width, height, target),
        kind=kind,
        kind_guessed=recipe.kind is None,
        quality=quality,
        method=method,
        model=model,
        scale=scale,
        how=_how(method, kind, recipe.kind is None),
        warning=_warning(method, scale, width, height),
    )


def _phrase(size: Size) -> str:
    if size.group == "other" and size.purpose != "print":
        return "That size"
    return phrase(size.purpose, size.name)


def _how(method: Method, kind: Kind, guessed: bool) -> str:
    said = ", guessed from the picture" if guessed else ""
    match method:
        case "shrink":
            return "It's already big enough, so Mado only makes it smaller, sharply."
        case "pixels":
            return f"Pixel art{said}: grown by repeating its pixels, so it stays blocky. No AI."
        case "smooth":
            return f"A screenshot{said}: resized smoothly, so no letters are invented. No AI."
        case "ai":
            word = "drawing" if kind == "drawing" else "photo"
            return f"Made with the {word} model{said}."


def _warning(method: Method, scale: float, width: int, height: int) -> str | None:
    if method != "ai" or scale < _PAINTED:
        return None
    times = round(scale)
    return (
        f"That's {times} times bigger than the picture's {width} × {height}: beyond "
        f"{SCALE} times, detail can't be found, so it looks painted rather than real."
    )


def kind_name(kind: Kind) -> str:
    return NAMES[kind]
