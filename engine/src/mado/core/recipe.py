"""A recipe: what the owner asked for, as steps made one after another, and what Mado does to make
it (a plan). Pure.

The steps, in the order they're made: the edits (erased, cut out, blurred behind: the Edit tab,
mado/core/edits.py), the size (cropped or extended, then made bigger: the Size tab) and a look
with its finishing touches, on the whole picture or only a part (the Looks tab); then the picture
is saved. Any step can be left out. Each step is a value that says all it does, so a recipe can be
kept by name and run on many pictures ("4K, then Warm film at 60%, then JPEG into Edited").

The ways of making a picture bigger: the AI model, four times bigger, then resized exactly to
the size made ("ai"); pixel art grown by repeating its pixels ("pixels"); a screenshot resized
smoothly, so no letters are invented ("smooth"); and a picture already big enough, only resized
down ("shrink"). With no size step, the picture keeps its pixels ("keep"). Four times bigger
looks real; much more than that from a small picture looks painted, and the plan says so.
"""

from dataclasses import dataclass
from typing import Literal

from mado.core.edits import Editing, Part, see_through
from mado.core.edits import label as edit_label
from mado.core.edits import phrase as edit_phrase
from mado.core.framing import Frame, Shape, frame, note
from mado.core.kind import Kind
from mado.core.looks import Look, changes, label, phrase
from mado.core.models import SCALE, Model, Quality, model_for
from mado.core.quality import phrase as size_phrase
from mado.core.sizes import Size, turned
from mado.core.touches import NONE, Touches

type Method = Literal["ai", "pixels", "smooth", "shrink", "keep"]

PAINTED = 6.0  # this many times bigger or more, from the part kept, looks painted


@dataclass(frozen=True)
class Sizing:
    """The size step, as the Size tab asks for it."""

    size: Size
    shape: Shape = "crop"
    focus: tuple[float, float] | None = None  # the owner's point to crop around, as fractions
    kind: Kind | None = None  # None: as Mado guesses
    quality: Quality | None = None  # None: as this PC starts on
    clean: bool = True  # noise and JPEG blocks out first (Fast's strong model)


@dataclass(frozen=True)
class Styling:
    """The look step, as the Looks tab asks for it: a look at a strength, then its touches."""

    look: Look
    strength: float = 1.0  # 0 to 1
    touches: Touches = NONE
    parts: tuple[Part, ...] = ()  # only on these, picked as Select does; none: the whole picture


@dataclass(frozen=True)
class Recipe:
    sizing: Sizing | None = None
    styling: Styling | None = None
    editing: Editing | None = None  # made first, on the picture at its own size


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
    made_for: str | None  # what the size step makes it for: "TV 8K"; None without one
    styling: Styling | None  # the look made after the size, when it changes the picture
    look: str | None  # the look as History says it, after "with": "Warm film at 60%"
    named: str  # what a new picture's name says: "TV 8K", "Warm film", "TV 8K, Warm film"
    editing: Editing | None = None  # the edits, made first
    edit: str | None = None  # the edits as History says them: "erased a part"
    see_through: bool = False  # the edits leave see-through parts: a cut-out with nothing behind

    @property
    def empty(self) -> bool:
        """Nothing to make: no edits, no size, and no look that changes the picture."""
        return self.method == "keep" and self.styling is None and self.editing is None


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
    sizing = recipe.sizing
    kind = sizing.kind if sizing and sizing.kind else guessed_kind
    quality = (sizing.quality if sizing else None) or starts_on[
        "drawing" if kind == "drawing" else "photo"
    ]
    styling = recipe.styling
    if styling is not None and not changes(styling.look, styling.strength, styling.touches):
        styling = None  # a look that changes nothing isn't a step
    look = phrase(styling.look, styling.strength, styling.touches) if styling else None
    if look and styling and styling.parts:
        look = f"{look} on {'a part' if len(styling.parts) == 1 else 'parts'}"
    looks_as = label(styling.look, styling.strength, styling.touches) if styling else None
    editing = recipe.editing if recipe.editing and recipe.editing.edits else None
    edited = edit_label(editing)
    edit_words = edit_phrase(editing)
    clear = see_through(editing)
    if sizing is None:
        return Plan(
            width=width,
            height=height,
            frame=frame(width, height, width, height, "crop"),
            focus=found_focus,
            focus_found=True,
            note="",
            kind=kind,
            kind_guessed=True,
            quality=quality,
            method="keep",
            model=None,
            scale=1.0,
            how="",
            warning=None,
            made_for=None,
            styling=styling,
            look=look,
            named=", ".join(each for each in (edited, looks_as) if each),
            editing=editing,
            edit=edit_words,
            see_through=clear,
        )
    target = turned(sizing.size, width, height)
    focus = sizing.focus or found_focus
    made = frame(width, height, *target, sizing.shape, focus)
    scale = target[0] / made.canvas.width
    method, model = way(scale, kind, quality, sizing.clean)
    named = ", ".join(each for each in (edited, sizing.size.label, looks_as) if each)
    return Plan(
        width=target[0],
        height=target[1],
        frame=made,
        focus=focus,
        focus_found=sizing.focus is None,
        note=note(made, _phrase(sizing.size), width, height, target),
        kind=kind,
        kind_guessed=sizing.kind is None,
        quality=quality,
        method=method,
        model=model,
        scale=scale,
        how=how(method, kind, sizing.kind is None),
        warning=warning(method, scale, width, height),
        made_for=sizing.size.label,
        styling=styling,
        look=look,
        named=named,
        editing=editing,
        edit=edit_words,
        see_through=clear,
    )


def _phrase(size: Size) -> str:
    if size.group == "other" and size.purpose != "print":
        return "That size"
    return size_phrase(size.purpose, size.name)


def way(scale: float, kind: Kind, quality: Quality, clean: bool) -> tuple[Method, Model | None]:
    """How a picture is made `scale` times bigger, and the model when it's the AI's: only made
    smaller when it's big enough already; pixel art by repeating its pixels; a screenshot
    smoothly; anything else through the model its kind and quality suit."""
    if scale <= 1.0:
        return "shrink", None
    if kind == "pixels":
        return "pixels", None
    if kind == "screenshot":
        return "smooth", None
    return "ai", model_for(kind, quality, clean)


def how(method: Method, kind: Kind, guessed: bool) -> str:
    """What making it bigger does, in a sentence: "Made with the photo model, guessed from the
    picture."."""
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
        case "keep":
            return ""


def warning(method: Method, scale: float, width: int, height: int) -> str | None:
    """What a `width` by `height` picture made `scale` times bigger can't make look real: beyond
    `PAINTED` times, the AI can't find the detail, so it looks painted."""
    if method != "ai" or scale < PAINTED:
        return None
    times = round(scale)
    return (
        f"That's {times} times bigger than the picture's {width} × {height}: beyond "
        f"{SCALE} times, detail can't be found, so it looks painted rather than real."
    )
