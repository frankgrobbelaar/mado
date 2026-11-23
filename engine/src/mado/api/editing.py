"""Editing by clicking, as the Edit tab asks (mado/editing.py): picking parts with clicks on the
picture as its edits so far left it, and making edits, which the previews and the Looks tab's
small copies then show. Nothing here changes the picture's file: Save makes the edits again at
full size, with the size and the look (mado/api/making.py)."""

import io
import sqlite3
import time
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Response, status
from PIL import Image
from pydantic import Field

from mado import own_looks
from mado.ai import Ai
from mado.api.common import ApiModel, Database, Editors, Models, Seeing
from mado.api.edits import ClickIn, EditIn, EditStepIn, PartIn, edits_of, picked
from mado.api.fixes import FixStepIn, fixing_of
from mado.api.looks import SMALL
from mado.core.edits import Click, EditError, parts_named
from mado.core.fixes import FixError, Fixing
from mado.directml import ModelError
from mado.editing import EditingError, picture_key
from mado.fixing import Measure, fixed
from mado.looks import through
from mado.making import GREY_MODES, Picture, Sight, picture_of, split_alpha
from mado.pictures import NeedsFfmpegError, NeedsReaderError, PictureGoneError, UnreadableError
from mado.previews import version

router = APIRouter()
_WEBP: dict[int | str, dict[str, object]] = {200: {"content": {"image/webp": {}}}}


class SelectIn(ApiModel):
    """The parts picked so far, and a click: one starts a part, an Alt-click (`keep` false) takes
    from the part it's in. `edits` are the edits made so far: the parts are picked on the picture
    as they left it."""

    version: str  # the picture's, as the window has it
    edits: Annotated[list[EditIn], Field(default_factory=list[EditIn], max_length=64)]
    parts: Annotated[list[PartIn], Field(default_factory=list[PartIn], max_length=32)]
    click: ClickIn | None = None


class PartOut(ApiModel):
    name: str  # "Part 1": Mado never guesses what a part is
    clicks: list[ClickIn]
    choice: int  # the answer shown, smallest first
    choices: int  # how many answers there are to step through


class Selection(ApiModel):
    parts: list[PartOut]
    outline: str  # round every part, as an SVG path in a frame 1000 across and 1000 down
    read: float | None  # seconds reading the picture took, when this pick read it
    place: Literal["card", "processor"]  # where it was read
    seconds: float  # all of this pick
    waited: float  # of which waiting for the graphics card, while the queue's picture had it
    missed: bool  # an Alt-click outside every part


class EditAsk(ApiModel):
    version: str
    edits: Annotated[list[EditIn], Field(min_length=1, max_length=64)]


class Edited(ApiModel):
    seconds: float  # what the last edit took
    place: Literal["card", "processor"] | None  # where its model ran
    waited: float  # seconds it waited for the graphics card
    smeared: bool  # an erase that came out much smoother than what's round it: Best may do better


@router.post("/pictures/{picture_id}/select")
def select(
    picture_id: int, body: SelectIn, conn: Database, sight: Seeing, editor: Editors
) -> Selection:
    """Picks parts: the first click reads the picture (about a fifth of a second on the card),
    every click after that is a few hundredths of a second, on the processor."""
    image, key = _opened(conn, sight, picture_id, body.version, edited=bool(body.edits))
    try:
        before = edits_of(body.edits, body.version).edits
        click = Click(body.click.x, body.click.y, body.click.keep) if body.click else None
        began = time.perf_counter()
        found = editor.pick(image, key, before, picked(body.parts), click)
    except EditError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except EditingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except ModelError as error:
        raise _refused(error) from None
    names = parts_named(len(found.parts))
    return Selection(
        parts=[
            PartOut(
                name=name,
                clicks=[ClickIn(x=c.x, y=c.y, keep=c.keep) for c in part.clicks],
                choice=part.choice or 0,
                choices=3,
            )
            for name, part in zip(names, found.parts, strict=True)
        ],
        outline=found.outline,
        read=round(found.read, 3) if found.read is not None else None,
        place=found.place,
        seconds=round(time.perf_counter() - began, 3),
        waited=round(found.waited, 3),
        missed=found.missed,
    )


@router.post("/pictures/{picture_id}/edit")
def edit(picture_id: int, body: EditAsk, conn: Database, sight: Seeing, editor: Editors) -> Edited:
    """Makes the edits (the last one new), so the previews show them; nothing is saved."""
    image, key = _opened(conn, sight, picture_id, body.version)
    try:
        edits = edits_of(body.edits, body.version).edits
        editor.state(image, key, edits)
    except EditError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except EditingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except ModelError as error:
        raise _refused(error) from None
    made = editor.made(key, edits)
    return Edited(
        seconds=round(made.seconds, 3) if made else 0.0,
        place=made.place if made else None,
        waited=round(made.waited, 3) if made else 0.0,
        smeared=made.smeared if made else False,
    )


