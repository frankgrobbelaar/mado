"""Looks, as the Looks tab asks for them: Mado's and the owner's own, a small copy of a picture in
each, importing a .cube file, keeping the mix on the tab as a look, renaming and deleting one."""

import io
import sqlite3
import zlib
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Response, status
from PIL import Image
from pydantic import Field

from mado import own_looks, recipes
from mado.api.common import ApiModel, Copies, Database
from mado.batches import order_of
from mado.core.cube import CubeError
from mado.core.looks import Look, built_in
from mado.core.touches import Touches
from mado.looks import through
from mado.own_looks import Kept, LookNameError
from mado.pictures import NeedsFfmpegError, PictureGoneError, UnreadableError
from mado.previews import Source

router = APIRouter()

SMALL = 256  # a look's small copy of a picture, on its longer side
_KEEP = {"Cache-Control": "private, max-age=31536000, immutable"}  # its address names its version
_WEBP: dict[int | str, dict[str, object]] = {200: {"content": {"image/webp": {}}}}
_GONE = "That look isn't in your looks any more."

Amount = Annotated[int, Field(ge=0, le=100)]


class TouchesIn(ApiModel):
    """Each finishing touch's amount, 0 (off) to 100."""

    grain: Amount = 0
    vignette: Amount = 0
    glow: Amount = 0
    fade: Amount = 0
    leak: Amount = 0  # a light leak
    dust: Amount = 0

    def touches(self) -> Touches:
        return Touches(self.grain, self.vignette, self.glow, self.fade, self.leak, self.dust)


class LookIn(ApiModel):
    """The look step: a look by its id, at a strength, with its touches."""

    look: str  # "warm-film", or one of the owner's: "yours-3"
    strength: float = Field(default=1.0, ge=0, le=1)
    touches: TouchesIn = Field(default_factory=TouchesIn)


class LookOut(ApiModel):
    id: str  # "warm-film"
    name: str
    version: str  # changes when its table does: its small copies' addresses carry it


class YourLook(ApiModel):
    id: str  # "yours-3"
    name: str
    kind: Literal["cube", "mix"]  # a .cube file imported, or a mix kept
    points: int  # its table's points a side
    touches: TouchesIn  # a mix's, which picking it brings back
    source: str  # the .cube file's name, or the look mixed: "Warm film at 60%"
    added_at: str


class Looks(ApiModel):
    looks: list[LookOut]  # Mado's, the original first
    yours: list[YourLook]  # the owner's, oldest first


class ImportIn(ApiModel):
    path: str  # a .cube file, as Windows' file picker gave it


class KeepIn(ApiModel):
    name: str = Field(max_length=200)
    look: LookIn


class RenameIn(ApiModel):
    name: str = Field(max_length=200)


@router.get("/looks")
def looks(conn: Database) -> Looks:
    """Mado's looks and the owner's own."""
    return Looks(
        looks=[LookOut(id=look.id, name=look.name, version=_version(look)) for look in built_in()],
        yours=[_yours(kept) for kept in own_looks.listed(conn)],
    )


@router.get("/pictures/{picture_id}/looks/{look_id}", response_class=Response, responses=_WEBP)
def small_copy(picture_id: int, look_id: str, conn: Database, copies: Copies) -> Response:
    """A small copy of the picture in a look, made from its thumbnail: WebP, kept by the window
    (its address carries the picture's version and the look's)."""
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't in your library any more."
        )
    look = own_looks.resolve(conn, look_id)
    if look is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    try:
        path = copies.thumbnail(Source.of(row))
        with Image.open(path) as thumbnail:
            thumbnail.load()
            small = thumbnail.copy()
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except NeedsFfmpegError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except OSError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Mado couldn't keep a copy of it to show in its data folder: "
            f"{error.strerror or error}. Your picture is as it was.",
        ) from None
    small.thumbnail((SMALL, SMALL), Image.Resampling.LANCZOS)
    made = through(small, look.grid)
    out = io.BytesIO()
    profile = made.info.get("icc_profile")  # Pillow writes it only when it's given
    kept = {"icc_profile": profile} if isinstance(profile, bytes) else {}
    made.save(out, format="WEBP", quality=80, method=2, **kept)
    return Response(out.getvalue(), media_type="image/webp", headers=_KEEP)


@router.post("/looks/import", status_code=status.HTTP_201_CREATED)
def import_cube(body: ImportIn, conn: Database) -> YourLook:
    """Keeps a .cube file as one of the owner's looks, named after its title or its file."""
    try:
        kept = own_looks.imported(conn, Path(body.path), _now())
    except CubeError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{Path(body.path).name}: {error}"
        ) from None
    return _yours(kept)


@router.post("/looks", status_code=status.HTTP_201_CREATED)
def keep_mix(body: KeepIn, conn: Database) -> YourLook:
    """Keeps the mix on the Looks tab (a look, its strength and its touches) as a look."""
    look = own_looks.resolve(conn, body.look.look)
    if look is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    try:
        kept = own_looks.kept(
            conn, body.name, look, body.look.strength, body.look.touches.touches(), _now()
        )
    except LookNameError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return _yours(kept)


@router.put("/looks/{look_id}")
def rename(look_id: str, body: RenameIn, conn: Database) -> YourLook:
    """Gives one of the owner's looks a new name."""
    try:
        kept = own_looks.renamed(conn, look_id, body.name)
    except LookNameError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)
    return _yours(kept)


@router.delete("/looks/{look_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(look_id: str, conn: Database) -> None:
    """Deletes one of the owner's looks. Pictures made with it stay as they are. Not while a
    recipe uses it, or pictures waiting in the queue are made with it."""
    needed = _needed_by(conn, look_id)
    if needed is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, needed)
    if not own_looks.deleted(conn, look_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _GONE)


def _needed_by(conn: sqlite3.Connection, look_id: str) -> str | None:
    """What still needs a look, in a sentence: a recipe that uses it (a watch folder may run
    it), or pictures waiting in the queue made with it."""
    for kept in recipes.listed(conn):
        if any(step.get("step") == "look" and step.get("look") == look_id for step in kept.steps):
            return (
                f"Your recipe {kept.name} uses it. Change that recipe first, or delete it, then "
                "this look."
            )
    for row in conn.execute("SELECT recipe FROM jobs WHERE state IN ('queued', 'running')"):
        made = order_of(row["recipe"]).get("recipe")
        look = cast("dict[str, object]", made).get("look") if isinstance(made, dict) else None
        if isinstance(look, dict) and cast("dict[str, object]", look).get("look") == look_id:
            return (
                "Pictures waiting in the queue are made with it. Delete it once they're made, or "
                "take them out of the queue first."
            )
    return None


def _yours(kept: Kept) -> YourLook:
    touches = kept.touches
    return YourLook(
        id=kept.id,
        name=kept.name,
        kind=kept.kind,
        points=kept.points,
        touches=TouchesIn(
            grain=touches.grain,
            vignette=touches.vignette,
            glow=touches.glow,
            fade=touches.fade,
            leak=touches.leak,
            dust=touches.dust,
        ),
        source=kept.source,
        added_at=kept.added_at,
    )


def _version(look: Look) -> str:
    """A look's table, in eight letters: its small copies are made again when it changes."""
    return f"{zlib.crc32(look.grid.tobytes()) if look.grid is not None else 0:08x}"


def _now() -> datetime:
    return datetime.now().astimezone()
