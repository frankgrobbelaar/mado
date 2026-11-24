"""Painting styles, as the Looks tab asks for them: Mado's painters and classic means and the
owner's own styles, a small copy of a picture in each, a picture's own style read (from the
library, a picture's page, or one dropped or pasted, which open as a picture of their own first),
and the owner's styles kept, renamed and deleted."""

import io
import sqlite3
from datetime import datetime
from typing import Annotated, Literal, cast

import numpy as np
from fastapi import APIRouter, HTTPException, Response, status
from PIL import Image
from pydantic import Field

from mado import own_styles, recipes
from mado.api.common import ApiModel, Copies, Database, Editors, Models, Seeing
from mado.api.editing import opened_picture
from mado.api.edits import EditStepIn, PartIn, edits_of
from mado.api.looks import SMALL
from mado.api.restore import RestoreStepIn, restoring_of, tied
from mado.batches import order_of
from mado.core.edits import EditError
from mado.core.painting import (
    CLASSICS,
    PAINTERS,
    SMALLEST,
    Style,
    classic,
    code_of,
    code_text,
    named_after,
    picture_style,
    unsuited,
)
from mado.core.restore import RestoreError
from mado.directml import ModelError
from mado.editing import EditingError, picture_key
from mado.making import split_alpha
from mado.own_styles import Kept, StyleNameError
from mado.painting import MICROAST
from mado.pictures import NeedsFfmpegError, NeedsReaderError, PictureGoneError, UnreadableError
from mado.previews import Source
from mado.restoring import RestoringError

router = APIRouter()

_KEEP = {"Cache-Control": "private, max-age=31536000, immutable"}  # its address names its version
_WEBP: dict[int | str, dict[str, object]] = {200: {"content": {"image/webp": {}}}}
_GONE = "That style isn't in your styles any more."
UNREAD_STYLE = "Mado couldn't read that picture's style. Pick the picture again for its style."
_THUMBNAIL = 160  # a kept style's small copy of its picture, on its longer side
_SMALL_STYLE = (
    "{name} is too small to take a style from: pick a picture at least {least} pixels across."
)
_PLAIN_STYLE = (
    "{name} is nearly one colour, so there's little style in it to take. Pick a picture with "
    "more colour and texture."
)


class PaintIn(ApiModel):
    """The painting step: a style at a strength, in the picture's own colours or the style's, a
    classic one at its setting. A picture's own style comes whole: its 512 numbers and what the
    picture is called."""

    style: str  # "van-gogh", "pencil", one of the owner's ("yours-3"), or "picture"
    strength: float = Field(default=1.0, ge=0, le=1)
    colours: bool = False  # the picture's own colours, the painting's lightness
    setting: int | None = Field(default=None, ge=0, le=100)  # a classic one's; None: as it starts
    code: str | None = Field(default=None, max_length=4096)  # a picture's: its numbers, base64
    named: str | None = Field(default=None, max_length=200)  # a picture's: what it's called


class PaintHereIn(PaintIn):
    """The painting step on a picture's page: on the whole picture, or only on parts picked as
    Select picks them, as a look's."""

    parts: Annotated[list[PartIn], Field(default_factory=list[PartIn], max_length=32)]


class StyleOut(ApiModel):
    id: str  # "van-gogh", "oil"
    name: str  # "After Van Gogh"
    kind: Literal["painter", "classic"]
    painting: str | None  # a painter's: the public-domain painting it learned from
    download: str | None  # a painter's network, as /tools lists it
    setting: str | None  # a classic one's one setting: "Darkness"
    first: int  # where that setting starts


class YourStyle(ApiModel):
    id: str  # "yours-3"
    name: str
    source: str  # the picture it came from, by name
    added_at: str


class Styles(ApiModel):
    painters: list[StyleOut]  # Mado's, after public-domain painters
    classics: list[StyleOut]  # drawn by code
    yours: list[YourStyle]  # the owner's, oldest first
    reader: str  # the download that reads a picture's style and paints with it


class SmallStyleAsk(ApiModel):
    edit: EditStepIn | None = None  # the picture as its edits leave it, at their version
    restore: RestoreStepIn | None = None  # and as restoring leaves it
    code: str | None = Field(default=None, max_length=4096)  # a picture's own style
    named: str | None = Field(default=None, max_length=200)


class ReadOut(ApiModel):
    code: str  # the picture's style: 512 numbers, base64, as a recipe carries it
    named: str  # what the picture is called: "Night market"
    version: str  # the picture's version, which its small copy's address carries


class KeepIn(ApiModel):
    name: str = Field(max_length=200)
    code: str = Field(max_length=4096)
    picture: int  # the picture it came from: a small copy of it is kept to know it by


class RenameIn(ApiModel):
    name: str = Field(max_length=200)


