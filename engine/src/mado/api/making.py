"""Making a picture to a recipe, as the Size and Looks tabs ask: the sizes there are, the owner's
screens, the plan for a recipe (its shape, model, look, time and quality), a preview (all of it
fitted, or a part at full detail), the name it would be saved as, and making it, as a job
(mado/api/jobs.py). A recipe is a size step, a look step, or both, made by one Save."""

import io
import json
import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from PIL import Image
from pydantic import Field

from mado import own_looks
from mado.ai import LAMA
from mado.api.common import ApiModel, Copies, Database, Models, Seeing, Toolbox, Working
from mado.api.jobs import Job, job_of
from mado.api.looks import LookIn
from mado.core.estimate import key
from mado.core.framing import Box, Shape
from mado.core.kind import Kind
from mado.core.models import Quality
from mado.core.naming import EXTENSIONS, aside_name, new_name, replacement_name
from mado.core.quality import Format, about_bytes, colour_words, suited
from mado.core.recipe import Plan, Recipe, Sizing, Styling
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
from mado.directml import ModelError
from mado.looks import Placement, seed_of, styled
from mado.making import (
    Picture,
    Seen,
    Sight,
    estimated,
    picture_of,
    planned,
    screens_kept,
    waiting_for,
)
from mado.pictures import NeedsFfmpegError, PictureGoneError, UnreadableError
from mado.previews import Previews, Source, version
from mado.upscale import Pixels, StoppedError, by_pixels, smaller, smoothly, through_model

router = APIRouter()
log = logging.getLogger(__name__)

_MOST_PREVIEW = 4_000_000  # pixels a preview of a part may have
_MARGIN = 16  # pixels of the picture around a part previewed, so its edges see what's beside
_NOTHING = "Pick a size or a look first: as it is, there's nothing to make."


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


class RecipeIn(ApiModel):
    """A recipe: the size step, then the look step; either can be left out."""

    size: SizeIn | None = None
    look: LookIn | None = None


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
    look: str | None  # the look, as Save says it after "with": "Warm film at 60%"
    seconds: float  # about how long it takes here
    place: Literal["card", "processor"]
    measured: bool  # the time is this PC's own, not a guess
    format: Format  # what suits it
    format_quality: int | None
    fits: str  # "What every TV shows."
    colour: str  # "sRGB", "Display P3"
    bytes: int  # about how big it comes out
    see_through: bool  # it has see-through parts, which JPEG makes white
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
    picture_id: int, body: RecipeIn, conn: Database, sight: Seeing, ai: Models, toolbox: Toolbox
) -> PlanOut:
    """How a picture would be made to a recipe: its shape, the model, its look, about how long it
    takes here and how it would be saved."""
    picture, seen, _source = _seen(conn, sight, picture_id)
    recipe = _recipe(body, conn)
    here = ai.where()
    made = planned(recipe, seen, ai.starts_on(here))
    purpose = recipe.sizing.size.purpose if recipe.sizing else "screen"
    suits = suited(purpose, made.kind, picture.format, alpha=seen.alpha)
    frame = made.frame
    names = {item.id: item for item, _ in toolbox.status()}
    measured = made.model is not None and key(made.model.id, here.place) in here.speeds
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
        clean_matters=made.method == "ai" and made.quality == "fast",
        look=made.look,
        seconds=estimated(made, here),
        place=here.place,
        measured=measured,
        format=suits.format,
        format_quality=suits.quality,
        fits=suits.fits,
        colour=colour_words(seen.profile, keep=True),
        bytes=about_bytes(suits.format, suits.quality, made.kind, made.width * made.height),
        see_through=seen.alpha,
        needs=[
            Need(id=each, name=names[each].name, size=names[each].size or 0)
            for each in waiting_for(made, ai)
            if each in names
        ],
    )


_PREVIEWS: dict[int | str, dict[str, object]] = {
    200: {"content": {"image/jpeg": {}, "image/webp": {}}}
}


@router.post("/pictures/{picture_id}/preview", response_class=Response, responses=_PREVIEWS)
def preview(
    picture_id: int, body: PreviewIn, conn: Database, sight: Seeing, ai: Models, copies: Copies
) -> Response:
    """A preview of the picture made: all of it no bigger than `fit` (from its view the size of a
    screen), or a part of it at full detail (`region`); before (the picture only stretched) or
    after (made, as Save would, with its look and touches). All of it comes as JPEG, quick to
    make as looks are gone through (WebP when it has see-through parts); a part as WebP."""
    picture, seen, source = _seen(conn, sight, picture_id)
    recipe = _recipe(body.recipe, conn)
    made = planned(recipe, seen, ai.starts_on())
    missing = waiting_for(made, ai)
    # Extending needs LaMa on either side; the upscaler only for a part made at full detail.
    if LAMA in missing or (missing and body.region is not None and body.side == "after"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "It needs a model Mado downloads the first time it's asked for: download it first.",
        )
    began = time.perf_counter()
    try:
        image = _previewed(picture, source, seen, made, body, sight, ai, copies)
    except ModelError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except (UnreadableError, PictureGoneError, NeedsFfmpegError) as error:
        raise _refused(error) from None
    except StoppedError:  # never asked to stop: a preview runs to its end
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The preview stopped.") from None
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


