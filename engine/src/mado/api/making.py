"""Making a picture to a recipe, as the Size, Looks, Edit, Fix and Depth tabs ask: the sizes
there are, the owner's screens, the plan for a recipe (its shape, model, depth tools, painting,
look, edits, fixes, time and quality), a preview (all of it fitted, or a part at full detail), the
name it would be saved as, what the Fix tab suggests, and making it, as a job (mado/api/jobs.py).
A recipe is its edits, its fixes, a size step, a depth step, a painting step and a look step, any
of them left out, made by one Save."""

import io
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from math import ceil, floor
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import numpy.typing as npt
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from PIL import Image
from pydantic import Field

from mado import own_looks, own_styles
from mado.ai import BIREFNET, COLOURER, DETECTOR, Ai
from mado.api.common import (
    ApiModel,
    Copies,
    Database,
    Depthing,
    Editors,
    Models,
    Seeing,
    SetAside,
    Toolbox,
    Working,
)
from mado.api.depth import DepthStepIn, depthing_of
from mado.api.editing import changed
from mado.api.edits import EditIn, EditStepIn, PartIn, editing_of, edits_of, picked
from mado.api.fixes import FixesOut, FixStepIn, fixing_of
from mado.api.jobs import Job, job_of
from mado.api.looks import LookIn
from mado.api.restore import RestoreStepIn, rechecked, restoring_of, tied
from mado.api.styles import UNREAD_STYLE, PaintHereIn
from mado.core.depth import DepthError, depthing_json
from mado.core.edits import Edit, EditError, Editing, Part, as_json
from mado.core.estimate import key
from mado.core.fixes import (
    LEAST_STOPS,
    FixError,
    blocks_suggested,
    dark_suggested,
    fixing_json,
    unchanged,
)
from mado.core.fixes import models_for as fix_models
from mado.core.framing import Box, Shape
from mado.core.kind import Kind
from mado.core.models import Quality
from mado.core.naming import EXTENSIONS, aside_name, new_name, replacement_name
from mado.core.painting import Painting, Style, enlarged, working_size
from mado.core.quality import Format, about_bytes, colour_words, suited
from mado.core.recipe import Plan, Recipe, Sizing, Styling, asks_nothing, hdr_lost
from mado.core.restore import (
    MOST_MASK,
    RestoreError,
    Restoring,
    changing,
    covers,
    restoring_json,
)
from mado.core.sizes import (
    MAX_SIDE,
    PRINTS,
    SCREENS,
    Size,
    SizeError,
    remember,
    resolve,
    yours,
)
from mado.depth import Depths, Worked, joined_on, work_out
from mado.directml import ModelError
from mado.editing import EditingError, Editor, cut_quality, picture_key
from mado.fixing import MARGIN, Measure, fixed
from mado.looks import Placement, seed_of, styled
from mado.making import (
    AS_IS_NEW,
    GREY_MODES,
    NO_RAW_REPLACE,
    Picture,
    Seen,
    Sight,
    canvas_of,
    depth_seconds,
    estimated,
    fix_seconds,
    only_on,
    paint,
    picture_of,
    placed,
    planned,
    restore_seconds,
    screens_kept,
    split_alpha,
    waiting_for,
)
from mado.pictures import NeedsFfmpegError, NeedsReaderError, PictureGoneError, UnreadableError
from mado.previews import Previews, Source, version
from mado.quarantine import Quarantine
from mado.restoring import Prepared, RestoringError, too_much
from mado.system import pictures_folder
from mado.upscale import (
    Pixels,
    StoppedError,
    bled,
    by_pixels,
    resize_alpha,
    smaller,
    smoothly,
    through_model,
)

router = APIRouter()
log = logging.getLogger(__name__)

_MOST_PREVIEW = 4_000_000  # pixels a preview of a part may have
_MARGIN = 16  # pixels of the picture around a part previewed, so its edges see what's beside
_NOTHING = "Pick a size, a style or a look first: as it is, there's nothing to make."
_ASIDE = (
    "It waits in Mado's quarantine, so Mado opens it to look at only. Put it back from History "
    "to make something of it."
)
_NO_ORIGINAL = "A pasted picture has no original to replace: save it as a new picture."
_NO_FOLDER = "Choose a folder for it: a pasted picture isn't in any of your folders yet."


class SizeOut(ApiModel):
    id: str
    name: str
    width: int
    height: int
    group: Literal["screens", "yours", "prints", "other"]
    purpose: str  # phone, tablet, laptop, monitor, ultrawide, tv, print, screen
    label: str  # what a new picture's name says it was made for


class Sizes(ApiModel):
    screens: list[SizeOut]  # the devices, as the Size tab draws them
    yours: list[SizeOut]  # the owner's screens Mado remembers
    prints: list[SizeOut]  # at 300 dpi


class SeenScreen(ApiModel):
    width: int = Field(gt=0, le=MAX_SIDE)
    height: int = Field(gt=0, le=MAX_SIDE)
    main: bool = False


class ScreensSeen(ApiModel):
    seen: Annotated[list[SeenScreen], Field(max_length=16)]  # a PC has a few


class SizeIn(ApiModel):
    """The size step, as the Size tab asks for it."""

    size: str  # an id from /sizes, or "other-5000x3000", "other-20x30cm"
    shape: Shape = "crop"
    focus: Annotated[list[float], Field(min_length=2, max_length=2)] | None = None
    kind: Kind | None = None  # None: as Mado guesses
    quality: Quality | None = None  # None: as this PC starts on
    clean: bool = True


class LookHereIn(LookIn):
    """The look step on a picture's page: on the whole picture, or only on parts picked as Select
    picks them, on the picture as its edits left it."""

    parts: Annotated[list[PartIn], Field(default_factory=list[PartIn], max_length=32)]


class RecipeIn(ApiModel):
    """A recipe: the edits, restoring, the fixes, the size step, the depth step, the painting
    step, then the look step; any can be left out."""

    edit: EditStepIn | None = None
    restore: RestoreStepIn | None = None
    fix: FixStepIn | None = None
    size: SizeIn | None = None
    depth: DepthStepIn | None = None
    paint: PaintHereIn | None = None
    look: LookHereIn | None = None


class Fraction(ApiModel):
    """A part of the picture, as fractions of its width and height (extending, a canvas starts
    before the picture and ends after it)."""

    x: float
    y: float
    width: float
    height: float


class Need(ApiModel):
    id: str  # the download's: "realesrgan-x4plus", "lama"
    name: str
    size: int  # bytes