class SmallAsk(ApiModel):
    edit: EditStepIn  # the edits made so far (none: no edits), on the picture at their version
    fix: FixStepIn | None = None  # the fixes chosen: a dark photo is shown brightened


@router.post("/pictures/{picture_id}/looks/{look_id}", response_class=Response, responses=_WEBP)
def small_edited(
    picture_id: int,
    look_id: str,
    body: SmallAsk,
    conn: Database,
    sight: Seeing,
    editor: Editors,
    ai: Models,
) -> Response:
    """A small copy of the picture as its edits leave it, in a look: the Looks tab's, once the
    Edit tab has made edits or the Fix tab brightens it (without either, it asks for the kept
    copy by GET). A dark photo is brightened, and given its local contrast, as the whole picture
    measures; noise, blur and blocks are too small to see at this size."""
    look = own_looks.resolve(conn, look_id)
    if look is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That look isn't in your looks any more.")
    picture, now = opened_picture(conn, picture_id, body.edit.version)
    image, key = _opened(conn, sight, picture_id, body.edit.version)
    try:
        editing = edits_of(body.edit.edits, body.edit.version)
        small = editor.small(image, key, editing.edits, SMALL)
        fixing = fixing_of(body.fix)
        if fixing is not None and fixing.dark is not None:
            measured = sight.measured(
                (str(picture.path).casefold(), now, editing if editing.edits else None),
                lambda: editor.state(image, key, editing.edits) if editing.edits else image,
            )
            small = _brightened(small, fixing, measured, image.width, ai)
    except FixError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except EditError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except EditingError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except ModelError as error:
        raise _refused(error) from None
    made = through(small, look.grid)
    out = io.BytesIO()
    profile = made.info.get("icc_profile")
    kept = {"icc_profile": profile} if isinstance(profile, bytes) else {}
    made.save(out, format="WEBP", quality=80, method=2, **kept)
    return Response(out.getvalue(), media_type="image/webp")


def _brightened(
    small: Image.Image, fixing: Fixing, measured: Measure, across: int, ai: Ai
) -> Image.Image:
    """A small copy of the picture (`across` pixels wide at full size) brightened as the dark
    photo fix brightens all of it, with its local contrast; its see-through parts and colours
    kept."""
    profile = small.info.get("icc_profile")
    grey = small.mode in GREY_MODES
    colours, alpha = split_alpha(small)
    done = fixed(colours, fixing, measured, "fast", ai, step=across / small.width, light_only=True)
    shown = Image.fromarray(done)
    if alpha is not None:
        shown.putalpha(Image.fromarray(alpha))
    elif grey:
        shown = shown.convert("L")
    if isinstance(profile, bytes):
        shown.info["icc_profile"] = profile
    return shown


def opened_picture(
    conn: sqlite3.Connection, picture_id: int, asked: str | None, *, edited: bool = True
) -> tuple[Picture, str]:
    """A library picture to edit, and its version: one that's changed since the window read it
    (`asked`) is refused, as its parts were picked on what it was (`edited`: with edits made)."""
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't in your library any more."
        )
    now = version(row["modified"], row["size"])
    picture = picture_of(conn, picture_id, Path(row["path"]))
    if asked is not None and asked != now:
        raise HTTPException(status.HTTP_409_CONFLICT, changed(picture.path.name, edited=edited))
    return picture, now


def changed(name: str, *, edited: bool = True) -> str:
    """What a picture changed since its parts were picked says: with edits made on it, that they
    were let go; with parts picked only, that they're to be picked again."""
    if not edited:
        return (
            f"{name} changed since Mado read it, so the parts you picked may not be where they "
            "were. Pick them again on it as it is now."
        )
    return (
        f"{name} changed since Mado read it, so the parts you picked may not be where they "
        "were. Your edits were let go; start again with it as it is now."
    )


def _opened(
    conn: sqlite3.Connection, sight: Sight, picture_id: int, asked: str, *, edited: bool = True
) -> tuple[Image.Image, str]:
    picture, now = opened_picture(conn, picture_id, asked, edited=edited)
    try:
        image = sight.picture(picture, now)
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return image, picture_key(picture.path, now)


def _refused(error: ModelError) -> HTTPException:
    """A model that isn't downloaded yet (409: the window offers it), or that can't run (503)."""
    said = str(error)
    if "isn't downloaded yet" in said:
        return HTTPException(status.HTTP_409_CONFLICT, f"{said} Download it first.")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, said)