@router.get("/styles")
def styles(conn: Database) -> Styles:
    """Mado's painting styles and the owner's own."""
    return Styles(
        painters=[_style(each) for each in PAINTERS],
        classics=[_style(each) for each in CLASSICS],
        yours=[_yours(each) for each in own_styles.listed(conn)],
        reader=MICROAST,
    )


@router.get("/styles/{style_id}/thumbnail", response_class=Response, responses=_WEBP)
def thumbnail(style_id: str, conn: Database) -> Response:
    """The small copy of the picture one of the owner's styles came from."""
    found = own_styles.thumbnail(conn, style_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    return Response(found, media_type="image/webp", headers=_KEEP)


@router.get("/pictures/{picture_id}/styles/{style_id}", response_class=Response, responses=_WEBP)
def small_copy(
    picture_id: int, style_id: str, conn: Database, copies: Copies, ai: Models
) -> Response:
    """A small copy of the picture in a painting style, at its full strength (a classic one at
    its first setting), from its thumbnail (a camera RAW's from its view, as looks' are): WebP,
    kept by the window, as its address carries the picture's version."""
    style = own_styles.resolve(conn, {"style": style_id})
    if style is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't in your library any more."
        )
    try:
        source = Source.of(row)
        path = copies.view(source) if row["raw"] else copies.thumbnail(source)
        with Image.open(path) as found:
            found.load()
            small = found.copy()
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except OSError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Mado couldn't keep a copy of it to show in its data folder: "
            f"{error.strerror or error}. Your picture is as it was.",
        ) from None
    return _webp(_painted_small(small, style, ai), keep=True)


@router.post("/pictures/{picture_id}/styles/{style_id}", response_class=Response, responses=_WEBP)
def small_asked(
    picture_id: int,
    style_id: str,
    body: SmallStyleAsk,
    conn: Database,
    sight: Seeing,
    editor: Editors,
    ai: Models,
) -> Response:
    """A small copy of the picture in a style it can't ask for by GET: as its edits leave it, or
    in a picture's own style (`style_id` "picture", its numbers in the body)."""
    style = own_styles.resolve(
        conn, {"style": style_id, "code": body.code, "named": body.named or "A picture"}
    )
    if style is None and style_id == "picture":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, UNREAD_STYLE)
    if style is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    asked = body.edit.version if body.edit is not None else None
    picture, now = opened_picture(conn, picture_id, asked)
    try:
        image = sight.picture(picture, now)
        restoring = tied(restoring_of(body.restore), now, picture.path.name)
        if (body.edit is not None and body.edit.edits) or restoring is not None:
            edits = edits_of(body.edit.edits, body.edit.version).edits if body.edit else ()
            key = picture_key(picture.path, now)
            small = editor.small(image, key, edits, SMALL, restoring)
        else:
            small = image.copy()
            small.thumbnail((SMALL * 2, SMALL * 2), Image.Resampling.LANCZOS)
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except (UnreadableError, EditError, EditingError, RestoreError, RestoringError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except ModelError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _webp(_painted_small(small, style, ai), keep=False)


@router.post("/pictures/{picture_id}/style")
def read_style(picture_id: int, conn: Database, sight: Seeing, ai: Models) -> ReadOut:
    """A picture's style, read by MicroAST from its colours and textures (never what it shows):
    512 numbers a recipe carries. A picture too small, or so plain there's no style in it, says
    so; MicroAST is downloaded the first time it's asked for (409 till then)."""
    picture, now = opened_picture(conn, picture_id, None, edited=False)
    named = named_after(picture.path.stem)
    try:
        image = sight.picture(picture, now)
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    # What it shows, not what its see-through parts hide.
    colours, _clear = split_alpha(image)
    shown = Image.fromarray(colours, "RGB")
    why = unsuited(np.asarray(_judged(shown))) if min(shown.size) >= SMALLEST else "small"
    if why == "small":
        said = _SMALL_STYLE.format(name=picture.path.name, least=SMALLEST)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, said)
    if why == "plain":
        said = _PLAIN_STYLE.format(name=picture.path.name)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, said)
    try:
        code = ai.painter.read(shown)
    except ModelError as error:
        raise _refused(error) from None
    return ReadOut(code=code_text(code), named=named, version=now)


def _judged(image: Image.Image) -> Image.Image:
    """A copy of a style picture to judge it by: 1024 pixels on its long side at most, but its
    short side no smaller than `SMALLEST`, so a long panorama isn't taken for a small picture."""
    k = min(1.0, max(1024 / max(image.size), SMALLEST / min(image.size)))
    if k >= 1.0:
        return image
    size = (max(1, round(image.width * k)), max(1, round(image.height * k)))
    return image.resize(size, Image.Resampling.BOX)