class PlanOut(ApiModel):
    width: int  # the size made
    height: int
    label: str  # what the size makes it for: "TV 8K"; empty with no size
    shape: Shape
    sides: Literal["none", "top and bottom", "sides"]
    kept: Fraction  # the part of the picture kept
    canvas: Fraction  # what's made
    focus: list[float]  # the point the crop is around
    focus_found: bool  # Mado found it; the owner didn't say
    note: str  # what the shape does, in a sentence
    kind: Kind
    kind_guessed: bool
    quality: Quality
    method: Literal["ai", "pixels", "smooth", "shrink", "keep"]  # keep: no size, its pixels kept
    model: str | None  # the model's name, when AI makes it
    how: str  # "Made with the photo model, guessed from the picture."
    warning: str | None  # what it can't make look real
    clean_matters: bool  # cleaning first changes the model (Fast keeps grain without it)
    cleaned_first: bool  # the fixes take noise and blocks out first, so the model doesn't again
    look: str | None  # the look, as Save says it after "with": "Warm film at 60%"
    edit: str | None  # the edits, as Save and History say them: "erased a part"
    fix: str | None  # the fixes, as Save and History say them: "took out noise"
    fix_quality: Quality | None  # JPEG blocks at Fast or Best, as decided; None without them
    fix_seconds: float  # of `seconds`, about how long the fixes take
    fix_place: Literal["card", "processor"] | None  # where the fixes' models run; None without
    depth: str | None  # the depth tools, as Save and History say them: "portrait blur at f/2.8"
    depth_seconds: float  # of `seconds`, about how long the depth tools take
    depth_place: Literal["card", "processor"] | None  # where the depth model runs; None without
    restore: str | None  # restoring, as Save and History say it: "filled its scratches and dust"
    restore_seconds: float  # of `seconds`, about how long restoring takes
    # where the detector and DDColor run (the processor when the card has no room left for them);
    # None without restoring that needs them
    restore_place: Literal["card", "processor"] | None
    restore_covers: float | None  # how much of the picture the scratches' mask covers, 0 to 1
    scratch_place: (
        Literal["card", "processor"] | None
    )  # where the scratches are found; None without
    paint_place: Literal["card", "processor"] | None  # where its painting is made; None without
    paint_note: str | None  # a painting made far bigger than it's painted: its strokes soft close
    seconds: float  # about how long it takes here
    place: Literal["card", "processor"]
    measured: bool  # the time is this PC's own, not a guess
    format: Format  # what suits it
    format_quality: int | None
    fits: str  # "What every TV shows."
    colour: str  # "sRGB", "Display P3"
    bytes: int  # about how big it comes out
    see_through: bool  # it has see-through parts, which JPEG makes white
    nothing_behind: bool  # a cut-out with nothing behind it: only PNG and WebP keep it
    # An HDR photo's gain map: "kept" through the recipe (in JPEG or AVIF), "lost" (`hdr_why`
    # says why), "none" for a picture without one Mado reads
    hdr: Literal["none", "kept", "lost"] = "none"
    hdr_why: str | None = None
    as_is: bool = False  # the recipe asks for nothing: Save saves the picture as it is
    needs: list[Need]  # downloads it waits for


class Region(ApiModel):
    """A part of the picture made, in its pixels."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Fit(ApiModel):
    width: int = Field(gt=0, le=4096)
    height: int = Field(gt=0, le=4096)


class PreviewIn(ApiModel):
    recipe: RecipeIn
    side: Literal["before", "after"] = "after"
    region: Region | None = None  # a part at full detail
    fit: Fit | None = None  # or all of it, this big at most


class SavingAsk(ApiModel):
    recipe: RecipeIn
    how: Literal["new", "replace"] = "new"
    format: Format
    quality: int | None = Field(default=None, ge=1, le=100)
    folder: str | None = None
    keep_colours: bool = True


class SavingName(ApiModel):
    name: str  # what it would be saved as
    folder: str
    taken: str | None  # the name it would have had, already there
    taken_at: str | None  # when that one was made, local
    bytes: int  # about how big it comes out
    colour: str


class SavingIn(ApiModel):
    how: Literal["new", "replace"] = "new"
    format: Format
    quality: int | None = Field(default=None, ge=1, le=100)
    folder: str | None = None  # new pictures: into this folder; None beside the original
    keep_camera: bool = True
    keep_colours: bool = True
    keep_location: bool = False
    keep_hdr: bool = True  # an HDR photo's gain map, in a format that holds one
    always: bool = False  # Save starts on this way from now on


class MakeIn(ApiModel):
    recipe: RecipeIn
    saving: SavingIn


@router.get("/sizes")
def sizes(conn: Database) -> Sizes:
    """The sizes a picture can be made for: the devices' screens, the owner's own and prints."""
    return Sizes(
        screens=[_size(each) for each in SCREENS],
        yours=[_size(each) for each in yours(screens_kept(conn))],
        prints=[_size(each) for each in PRINTS],
    )


@router.post("/screens")
def seen_screens(body: ScreensSeen, conn: Database) -> list[SizeOut]:
    """Remembers this PC's screens, as the window sees them, and says which Mado knows now."""
    kept = remember(screens_kept(conn), [(s.width, s.height, s.main) for s in body.seen])
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('screens', ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (json.dumps([{"name": s.name, "width": s.width, "height": s.height} for s in kept]),),
        )
    return [_size(each) for each in yours(kept)]


@router.post("/pictures/{picture_id}/plan")
def plan_for(
    picture_id: int,
    body: RecipeIn,
    conn: Database,
    sight: Seeing,
    copies: Copies,
    ai: Models,
    toolbox: Toolbox,
    editor: Editors,
) -> PlanOut:
    """How a picture would be made to a recipe: its shape, the model, its look, about how long it
    takes here and how it would be saved. A recipe with no step at all (the picture as it is,
    which its page asks about as it opens) is planned at a glance, without decoding it whole."""
    if not body.model_dump(exclude_none=True):
        picture, seen, source = _glanced(conn, sight, copies, picture_id)
    else:
        picture, seen, source = _seen(conn, sight, picture_id)
    recipe = _recipe(body, conn, source.version, picture.path.name)
    as_is = asks_nothing(recipe)  # as asked: scratches found nowhere aren't saving it as it is
    here = ai.where()
    made = _planned(recipe, picture, source, seen, sight, ai, editor)
    recipe, made, covers = _emptied(recipe, made, picture, source, seen, sight, ai, editor)
    fixers = fix_models(made.fixing, made.fix_quality)
    fix_on = ai.fix_place(fixers) if fixers else None
    painting = made.painting
    paint_on = ai.painter.place(painting.style) if painting is not None else None
    depth_on = ai.depth_place()
    purpose = recipe.sizing.size.purpose if recipe.sizing else "screen"
    clear = seen.alpha or made.see_through
    # A cut-out with nothing behind it keeps its nothing: PNG, or WebP when it was WebP.
    kept_as = picture.format if not made.see_through or picture.format == "WebP" else None
    suits = suited(purpose, made.kind, kept_as, alpha=clear)
    if as_is and suits.format == "JPEG" and seen.jpeg is not None:
        suits = replace(suits, quality=min(max(seen.jpeg, 50), 100))  # as it was saved
    frame = made.frame
    names = {item.id: item for item, _ in toolbox.status()}
    measured = made.model is not None and key(made.model.id, here.place) in here.speeds
    restoring = made.restoring
    restore_on = (ai.restore_place(DETECTOR), ai.restore_place(COLOURER))
    # Where restoring runs: on the processor when a model it uses does (LaMa runs where this PC
    # runs the models); faded colours alone use none.
    find_on = restore_on[0] if restoring is not None and restoring.scratches is not None else None
    colour_on = restore_on[1] if restoring is not None and restoring.colour else None
    in_use = [place for place in (find_on, colour_on) if place is not None]
    restore_place = ("processor" if "processor" in in_use else here.place) if in_use else None
    missing = waiting_for(made, ai)
    lost = hdr_lost(made) if seen.hdr == "hdr" else None
    return PlanOut(
        width=made.width,
        height=made.height,
        label=made.made_for or "",
        shape=frame.shape,
        sides=frame.sides,
        kept=_fraction(frame.kept, seen),
        canvas=_fraction(frame.canvas, seen),
        focus=[made.focus[0], made.focus[1]],
        focus_found=made.focus_found,
        note=made.note,
        kind=made.kind,
        kind_guessed=made.kind_guessed,
        quality=made.quality,
        method=made.method,
        model=made.model.name if made.model else None,
        how=made.how,
        warning=made.warning,
        clean_matters=made.method == "ai" and made.quality == "fast" and not made.cleaned_first,
        cleaned_first=made.cleaned_first,
        look=made.look,
        edit=made.edit,
        fix=made.fix,
        fix_quality=made.fix_quality if made.fixing and made.fixing.jpeg is not None else None,
        fix_seconds=fix_seconds(made, here, fix_on),
        fix_place=fix_on if made.fixing is not None else None,
        depth=made.depth,
        depth_seconds=depth_seconds(made, depth_on, ai.edit_place(BIREFNET)),
        depth_place=depth_on if made.depthing is not None else None,
        restore=made.restore,
        restore_seconds=restore_seconds(made, here.place, restore_on),
        restore_place=restore_place,
        restore_covers=covers,
        scratch_place=find_on,
        paint_place=paint_on,
        paint_note=enlarged(painting, made.width, made.height) if painting is not None else None,
        seconds=estimated(
            made,
            here,
            ai.edit_place(BIREFNET),
            fix_on,
            paint_on=paint_on,
            depth_on=depth_on,
            restore_on=restore_on,
        ),
        place=here.place,
        measured=measured,
        format=suits.format,
        format_quality=suits.quality,
        fits=suits.fits,
        colour=colour_words(seen.profile, keep=True),
        bytes=about_bytes(suits.format, suits.quality, made.kind, made.width * made.height),
        see_through=clear,
        nothing_behind=made.see_through,
        hdr="none" if seen.hdr != "hdr" else "lost" if lost else "kept",
        hdr_why=lost,
        as_is=as_is,
        needs=[
            Need(id=each, name=names[each].name, size=names[each].size or 0)
            for each in missing
            if each in names
        ],
    )


