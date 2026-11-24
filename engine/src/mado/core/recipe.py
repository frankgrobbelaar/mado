"""A recipe: what the owner asked for, as steps made one after another, and what Mado does to make
it (a plan). Pure.

The steps, in the order they're made: the edits (erased, cut out, blurred behind: the Edit tab,
mado/core/edits.py), the fixes (noise, blur, JPEG blocks and darkness taken out: the Fix tab,
mado/core/fixes.py), the size (cropped or extended, then made bigger: the Size tab), a painting
style (mado/core/painting.py) and a look with its finishing touches, each on the whole picture
or only a part (the Looks tab); then the picture is saved. The fixes are made on the part of the
picture the size keeps, before it grows: noise and blocks come out first, and the upscaler,
given a picture cleaned already, doesn't clean it again (Fast keeps what's left, with its
weak-denoise twin). What the fixes make goes by what the picture measures: a picture that isn't
dark isn't brightened, and a batch's JPEG blocks come out as hard as each JPEG was squeezed. The
painting comes before the look, so a look grades the painted picture, and the touches go on top
of both. Any step can be left out. Each step is a value that says all it does, so a recipe can
be kept by name and run on many pictures ("4K, then Warm film at 60%, then JPEG into Edited").

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
from mado.core.fixes import MOST_STOPS, Fixing, changing, cleans, for_picture
from mado.core.fixes import label as fix_label
from mado.core.fixes import phrase as fix_phrase
from mado.core.framing import Frame, Shape, frame, note
from mado.core.kind import Kind
from mado.core.looks import Look, changes, label, phrase
from mado.core.models import SCALE, Model, Quality, model_for
from mado.core.painting import Painting
from mado.core.painting import changes as paints
from mado.core.painting import label as paint_label
from mado.core.painting import phrase as paint_phrase
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
    fixing: Fixing | None = None  # made next, on the part the size keeps, before it grows
    painting: Painting | None = None  # made after the size, before the look


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
    fixing: Fixing | None = None  # the fixes, made before the picture grows: None when they
    # change nothing in it (a dark photo's fix on a picture that isn't dark)
    fix: str | None = None  # the fixes as History says them: "took out noise"
    fix_quality: Quality = "fast"  # JPEG blocks at Fast (SCUNet) or Best (FBCNN), as decided
    cleaned_first: bool = False  # the fixes clean it, so the upscaler doesn't clean it again
    fix_stops: float = 0.0  # how dark the fixes take it for: as measured, or MOST_STOPS till then
    painting: Painting | None = None  # the painting made after the size, when it changes it

    @property
    def empty(self) -> bool:
        """Nothing to make: no edits, no fixes, no size, no painting and no look that changes
        the picture."""
        return (
            self.method == "keep"
            and self.styling is None
            and self.editing is None
            and self.fixing is None
            and self.painting is None
        )


def plan(
    recipe: Recipe,
    width: int,
    height: int,
    *,
    guessed_kind: Kind,
    found_focus: tuple[float, float],
    starts_on: dict[Literal["photo", "drawing"], Quality],
    fix_starts_on: Quality = "fast",
    stops: float | None = None,
    jpeg_saved_at: int | None = None,
) -> Plan:
    """How a `width` by `height` picture (as it's shown) is made to `recipe`. `guessed_kind` is
    what Mado takes it for, `found_focus` where it found the subject, `starts_on` the quality
    each kind starts on here, and `fix_starts_on` the one JPEG blocks start on (Best once its
    model is downloaded). `stops`: how dark the picture measures, as its edits leave it (None
    till it's measured: planned as if it's dark); `jpeg_saved_at`: its quality, when it's a
    JPEG."""
    sizing = recipe.sizing
    kind = sizing.kind if sizing and sizing.kind else guessed_kind
    quality = (sizing.quality if sizing else None) or starts_on[
        "drawing" if kind == "drawing" else "photo"
    ]
    styling = recipe.styling
    if styling is not None and not changes(styling.look, styling.strength, styling.touches):
        styling = None  # a look that changes nothing isn't a step
    painting = recipe.painting if recipe.painting and paints(recipe.painting) else None
    look = said_with(painting, styling)
    looks_as = ", ".join(
        each
        for each in (
            paint_label(painting) if painting else None,
            label(styling.look, styling.strength, styling.touches) if styling else None,
        )
        if each
    )
    editing = recipe.editing if recipe.editing and recipe.editing.edits else None
    edited = edit_label(editing)
    edit_words = edit_phrase(editing)
    clear = see_through(editing)
    dark = MOST_STOPS if stops is None else stops
    fixing = for_picture(
        recipe.fixing if recipe.fixing and recipe.fixing.on else None, jpeg_saved_at
    )
    if not changing(fixing, dark):
        fixing = None  # the fixes change nothing in this picture: no step
    fix_quality = (fixing.jpeg_quality if fixing else None) or fix_starts_on
    fixed_as = fix_label(fixing, dark)
    fix_words = fix_phrase(fixing, dark)
    cleaned = cleans(fixing, dark)
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
            named=", ".join(each for each in (edited, fixed_as, looks_as) if each),
            editing=editing,
            edit=edit_words,
            see_through=clear,
            fixing=fixing,
            fix=fix_words,
            fix_quality=fix_quality,
            cleaned_first=cleaned,
            fix_stops=dark,
            painting=painting,
        )
    target = turned(sizing.size, width, height)
    focus = sizing.focus or found_focus
    made = frame(width, height, *target, sizing.shape, focus)
    scale = target[0] / made.canvas.width
    method, model = way(scale, kind, quality, sizing.clean and not cleaned)
    named = ", ".join(each for each in (edited, fixed_as, sizing.size.label, looks_as) if each)
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
        fixing=fixing,
        fix=fix_words,
        fix_quality=fix_quality,
        cleaned_first=cleaned,
        fix_stops=dark,
        painting=painting,
    )


def said_with(painting: Painting | None, styling: Styling | None) -> str | None:
    """A painting and a look as Save and History say them, after "with": "After Hokusai at 80%
    and Warm film at 60%" (", and" when the painting's words have a comma of their own), each
    "on a part" when it is; None with neither."""
    looked = phrase(styling.look, styling.strength, styling.touches) if styling else None
    if looked and styling and styling.parts:
        looked = f"{looked} {_on(styling.parts)}"
    painted = (
        paint_phrase(painting, on=_on(painting.parts) if painting.parts else "")
        if painting
        else None
    )
    if painted and looked:
        return f"{painted}{',' if ',' in painted else ''} and {looked}"
    return painted or looked


def _on(parts: tuple[object, ...]) -> str:
    return f"on {'a part' if len(parts) == 1 else 'parts'}"


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