@router.post("/styles", status_code=status.HTTP_201_CREATED)
def keep(body: KeepIn, conn: Database, sight: Seeing) -> YourStyle:
    """Keeps a picture's style as one of the owner's: its numbers and a small copy of the picture
    to know it by (160 pixels at most), never the picture itself."""
    try:
        code = code_of(body.code)
        picture_style(body.name, code)  # its numbers are a style's
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    picture, now = opened_picture(conn, body.picture, None, edited=False)
    try:
        image = sight.picture(picture, now)
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    colours, clear = split_alpha(image)
    small = Image.fromarray(colours, "RGB")
    if clear is not None:  # its see-through parts stay so in the small copy it's known by
        small.putalpha(Image.fromarray(clear, "L"))
    small.thumbnail((_THUMBNAIL, _THUMBNAIL), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    small.save(out, format="WEBP", quality=80, method=4)
    try:
        kept = own_styles.kept(conn, body.name, code, out.getvalue(), picture.path.name, _now())
    except StyleNameError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return _yours(kept)


@router.put("/styles/{style_id}")
def rename(style_id: str, body: RenameIn, conn: Database) -> YourStyle:
    """Gives one of the owner's styles a new name."""
    try:
        kept = own_styles.renamed(conn, style_id, body.name)
    except StyleNameError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    return _yours(kept)


@router.delete("/styles/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(style_id: str, conn: Database) -> None:
    """Deletes one of the owner's styles. Pictures painted with it stay as they are. Not while a
    recipe uses it, or pictures waiting in the queue are painted with it."""
    needed = _needed_by(conn, style_id)
    if needed is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, needed)
    if not own_styles.deleted(conn, style_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)


def _needed_by(conn: sqlite3.Connection, style_id: str) -> str | None:
    """What still needs a style, in a sentence: a recipe that paints with it (a watch folder may
    run it), or pictures waiting in the queue painted with it."""
    for kept in recipes.listed(conn):
        if any(
            step.get("step") == "paint" and step.get("style") == style_id for step in kept.steps
        ):
            return (
                f"Your recipe {kept.name} paints with it. Change that recipe first, or delete it, "
                "then this style."
            )
    for row in conn.execute("SELECT recipe FROM jobs WHERE state IN ('queued', 'running')"):
        made = order_of(row["recipe"]).get("recipe")
        paint = cast("dict[str, object]", made).get("paint") if isinstance(made, dict) else None
        if isinstance(paint, dict) and cast("dict[str, object]", paint).get("style") == style_id:
            return (
                "Pictures waiting in the queue are painted with it. Delete it once they're made, "
                "or take them out of the queue first."
            )
    return None


def _painted_small(image: Image.Image, style: Style, ai: Models) -> Image.Image:
    """A small copy in a style at its full strength, `SMALL` pixels on its longer side, its
    see-through parts kept: a network's painted on the processor at the small canvas, which
    never takes the graphics card for a style no one has chosen yet."""
    colours, clear = split_alpha(image)
    shown = Image.fromarray(colours, "RGB")
    if style.kind == "classic":
        small = shown.copy()
        small.thumbnail((SMALL, SMALL), Image.Resampling.LANCZOS)
        made = classic(small, style, style.first, reach=min(small.size) / 100)
    else:
        try:
            made = ai.painter.paint(shown, style, small=True)
        except ModelError as error:
            raise _refused(error) from None
        made.thumbnail((SMALL, SMALL), Image.Resampling.LANCZOS)
    if clear is not None:
        made.putalpha(Image.fromarray(clear, "L").resize(made.size, Image.Resampling.LANCZOS))
    profile = image.info.get("icc_profile")
    if isinstance(profile, bytes):
        made.info["icc_profile"] = profile
    return made


def _webp(image: Image.Image, *, keep: bool) -> Response:
    out = io.BytesIO()
    profile = image.info.get("icc_profile")  # Pillow writes it only when it's given
    kept = {"icc_profile": profile} if isinstance(profile, bytes) else {}
    image.save(out, format="WEBP", quality=80, method=2, **kept)
    return Response(out.getvalue(), media_type="image/webp", headers=_KEEP if keep else None)


def _refused(error: ModelError) -> HTTPException:
    """A network that isn't downloaded yet (409: the window offers it), or that can't run."""
    said = str(error)
    if "isn't downloaded yet" in said:
        return HTTPException(status.HTTP_409_CONFLICT, f"{said} Download it first.")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, said)


def _style(style: Style) -> StyleOut:
    return StyleOut(
        id=style.id,
        name=style.name,
        kind="painter" if style.kind == "painter" else "classic",
        painting=style.painting,
        download=style.download,
        setting=style.setting,
        first=style.first,
    )


def _yours(kept: Kept) -> YourStyle:
    return YourStyle(id=kept.id, name=kept.name, source=kept.source, added_at=kept.added_at)


def _now() -> datetime:
    return datetime.now().astimezone()