def _laid_round(
    pixels: Pixels, prepared: Prepared, box: Box, margin: int, editor: Editor
) -> tuple[Pixels, bytes | None]:
    """The picture's pixels (as its edits leave it, its scratches filled) with colour and faded
    colours laid on round a part (`box`, in its pixels, `margin` more each way): only what the
    part is made from. And its colour profile, as laying colour leaves it (a grey picture's own
    goes once it's coloured)."""
    height, width = pixels.shape[:2]
    left, top = max(0, floor(box.x) - margin), max(0, floor(box.y) - margin)
    right = min(width, ceil(box.x + box.width) + margin)
    bottom = min(height, ceil(box.y + box.height) + margin)
    crop = prepared.picture.crop((left, top, right, bottom))
    crop.info = dict(prepared.picture.info)
    shown = editor.restorer.shown(prepared, crop, (left, top, right, bottom))
    out = pixels.copy()
    out[top:bottom, left:right] = np.asarray(shown.convert("RGBA" if out.shape[2] == 4 else "RGB"))
    profile = shown.info.get("icc_profile")
    return out, profile if isinstance(profile, bytes) else None


def _emptied(
    recipe: Recipe,
    made: Plan,
    picture: Picture,
    source: Source,
    seen: Seen,
    sight: Sight,
    ai: Ai,
    editor: Editor,
) -> tuple[Recipe, Plan, float | None]:
    """The recipe and its plan as the scratches' mask leaves them, and how much of the picture
    the mask covers (None without scratches, or while the detector can't run). A mask covering
    nothing (Mado found none, and none was painted) fills nothing: restoring goes on without its
    scratches, and with nothing else on there's nothing to restore, so Save, History and the
    picture's new name never say scratches were filled."""
    restoring = made.restoring
    if restoring is None or restoring.scratches is None or DETECTOR in waiting_for(made, ai):
        return recipe, made, None
    share = _covers(picture, source, made, sight, editor)
    if share != 0:
        return recipe, made, share
    rest = replace(restoring, scratches=None)
    unscratched = replace(recipe, restoring=rest if changing(rest) else None)
    return unscratched, _planned(unscratched, picture, source, seen, sight, ai, editor), share


def _covers(
    picture: Picture, source: Source, made: Plan, sight: Sight, editor: Editor
) -> float | None:
    """How much of the picture the scratches' mask covers, as found and painted (the detector run
    now when it hasn't been yet); None when the detector can't run."""
    assert made.restoring is not None  # noqa: S101 - asked for with scratches
    edits = made.editing.edits if made.editing else ()
    key = picture_key(picture.path, source.version)
    try:
        decoded = sight.picture(picture, source.version)
        mask = editor.scratch_mask(decoded, key, edits, made.restoring)
    except ModelError:
        return None
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    except EditingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return covers(mask)  # as it is: one dab of the finest brush is something to fill


_PREVIEWS: dict[int | str, dict[str, object]] = {
    200: {"content": {"image/jpeg": {}, "image/webp": {}}}
}


@router.post("/pictures/{picture_id}/preview", response_class=Response, responses=_PREVIEWS)
def preview(
    picture_id: int,
    body: PreviewIn,
    conn: Database,
    sight: Seeing,
    ai: Models,
    copies: Copies,
    editor: Editors,
    depths: Depthing,
) -> Response:
    """A preview of the picture made: all of it no bigger than `fit` (from its view the size of a
    screen), or a part of it at full detail (`region`); before (the picture only stretched) or
    after (made, as Save would, with its depth tools, look and touches). All of it comes as JPEG,
    quick to make as looks are gone through (WebP when it has see-through parts); a part as
    WebP."""
    picture, seen, source = _seen(conn, sight, picture_id)
    recipe = _recipe(body.recipe, conn, source.version, picture.path.name)
    made = _planned(recipe, picture, source, seen, sight, ai, editor)
    missing = waiting_for(made, ai)
    upscaler = made.model.download if made.model is not None else None
    fixers = {model.id for model in fix_models(made.fixing, made.fix_quality)}
    painter = ai.painter.needs(made.painting.style) if made.painting is not None else None
    # Extending and the edits need their models on either side; the upscaler and the fixes' only
    # for a part made at full detail (all of it shows only the brightening, which needs none);
    # a painting style's network and the depth tools' only after.
    for each in missing:
        if each == upscaler or each in fixers:
            needed = body.region is not None and body.side == "after"
        elif each == painter or (each in _DEPTH_MODELS and made.depthing is not None):
            needed = body.side == "after"
        else:
            needed = True
        if needed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "It needs a model Mado downloads the first time it's asked for: download it first.",
            )
    began = time.perf_counter()
    try:
        image = _previewed(picture, source, seen, made, body, sight, ai, copies, editor, depths)
    except ModelError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except (EditingError, RestoringError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    except StoppedError:  # a part's fixes or depth, stopped as a newer preview of it came
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "A newer preview took this one's place."
        ) from None
    except OSError as error:  # keeping the copy it's made from, not the picture
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Mado couldn't keep a copy of it to show in its data folder: "
            f"{error.strerror or error}. Your picture is as it was.",
        ) from None
    out = io.BytesIO()
    profile = image.info.get("icc_profile")  # its colours, so wide ones show as wide
    kept = {"icc_profile": profile} if isinstance(profile, bytes) else {}
    if body.region is None and image.mode in ("RGB", "L"):
        # JPEG takes a few milliseconds where WebP takes a hundred and more on a grainy picture.
        image.save(out, format="JPEG", quality=92, subsampling=0, **kept)
        media = "image/jpeg"
    else:
        image.save(out, format="WEBP", quality=90, method=2, **kept)
        media = "image/webp"
    took = f"{time.perf_counter() - began:.2f}"
    return Response(out.getvalue(), media_type=media, headers={"X-Made-In": took})