@router.post("/pictures/{picture_id}/saving")
def saving_name(
    picture_id: int, body: SavingAsk, conn: Database, sight: Seeing, ai: Models
) -> SavingName:
    """What a picture made would be saved as, and about how big it would be."""
    picture, seen, _source = _seen(conn, sight, picture_id)
    recipe = _recipe(body.recipe, conn)
    made = planned(recipe, seen, ai.starts_on())
    if made.empty:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _NOTHING)
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
    picture_id: int, body: MakeIn, conn: Database, sight: Seeing, ai: Models, jobs: Working
) -> Job:
    """Makes a picture to its recipe and saves it as the owner chose, as a job: its progress,
    the time left and Cancel come from /jobs."""
    picture, seen, _source = _seen(conn, sight, picture_id)
    recipe = _recipe(body.recipe, conn)
    made = planned(recipe, seen, ai.starts_on())
    if made.empty:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _NOTHING)
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
    if saving.always:
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
    order = {
        "recipe": {
            "size": decided.model_dump(by_alias=True) if decided else None,
            "look": look.model_dump(by_alias=True) if look else None,
        },
        "saving": saving.model_dump(by_alias=True, exclude={"always"}),
        "label": made.made_for,
        "look": made.look,
        "estimate": round(made.scale, 3),
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
) -> Image.Image:
    """The preview as asked for: all of it fitted, or a part at full detail; its look and
    touches where they fall on the picture made, after."""
    looked = made.styling if body.side == "after" else None
    seed = seed_of(picture.path)
    target = (made.width, made.height)
    if body.region is None:
        fit = body.fit or Fit(width=1600, height=1600)
        scale = min(fit.width / target[0], fit.height / target[1], 1.0)
        size = (max(1, round(target[0] * scale)), max(1, round(target[1] * scale)))
        base = sight.fitted(
            (str(picture.path).casefold(), source.version, made.frame, size),
            lambda: _fitted(picture, source, seen, made, size, sight, ai, copies),
        )
        if looked is None:
            return base
        return styled(base, looked, seed=seed, placement=Placement.fitted(base.size, target))
    region = body.region
    if region.width * region.height > _MOST_PREVIEW:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That part is too big to preview at once."
        )
    if region.x + region.width > target[0] or region.y + region.height > target[1]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That part is outside the picture made."
        )
    version_ = _version_of(picture)
    decoded = sight.picture(picture, version_)
    profile = decoded.info.get("icc_profile")
    if made.frame.shape == "extend" and made.frame.sides != "none":
        pixels, kept, _at = sight.extended(picture, version_, made.frame.canvas, ai.filler)
    else:
        pixels = np.asarray(decoded.convert("RGB"))
        kept = made.frame.kept
    kx, ky = kept.width / target[0], kept.height / target[1]  # the picture's pixels a made one
    part = Box(
        kept.x + region.x * kx, kept.y + region.y * ky, region.width * kx, region.height * ky
    )
    if body.side == "before":
        stretched = Image.fromarray(pixels).resize(
            (region.width, region.height),
            Image.Resampling.BICUBIC,
            box=(part.x, part.y, part.x + part.width, part.y + part.height),
        )
        return _profiled(stretched, profile)
    made_part = Image.fromarray(_made_part(pixels, part, (region.width, region.height), made, ai))
    made_part = _profiled(made_part, profile)
    if looked is None:
        return made_part
    at = Placement(target[0], target[1], left=region.x, top=region.y)
    return styled(made_part, looked, seed=seed, placement=at)


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
) -> Image.Image:
    """The picture made, `size` big: from its view the size of a screen, cut as its plan says
    (or from the picture itself, when the view has fewer pixels than that); or, with its edges
    extended, from the canvas LaMa drew."""
    if made.frame.shape == "extend" and made.frame.sides != "none":
        version_ = _version_of(picture)
        canvas, kept, _at = sight.extended(picture, version_, made.frame.canvas, ai.filler)
        profile = sight.picture(picture, version_).info.get("icc_profile")
        return _profiled(Image.fromarray(smaller(canvas, kept, size)), profile)
    kept = made.frame.kept
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
    if row["raw"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Mado can't read camera RAW yet, so it can't make it.",
        )
    picture = picture_of(conn, picture_id, Path(row["path"]))
    try:
        seen = sight.of(picture, version(row["modified"], row["size"]))
    except (UnreadableError, PictureGoneError, NeedsFfmpegError) as error:
        raise _refused(error) from None
    return picture, seen, Source.of(row)


def _version_of(picture: Picture) -> str:
    try:
        stat = picture.path.stat()
    except OSError as error:
        raise _refused(PictureGoneError(picture.path)) from error
    return version(stat.st_mtime_ns, stat.st_size)


def _recipe(body: RecipeIn, conn: sqlite3.Connection) -> Recipe:
    """The recipe asked for: its size (the owner's screens naming theirs) and its look (one of
    Mado's or the owner's), either of them none."""
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
    if body.look is not None:
        look = own_looks.resolve(conn, body.look.look)
        if look is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "That look isn't in your looks any more."
            )
        styling = Styling(look, body.look.strength, body.look.touches.touches())
    return Recipe(sizing, styling)


def _refused(error: Exception) -> HTTPException:
    if isinstance(error, PictureGoneError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, NeedsFfmpegError):
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