@router.get("/pictures/{picture_id}/fixes")
def fixes_for(picture_id: int, conn: Database, sight: Seeing) -> FixesOut:
    """What the Fix tab suggests fixing, from what Mado can measure cheaply and reliably: a
    JPEG's own quality from its tables, and how dark the picture is."""
    picture, seen, source = _seen(conn, sight, picture_id)
    quality = seen.jpeg
    try:
        measured = sight.measured(
            (str(picture.path).casefold(), source.version, None, None),
            lambda: sight.picture(picture, source.version),
        )
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    stops = round(measured.stops, 1) if measured.stops >= LEAST_STOPS else 0.0
    return FixesOut(
        jpeg_quality=quality,
        blocks=blocks_suggested(quality),
        stops=stops,
        dark=dark_suggested(stops),
        grey=seen.grey,
        see_through=seen.alpha,
        colour=colour_words(seen.profile, keep=True),
        megapixels=round(seen.width * seen.height / 1e6, 1),
        colours=seen.colours,
        tone=seen.tone,
    )


_PNG: dict[int | str, dict[str, object]] = {200: {"content": {"image/png": {}}}}


class ScratchesAsk(ApiModel):
    """What the scratch detector is to look at: the picture as `edits` leave it, as it was at
    `version`."""

    version: str
    edits: Annotated[list[EditIn], Field(default_factory=list[EditIn], max_length=64)]


@router.post("/pictures/{picture_id}/scratches", response_class=Response, responses=_PNG)
def scratches(
    picture_id: int, body: ScratchesAsk, conn: Database, sight: Seeing, editor: Editors
) -> Response:
    """What the scratch detector finds on the picture as its edits leave it, as a mask at the
    mask's size (PNG, white where it found scratches and dust), kept by the picture's version:
    how long finding took (`X-Made-In`), how much of the picture it covers (`X-Found`, 0 to 1),
    where it ran (`X-Place`) and how long it waited for the graphics card (`X-Waited`). 409 while
    the detector isn't downloaded, or once the picture changed."""
    picture, _, source = _seen(conn, sight, picture_id)
    if body.version != source.version:
        raise HTTPException(status.HTTP_409_CONFLICT, rechecked(picture.path.name))
    try:
        editing = edits_of(body.edits, body.version)
    except EditError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    key = picture_key(picture.path, source.version)
    try:
        decoded = sight.picture(picture, source.version)
        found = editor.found(decoded, key, editing.edits)
    except ModelError as error:
        downloaded = editor.restorer.ready()
        code = status.HTTP_503_SERVICE_UNAVAILABLE if downloaded else status.HTTP_409_CONFLICT
        raise HTTPException(code, str(error)) from None
    except EditingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    out = io.BytesIO()
    Image.fromarray(found.mask, "L").save(out, format="PNG", compress_level=1)
    headers = {
        "X-Made-In": f"{found.seconds:.2f}",
        "X-Found": repr(covers(found.mask)),  # a speck found is never said as nothing
        "X-Place": found.place or "",
        "X-Waited": f"{found.waited:.2f}",
    }
    return Response(out.getvalue(), media_type="image/png", headers=headers)


@router.post("/pictures/{picture_id}/saving")
def saving_name(
    picture_id: int,
    body: SavingAsk,
    conn: Database,
    sight: Seeing,
    ai: Models,
    editor: Editors,
) -> SavingName:
    """What a picture made would be saved as, and about how big it would be: a pasted one, into
    the owner's Pictures folder till another is chosen."""
    picture, seen, source = _seen(conn, sight, picture_id)
    pasted = _pasted(conn, picture_id)
    if body.how == "new" and not body.folder and pasted:
        body = body.model_copy(update={"folder": str(pictures_folder())})
    recipe = _recipe(body.recipe, conn, source.version, picture.path.name)
    made = _planned(recipe, picture, source, seen, sight, ai, editor)
    if made.empty and not (pasted or asks_nothing(recipe)):  # saved as it is: something to save
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _nothing(recipe))
    extension = EXTENSIONS[body.format]
    original = picture.path
    taken: str | None = None
    if body.how == "new":
        folder = Path(body.folder) if body.folder else original.parent
        first = new_name(original.stem, made.named, extension, lambda _name: False)
        name = new_name(original.stem, made.named, extension, _taken_in(folder))
        taken = first if name != first else None
    else:
        folder = original.parent
        name = replacement_name(original.name, extension)
        if (folder / name).exists() and folder / name != original:
            taken = name
            name = aside_name(name, _taken_in(folder))
    return SavingName(
        name=name,
        folder=str(folder),
        taken=taken,
        taken_at=_made_at(folder / taken) if taken else None,
        bytes=about_bytes(body.format, body.quality, made.kind, made.width * made.height),
        colour=colour_words(seen.profile, keep=body.keep_colours),
    )


@router.post("/pictures/{picture_id}/make", status_code=status.HTTP_202_ACCEPTED)
def make(
    picture_id: int,
    body: MakeIn,
    conn: Database,
    sight: Seeing,
    ai: Models,
    jobs: Working,
    aside: SetAside,
    editor: Editors,
) -> Job:
    """Makes a picture to its recipe and saves it as the owner chose, as a job: its progress,
    the time left and Cancel come from /jobs. A picture waiting in a quarantine is opened to look
    at only, and a pasted one is saved only as a new picture, into a folder chosen."""
    _may_save(conn, picture_id, body.saving, aside)
    picture, seen, source = _seen(conn, sight, picture_id)
    recipe = _recipe(body.recipe, conn, source.version, picture.path.name)
    made = _planned(recipe, picture, source, seen, sight, ai, editor)
    # Saved as it is: nothing asked for (or a paste whose steps change nothing), in the format
    # chosen, always as a new picture.
    asked_nothing = asks_nothing(recipe)
    recipe, made, share = _emptied(recipe, made, picture, source, seen, sight, ai, editor)
    if share is not None and share > MOST_MASK:  # filling it would invent most of it
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, too_much(share))
    as_is = made.empty and (asked_nothing or _pasted(conn, picture_id))
    if made.empty and not as_is:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _nothing(recipe))
    if as_is and body.saving.how == "replace":
        raise HTTPException(status.HTTP_409_CONFLICT, AS_IS_NEW)
    if made.see_through and body.saving.format not in ("PNG", "WebP"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A cut-out with nothing behind it keeps its see-through parts only as PNG or WebP: "
            "pick one of those.",
        )
    if waiting_for(made, ai):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "It needs a model Mado downloads the first time it's asked for: download it first.",
        )
    saving = body.saving
    if saving.how == "new" and saving.folder and not Path(saving.folder).is_dir():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{saving.folder} isn't there: its drive may be unplugged. Choose another folder.",
        )
    # A picture saved as it is, or a camera RAW, can only be a new picture: no choice of the
    # owner's to keep as the way Save starts.
    if saving.always and not as_is and picture.kind != "raw":
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('save_first', ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (json.dumps(saving.how),),
            )
    asked = body.recipe
    # What the plan decided, so the job makes what was previewed: the picture's kind, Fast or
    # Best, and the crop's point, even if this PC's choice changes before it starts.
    decided = (
        asked.size.model_copy(
            update={"kind": made.kind, "quality": made.quality, "focus": list(made.focus)}
        )
        if asked.size is not None
        else None
    )
    look = asked.look if made.styling is not None else None  # a look that changes nothing isn't
    painted = asked.paint if made.painting is not None else None  # nor a painting at nought
    # The depth tools as the plan decided them: the subject's edges at the quality previewed.
    depthing = made.depthing
    if depthing is not None and depthing.portrait is not None and depthing.portrait.quality is None:
        depthing = replace(depthing, portrait=replace(depthing.portrait, quality=cut_quality(ai)))
    # The fixes as the plan decided them too: JPEG blocks at the model previewed.
    fixing = (
        replace(made.fixing, jpeg_quality=made.fix_quality)
        if made.fixing is not None and made.fixing.jpeg is not None
        else made.fixing
    )
    order = {
        "recipe": {
            "edit": as_json(recipe.editing) if recipe.editing else None,  # its version too
            "restore": restoring_json(made.restoring),  # the scratches' version too
            "fix": fixing_json(fixing),
            "size": decided.model_dump(by_alias=True) if decided else None,
            "depth": depthing_json(depthing),
            "paint": painted.model_dump(by_alias=True) if painted else None,
            "look": look.model_dump(by_alias=True) if look else None,
        },
        "saving": saving.model_dump(by_alias=True, exclude={"always"}),
        "label": made.made_for,
        "look": made.look,
        "edit": made.edit,
        "fix": made.fix,
        "depth": made.depth,
        "restore": made.restore,
        "estimate": round(made.scale, 3),
        "as_is": as_is,
    }
    job_id = jobs.add(conn, picture_id, picture.path, order)
    return job_of(conn, jobs, job_id)


def _previewed(
    picture: Picture,
    source: Source,
    seen: Seen,
    made: Plan,
    body: PreviewIn,
    sight: Sight,
    ai: Models,
    copies: Previews,
    editor: Editor,
    depths: Depths,
) -> Image.Image:
    """The preview as asked for: all of it fitted, or a part at full detail; the picture as its
    edits left it; after, its depth tools, worked out on the whole picture made, then its
    painting, then its look and touches where they fall on the picture made, each only on a part
    when it says so."""
    looked = made.styling if body.side == "after" else None
    painting = made.painting if body.side == "after" else None
    seed = seed_of(picture.path)
    target = (made.width, made.height)
    edits = made.editing.edits if made.editing else ()
    parts = made.styling.parts if made.styling else ()
    key = picture_key(picture.path, source.version)
    if body.region is None:
        fit = body.fit or Fit(width=1600, height=1600)
        scale = min(fit.width / target[0], fit.height / target[1], 1.0)
        size = (max(1, round(target[0] * scale)), max(1, round(target[1] * scale)))
        base = sight.fitted(
            (
                str(picture.path).casefold(),
                source.version,
                made.frame,
                size,
                made.editing,
                made.restoring,
                made.fixing,
                made.fix_quality,
            ),
            lambda: _fitted(picture, source, seen, made, size, sight, ai, copies, editor),
        )
        if made.depthing is not None and body.side == "after":
            whole = sight.picture(picture, source.version)
            worked = _worked(picture, source, seen, made, base, whole, depths, editor, ai)
            base = joined_on(
                base, (0, 0, base.width, base.height), worked, mask=_subject_on(
                    whole, made, base.size, None, key, editor, ai
                ),
            )  # fmt: skip
        if painting is not None:
            working = _working(
                painting.style, picture, source, seen, made, sight, ai, copies, editor
            )
            painted = paint(base, painting, ai.painter, working=working)
            if painting.parts:
                whole = sight.picture(picture, source.version)
                mask = editor.look_mask(whole, key, edits, painting.parts)
                painted = only_on(painted, base, placed(mask, made, base.size))
            base = painted
        if looked is None:
            return base
        shown = styled(base, looked, seed=seed, placement=Placement.fitted(base.size, target))
        if parts:
            whole = sight.picture(picture, source.version)
            mask = editor.look_mask(whole, key, edits, parts)
            shown = only_on(shown, base, placed(mask, made, base.size))
        return shown
    region = body.region
    if region.width * region.height > _MOST_PREVIEW:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That part is too big to preview at once."
        )
    if region.x + region.width > target[0] or region.y + region.height > target[1]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That part is outside the picture made."
        )
    # A classic means reaches past the part (its lines and strokes see what's beside them): the
    # part is made with a margin, drawn, then cut back.
    reach = min(target) / 100
    grown = region
    if painting is not None and painting.style.kind == "classic":
        margin = ceil(_CLASSIC_REACHES * reach)
        left, top = max(0, region.x - margin), max(0, region.y - margin)
        right = min(target[0], region.x + region.width + margin)
        bottom = min(target[1], region.y + region.height + margin)
        grown = Region(x=left, y=top, width=right - left, height=bottom - top)
    version_ = _version_of(picture)
    decoded = sight.picture(picture, version_)
    restoring = made.restoring
    changed = bool(edits) or restoring is not None
    extending = made.frame.shape == "extend" and made.frame.sides != "none"
    # Colour and faded colours are laid only round the part, on what's kept (the picture with its
    # scratches filled, DDColor's colours, the levels): a strength moved never lays them on all of
    # it. An extended canvas is drawn by LaMa from the picture as restoring leaves it, whole.
    prepared = (
        editor.prepared(decoded, key, edits, restoring)
        if restoring is not None and (restoring.colour or restoring.faded) and not extending
        else None
    )
    if prepared is not None:
        state = prepared.picture
    else:
        state = editor.state(decoded, key, edits, restoring=restoring) if changed else decoded
    profile = state.info.get("icc_profile")
    offset = (0, 0)
    if extending:
        pixels, kept, offset = sight.extended(
            picture,
            version_,
            made.frame.canvas,
            ai.filler,
            image=state if changed else None,
            also=(made.editing, restoring),
        )
    else:
        # A cut-out's see-through parts as a fourth channel: worked out round the part below,
        # never over the whole picture.
        see_through = "A" in state.getbands()
        pixels = np.asarray(state.convert("RGBA" if see_through else "RGB"))
        kept = made.frame.kept
    kx, ky = kept.width / target[0], kept.height / target[1]  # the picture's pixels a made one

    def box_of(asked: Region) -> Box:
        return Box(
            kept.x + asked.x * kx, kept.y + asked.y * ky, asked.width * kx, asked.height * ky
        )

    part = box_of(region)
    size = (region.width, region.height)
    if body.side == "before":
        stretched = Image.fromarray(pixels).resize(
            size,
            Image.Resampling.BICUBIC,
            box=(part.x, part.y, part.x + part.width, part.y + part.height),
        )
        return _profiled(stretched, profile)
    made_box, made_size = box_of(grown), (grown.width, grown.height)
    if prepared is not None:
        reach_round = MARGIN + 8 if made.fixing is not None else 8  # the fixes' margin, resizing's
        pixels, profile = _laid_round(pixels, prepared, made_box, reach_round, editor)
    source_pixels, source_part = pixels, made_box
    if made.fixing is not None:  # fixed round the part, as the whole picture measures
        measured = (
            _measure(picture, version_, made.editing, sight, editor, decoded, restoring)
            if made.fixing.dark is not None
            else None
        )
        newer = _NEWEST.started(picture.path)
        source_pixels, source_part = _fixed_round(
            pixels, made_box, made, measured, ai, offset, stop=newer
        )
    if source_pixels.shape[2] == 4:  # see-through parts (a cut-out's) apart, as Save makes them
        colours, clear, here = _round(source_pixels, source_part, made_size)
        made_part = Image.fromarray(_made_part(colours, here, made_size, made, ai))
        made_part.putalpha(Image.fromarray(resize_alpha(clear, here, made_size)))
    else:
        made_part = Image.fromarray(_made_part(source_pixels, source_part, made_size, made, ai))
    made_part = _profiled(made_part, profile)
    if made.depthing is not None:  # worked out on the whole picture made, as Save does
        fit = _fit_for(target)
        whole_made = sight.fitted(
            (
                str(picture.path).casefold(),
                source.version,
                made.frame,
                fit,
                made.editing,
                made.restoring,
                made.fixing,
                made.fix_quality,
            ),
            lambda: _fitted(picture, source, seen, made, fit, sight, ai, copies, editor),
        )
        worked = _worked(picture, source, seen, made, whole_made, decoded, depths, editor, ai)
        # The part as made: with a classic painting's margin round it, cut back after.
        made_part = joined_on(
            made_part,
            (grown.x, grown.y, target[0], target[1]),
            worked,
            mask=_subject_on(
                decoded,
                made,
                target,
                (grown.x, grown.y, grown.width, grown.height),
                key,
                editor,
                ai,
            ),
            stop=_NEWEST.started(picture.path),
        )
    if painting is not None:
        if painting.style.kind == "classic":
            drawn = paint(made_part, painting, ai.painter, reach=reach)
            inside = (region.x - grown.x, region.y - grown.y)
            painted = drawn.crop((*inside, inside[0] + size[0], inside[1] + size[1]))
            made_part = made_part.crop((*inside, inside[0] + size[0], inside[1] + size[1]))
            painted = _profiled(painted, profile)
        else:
            working = _working(
                painting.style, picture, source, seen, made, sight, ai, copies, editor
            )
            assert working is not None  # noqa: S101 - a network's style has one
            wx, wy = working.width / target[0], working.height / target[1]
            cut = working.resize(
                size,
                Image.Resampling.LANCZOS,
                box=(
                    region.x * wx,
                    region.y * wy,
                    (region.x + region.width) * wx,
                    (region.y + region.height) * wy,
                ),
            )
            painted = paint(made_part, painting, ai.painter, working=cut)
        if painting.parts:
            here = _part_mask(
                editor, decoded, key, edits, painting.parts, pixels, offset, part, size
            )
            painted = only_on(painted, made_part, here)
        made_part = painted
    if looked is None:
        return made_part
    at = Placement(target[0], target[1], left=region.x, top=region.y)
    shown = styled(made_part, looked, seed=seed, placement=at)
    if parts:
        here = _part_mask(editor, decoded, key, edits, parts, pixels, offset, part, size)
        shown = only_on(shown, made_part, here)
    return shown


_CLASSIC_REACHES = 4.0  # how many hundredths of the short side a classic means sees round a part


def _part_mask(
    editor: Editor,
    decoded: Image.Image,
    key: str,
    edits: tuple[Edit, ...],
    parts: tuple[Part, ...],
    pixels: Pixels,
    offset: tuple[int, int],
    part: Box,
    size: tuple[int, int],
) -> Image.Image:
    """Where a painting or a look goes on a part of the picture made at full detail: the parts'
    mask at the picture's size, spread over an extended canvas as its edges carry on, cut to the
    part."""
    mask = editor.look_mask(decoded, key, edits, parts)
    height, width = mask.shape
    canvas_height, canvas_width = pixels.shape[:2]
    left, top = offset
    spread = np.pad(
        mask,
        ((top, canvas_height - top - height), (left, canvas_width - left - width)),
        mode="edge",
    )
    return Image.fromarray(spread, "L").resize(
        size,
        Image.Resampling.BILINEAR,
        box=(part.x, part.y, part.x + part.width, part.y + part.height),
    )


def _working(
    style: Style,
    picture: Picture,
    source: Source,
    seen: Seen,
    made: Plan,
    sight: Sight,
    ai: Models,
    copies: Previews,
    editor: Editor,
) -> Image.Image | None:
    """A network's painting of the picture made, at its working size, kept for the previews that
    follow (another strength, the colours choice, a look, a part zoomed into); None for a classic
    means, drawn on each preview itself."""
    if style.kind == "classic":
        return None
    size = working_size(made.width, made.height)

    def painted() -> Image.Image:
        shaped = _fitted(picture, source, seen, made, size, sight, ai, copies, editor)
        colours, _alpha = split_alpha(shaped)
        return ai.painter.paint(Image.fromarray(colours, "RGB"), style)

    asked = (
        str(picture.path).casefold(),
        source.version,
        made.frame,
        made.editing,
        made.restoring,
        made.fixing,
        made.fix_quality,
        style.id,
        style.code.tobytes() if style.code is not None else b"",
    )
    return ai.painter.kept(asked, painted)


class Newest:
    """Which preview of each picture's part with its fixes is the newest: an older one still
    being made stops at its next tile, as the window has let it go for the newer (a slider
    moved, the part dragged), so the card and processor aren't kept on what no one will see."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, int] = {}

    def started(self, path: Path) -> Callable[[], bool]:
        """A preview of the picture at `path` starts: whether a newer one has started since."""
        name = str(path).casefold()
        with self._lock:
            mine = self._latest.get(name, 0) + 1
            self._latest[name] = mine

        def newer() -> bool:
            with self._lock:
                return self._latest.get(name) != mine

        return newer


_NEWEST = Newest()


def _planned(
    recipe: Recipe,
    picture: Picture,
    source: Source,
    seen: Seen,
    sight: Sight,
    ai: Models,
    editor: Editor,
) -> Plan:
    """The plan for a recipe, with how dark the picture measures as its edits and restoring
    leave it, once the dark photo fix asks (worked out once, as the previews' own)."""
    stops = None
    if recipe.fixing is not None and recipe.fixing.dark is not None:
        editing = recipe.editing if recipe.editing and recipe.editing.edits else None
        restoring = planned(recipe, seen, ai.starts_on(), ai.fix_starts_on()).restoring
        try:
            stops = _measure(
                picture, source.version, editing, sight, editor, restoring=restoring
            ).stops
        except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
            raise _refused(error) from None
        except (EditingError, RestoringError) as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
        except ModelError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    return planned(recipe, seen, ai.starts_on(), ai.fix_starts_on(), stops)


_DEPTH_MODELS = {"depth-anything-v2-small", BIREFNET}


def _fit_for(target: tuple[int, int]) -> tuple[int, int]:
    """The size the whole picture made is worked out from for its depth tools: as a preview of
    all of it fits the copy they're worked out on."""
    scale = min(1600 / target[0], 1600 / target[1], 1.0)
    return max(1, round(target[0] * scale)), max(1, round(target[1] * scale))


def _worked(
    picture: Picture,
    source: Source,
    seen: Seen,
    made: Plan,
    whole_made: Image.Image,
    whole: Image.Image,
    depths: Depths,
    editor: Editor,
    ai: Models,
) -> Worked:
    """The depth tools worked out on the whole picture made (`whole_made`, a preview of all of
    it), from the depth of the picture (`whole`, decoded) as its edits leave it."""
    assert made.depthing is not None  # noqa: S101 - asked for with depth tools
    key = picture_key(picture.path, source.version)
    edits = made.editing.edits if made.editing else ()
    depthing = made.depthing
    if depthing.portrait is not None or depthing.fog is not None:
        near = depths.read(whole, key, edits).near
    else:
        near = np.zeros((2, 2), np.float32)
    mask = _subject_on(whole, made, whole_made.size, None, key, editor, ai)
    return work_out(
        whole_made,
        depthing,
        near,
        canvas_of(made),
        whole.size,  # edits keep the picture's size
        mask=mask,
        found_focus=seen.focus,
    )


def _subject_on(
    whole: Image.Image,
    made: Plan,
    size: tuple[int, int],
    region: tuple[int, int, int, int] | None,
    key: str,
    editor: Editor,
    ai: Models,
) -> npt.NDArray[np.uint8] | None:
    """The subject portrait blur keeps sharp, on the picture made `size` big (`region`, a part of
    it: left, top, width, height in its pixels), or None without portrait blur or a subject."""
    depthing = made.depthing
    if depthing is None or depthing.portrait is None:
        return None
    edits = made.editing.edits if made.editing else ()
    quality = depthing.portrait.quality or cut_quality(ai)
    found, _where = editor.subject(whole, key, edits, quality)
    if not found.any():
        return None
    if region is None:
        return np.asarray(placed(found, made, size))
    full = np.asarray(placed(found, made, size))
    left, top, width, height = region
    return np.ascontiguousarray(full[top : top + height, left : left + width])


def _nothing(recipe: Recipe) -> str:
    """What a Save with nothing to make says: why its fixes change nothing in the picture, or
    to pick a size or a look."""
    if (
        recipe.fixing is not None
        and recipe.sizing is None
        and recipe.styling is None
        and recipe.painting is None
        and recipe.restoring is None
    ):
        return unchanged(recipe.fixing)
    return _NOTHING


def _measure(
    picture: Picture,
    version_: str,
    editing: Editing | None,
    sight: Sight,
    editor: Editor,
    decoded: Image.Image | None = None,
    restoring: Restoring | None = None,
) -> Measure:
    """What the dark photo fix takes from the whole picture, as its edits and restoring leave
    it, worked out once."""
    edits = editing.edits if editing else ()

    def image() -> Image.Image:
        whole = decoded if decoded is not None else sight.picture(picture, version_)
        if not edits and restoring is None:
            return whole
        key = picture_key(picture.path, version_)
        return editor.state(whole, key, edits, restoring=restoring)

    return sight.measured((str(picture.path).casefold(), version_, editing, restoring), image)


def _fixed_round(
    pixels: Pixels,
    part: Box,
    made: Plan,
    measured: Measure | None,
    ai: Models,
    offset: tuple[int, int],
    *,
    stop: Callable[[], bool] = lambda: False,
) -> tuple[Pixels, Box]:
    """The picture round a part, with a margin so the fixes' edges see what's beside them, its
    fixes made (see-through parts kept as they are); and where the part is on it. `offset` is
    where the picture itself is on `pixels` (its extended canvas); `stop` stops it at its next
    tile (StoppedError)."""
    assert made.fixing is not None  # noqa: S101 - asked for with fixes
    height, width = pixels.shape[:2]
    left, top = max(int(part.x) - MARGIN, 0), max(int(part.y) - MARGIN, 0)
    right = min(ceil(part.x + part.width) + MARGIN, width)
    bottom = min(ceil(part.y + part.height) + MARGIN, height)
    around = np.ascontiguousarray(pixels[top:bottom, left:right])
    colours = around[..., :3]
    if around.shape[2] == 4:
        colours = bled(np.ascontiguousarray(colours), np.ascontiguousarray(around[..., 3]))
    done = fixed(
        np.ascontiguousarray(colours),
        made.fixing,
        measured,
        made.fix_quality,
        ai,
        at=(left - offset[0], top - offset[1]),
        stop=stop,
    )
    if around.shape[2] == 4:
        done = np.dstack([done, around[..., 3]])
    return done, Box(part.x - left, part.y - top, part.width, part.height)


def _round(
    pixels: Pixels, part: Box, size: tuple[int, int]
) -> tuple[Pixels, npt.NDArray[np.uint8], Box]:
    """The picture round a part (see-through as a fourth channel), with room for the model's
    margin and the resize's reach: its colours, what its see-through parts hide carried in from
    what shows (so making it bigger brings in no dark fringe), its see-through parts, and where
    the part is in it. Only round the part: over all of a big picture it takes seconds."""
    height, width = pixels.shape[:2]
    reach = _MARGIN + ceil(3 * max(part.width / size[0], part.height / size[1], 1.0)) + 2
    left, top = max(int(part.x) - reach, 0), max(int(part.y) - reach, 0)
    right = min(ceil(part.x + part.width) + reach, width)
    bottom = min(ceil(part.y + part.height) + reach, height)
    around = pixels[top:bottom, left:right]
    clear = np.ascontiguousarray(around[..., 3])
    colours = bled(np.ascontiguousarray(around[..., :3]), clear)
    return colours, clear, Box(part.x - left, part.y - top, part.width, part.height)


def _profiled(image: Image.Image, profile: object) -> Image.Image:
    """The picture with the colour profile it was made from, so its colours show as they are."""
    if isinstance(profile, bytes):
        image.info["icc_profile"] = profile
    return image


def _fitted(
    picture: Picture,
    source: Source,
    seen: Seen,
    made: Plan,
    size: tuple[int, int],
    sight: Sight,
    ai: Models,
    copies: Previews,
    editor: Editor,
) -> Image.Image:
    """The picture made, `size` big, as `_cut` cuts it, a dark photo brightened (and given its
    local contrast) on that copy as the whole picture measures. Noise, blur and blocks show only
    on a part at full detail: on a copy this size they're too small to judge, and their models
    would take seconds to minutes over all of it."""
    image = _cut(picture, source, seen, made, size, sight, ai, copies, editor)
    if made.fixing is None or made.fixing.dark is None:
        return image
    measured = _measure(
        picture, _version_of(picture), made.editing, sight, editor, restoring=made.restoring
    )
    extending = made.frame.shape == "extend" and made.frame.sides != "none"
    shown = made.frame.canvas if extending else made.frame.kept
    profile = image.info.get("icc_profile")
    grey = image.mode in GREY_MODES
    colours, alpha = split_alpha(image)
    done = fixed(
        colours,
        made.fixing,
        measured,
        made.fix_quality,
        ai,
        at=(shown.x, shown.y),
        step=shown.width / size[0],
        light_only=True,
    )
    result = Image.fromarray(done)
    if alpha is not None:
        result.putalpha(Image.fromarray(alpha))
    elif grey:
        result = result.convert("L")
    return _profiled(result, profile)


def _cut(
    picture: Picture,
    source: Source,
    seen: Seen,
    made: Plan,
    size: tuple[int, int],
    sight: Sight,
    ai: Models,
    copies: Previews,
    editor: Editor,
) -> Image.Image:
    """The picture made, `size` big, before its fixes: from its view the size of a screen, cut
    as its plan says (or from the picture itself, when the view has fewer pixels than that, or
    as its edits left it, restored: its scratches filled at full size, its colour laid on the
    copy); or, with its edges extended, from the canvas LaMa drew."""
    edits = made.editing.edits if made.editing else ()
    restoring = made.restoring
    key = picture_key(picture.path, source.version)
    if made.frame.shape == "extend" and made.frame.sides != "none":
        version_ = _version_of(picture)
        whole = sight.picture(picture, version_)
        changed = bool(edits) or restoring is not None
        state = editor.state(whole, key, edits, restoring=restoring) if changed else None
        canvas, kept, _at = sight.extended(
            picture,
            version_,
            made.frame.canvas,
            ai.filler,
            image=state,
            also=(made.editing, restoring),
        )
        profile = (state or whole).info.get("icc_profile")
        return _profiled(Image.fromarray(smaller(canvas, kept, size)), profile)
    kept = made.frame.kept
    box = (kept.x, kept.y, kept.x + kept.width, kept.y + kept.height)
    if restoring is not None:
        prepared = editor.prepared(sight.picture(picture, source.version), key, edits, restoring)
        base = prepared.picture
        small = _profiled(
            base.resize(size, Image.Resampling.LANCZOS, box=box), base.info.get("icc_profile")
        )
        return editor.restorer.shown(prepared, small, box)
    if edits:
        state = editor.state(sight.picture(picture, source.version), key, edits)
        return _profiled(
            state.resize(size, Image.Resampling.LANCZOS, box=box), state.info.get("icc_profile")
        )
    with Image.open(copies.view(source)) as view:
        view.load()
        k = view.width / seen.width
        if kept.width * k >= size[0] or k >= 1:
            box = (kept.x * k, kept.y * k, (kept.x + kept.width) * k, (kept.y + kept.height) * k)
            return _profiled(
                view.resize(size, Image.Resampling.LANCZOS, box=box), view.info.get("icc_profile")
            )
    # A big picture on a big, sharp screen: the view would only be stretched.
    whole = sight.picture(picture, _version_of(picture))
    box = (kept.x, kept.y, kept.x + kept.width, kept.y + kept.height)
    return _profiled(
        whole.resize(size, Image.Resampling.LANCZOS, box=box), whole.info.get("icc_profile")
    )


def _made_part(pixels: Pixels, part: Box, size: tuple[int, int], made: Plan, ai: Models) -> Pixels:
    """A part of the picture made, with a margin of the picture around it so its edges see what's
    beside them, then cut back."""
    match made.method:
        case "pixels":
            return by_pixels(pixels, part, size)
        case "smooth":
            return smoothly(pixels, part, size)
        case "shrink" | "keep":
            return smaller(pixels, part, size)
        case "ai":
            pass
    assert made.model is not None  # noqa: S101 - the plan names one for "ai"
    height, width = pixels.shape[:2]
    left = min(_MARGIN, part.x)
    top = min(_MARGIN, part.y)
    right = min(_MARGIN, width - part.x - part.width)
    bottom = min(_MARGIN, height - part.y - part.height)
    k = size[0] / part.width
    wider = Box(part.x - left, part.y - top, part.width + left + right, part.height + top + bottom)
    out = (ceil(wider.width * k - 1e-6), ceil(wider.height * size[1] / part.height - 1e-6))
    whole = through_model(pixels, wider, out, ai.tiling(made.model))
    cut_x, cut_y = round(left * k), round(top * size[1] / part.height)
    return np.ascontiguousarray(whole[cut_y : cut_y + size[1], cut_x : cut_x + size[0]])


def _seen(conn: sqlite3.Connection, sight: Seeing, picture_id: int) -> tuple[Picture, Seen, Source]:
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't in your library any more."
        )
    picture = picture_of(conn, picture_id, Path(row["path"]))
    try:
        seen = sight.of(picture, version(row["modified"], row["size"]))
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    return picture, seen, Source.of(row)


def _glanced(
    conn: sqlite3.Connection, sight: Seeing, copies: Previews, picture_id: int
) -> tuple[Picture, Seen, Source]:
    """As `_seen`, from the picture's thumbnail and its size as the library read it, so nothing
    is decoded whole (`Sight.glance`); a picture not read yet is seen whole."""
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None or not row["width"] or not row["height"]:
        return _seen(conn, sight, picture_id)
    picture = picture_of(conn, picture_id, Path(row["path"]))
    source = Source.of(row)
    size = (int(row["width"]), int(row["height"]))
    try:
        seen = sight.glance(picture, source.version, size, lambda: copies.thumbnail(source))
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise _refused(error) from None
    return picture, seen, source


def _pasted(conn: sqlite3.Connection, picture_id: int) -> bool:
    row = conn.execute("SELECT pasted FROM pictures WHERE id = ?", (picture_id,)).fetchone()
    return bool(row and row["pasted"])


def _may_save(
    conn: sqlite3.Connection, picture_id: int, saving: SavingIn, aside: Quarantine
) -> None:
    """Refuses a Save that would write where it mustn't: over a picture waiting in a quarantine,
    beside or in place of a pasted one, which lives in Mado's data folder, or in place of a
    camera RAW, which Mado can't write."""
    row = conn.execute(
        "SELECT path, folder_id, pasted, raw FROM pictures WHERE id = ? AND gone_at IS NULL",
        (picture_id,),
    ).fetchone()
    if row is None:
        return  # said as gone by what follows
    if row["folder_id"] is None and aside.holds(Path(row["path"])):
        raise HTTPException(status.HTTP_409_CONFLICT, _ASIDE)
    if row["raw"] and saving.how == "replace":
        raise HTTPException(status.HTTP_409_CONFLICT, NO_RAW_REPLACE)
    if row["pasted"] and saving.how == "replace":
        raise HTTPException(status.HTTP_409_CONFLICT, _NO_ORIGINAL)
    if row["pasted"] and not saving.folder:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _NO_FOLDER)


def _version_of(picture: Picture) -> str:
    try:
        stat = picture.path.stat()
    except OSError as error:
        raise _refused(PictureGoneError(picture.path)) from error
    return version(stat.st_mtime_ns, stat.st_size)


def _recipe(body: RecipeIn, conn: sqlite3.Connection, now: str, name: str) -> Recipe:
    """The recipe asked for: its edits (made on the picture as it is `now`; once it's changed,
    they're refused), its size (the owner's screens naming theirs) and its look (one of Mado's or
    the owner's, on the whole picture or parts, those tied to the picture as it is `now` too), any
    of them none."""
    sizing: Sizing | None = None
    if body.size is not None:
        asked = body.size
        try:
            size = resolve(asked.size, screens_kept(conn))
        except SizeError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
        focus = (asked.focus[0], asked.focus[1]) if asked.focus else None
        sizing = Sizing(size, asked.shape, focus, asked.kind, asked.quality, asked.clean)
    styling: Styling | None = None
    painting: Painting | None = None
    try:
        if body.paint is not None:
            asked_paint = body.paint
            style = own_styles.resolve(conn, asked_paint.model_dump(by_alias=True))
            if style is None and asked_paint.style == "picture":
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, UNREAD_STYLE)
            if style is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "That style isn't in your styles any more."
                )
            painting = Painting(
                style,
                asked_paint.strength,
                asked_paint.colours,
                asked_paint.setting,
                picked(asked_paint.parts),
            )
        if body.look is not None:
            look = own_looks.resolve(conn, body.look.look)
            if look is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "That look isn't in your looks any more."
                )
            styling = Styling(
                look, body.look.strength, body.look.touches.touches(), picked(body.look.parts)
            )
        editing: Editing | None = editing_of(body.edit)
        fixing = fixing_of(body.fix)
        depthing = depthing_of(body.depth)
        restoring = restoring_of(body.restore)
    except (EditError, FixError, DepthError, RestoreError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if editing is not None and editing.version is not None and editing.version != now:
        raise HTTPException(status.HTTP_409_CONFLICT, changed(name, edited=bool(editing.edits)))
    # The scratches' strokes were painted on the picture as it was: once it's changed, they're
    # refused as edits are. A picture's own page always ties them to its version.
    restoring = tied(restoring, now, name)
    picked_parts = (styling is not None and styling.parts) or (
        painting is not None and painting.parts
    )
    if picked_parts and (editing is None or editing.version is None):
        # Parts picked for a look or a painting are tied to the picture as it is, as edits are:
        # a Save that finds it changed saves nothing.
        editing = Editing(editing.edits if editing else (), now)
    return Recipe(
        sizing,
        styling,
        editing,
        fixing,
        depthing=depthing,
        painting=painting,
        restoring=restoring,
    )


def _refused(error: Exception) -> HTTPException:
    if isinstance(error, PictureGoneError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, NeedsFfmpegError | NeedsReaderError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


def _size(size: Size) -> SizeOut:
    return SizeOut(
        id=size.id,
        name=size.name,
        width=size.width,
        height=size.height,
        group=size.group,
        purpose=size.purpose,
        label=size.label,
    )


def _fraction(box: Box, seen: Seen) -> Fraction:
    return Fraction(
        x=box.x / seen.width,
        y=box.y / seen.height,
        width=box.width / seen.width,
        height=box.height / seen.height,
    )


def _taken_in(folder: Path) -> Callable[[str], bool]:
    return lambda name: (folder / name).exists()


def _made_at(path: Path) -> str | None:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(stamp).astimezone().isoformat(timespec="seconds")
