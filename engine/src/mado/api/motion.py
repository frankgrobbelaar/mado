"""3D photos, as the Depth tab asks (mado/motion.py): what this PC can make one with
(`GET /pictures/{id}/motion`), making one into the cache to play in the page, how it's coming
on, the video itself, saving it as a new file beside the picture or into a folder, and letting it
go. Nothing is written to the owner's folders till they save it."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import Field

from mado.ai import DEPTH, DEPTH_FILE
from mado.api.common import ApiModel, Database, Models, Seeing, SetAside
from mado.api.edits import EditIn, edits_of
from mado.core.edits import EditError
from mado.core.motion import (
    ENCODERS,
    LENGTH,
    SECONDS,
    SIDES,
    Moving,
    about_bytes,
    video_size,
    webp_size,
)
from mado.editing import MOST_PIXELS
from mado.making import Picture, picture_of
from mado.motion import MotionError, Motions
from mado.pictures import NeedsFfmpegError, NeedsReaderError, PictureGoneError, UnreadableError
from mado.previews import version

router = APIRouter()

_ASIDE = (
    "It waits in Mado's quarantine, so Mado opens it to look at only. Put it back from History "
    "to make something of it."
)
_VIDEO: dict[int | str, dict[str, object]] = {200: {"content": {"video/mp4": {}, "image/webp": {}}}}


def _motions(request: Request) -> Motions:
    found: Motions = request.app.state.motions
    return found


class SizeChoice(ApiModel):
    size: Literal["1080p", "4k"]
    width: int
    height: int
    bytes: int  # about how big it comes out at the length asked for, as an MP4


class MotionFacts(ApiModel):
    """What this PC can make a picture's 3D photo with."""

    ffmpeg: bool  # Mado's ffmpeg is downloaded: an MP4 needs it
    encoder: str | None  # the H.264 encoder that works here ("h264_mf"); None with none
    encoder_name: str | None  # "Windows' own video encoder"
    sizes: list[SizeChoice]  # 1080p, and 4K when the picture has the pixels for it
    webp: SizeChoice  # an animated WebP's size
    seconds: list[int]  # the lengths it can be
    needs: list[str]  # downloads it waits for: the depth model


class MotionAsk(ApiModel):
    """A 3D photo of the picture as its edits leave it."""

    version: str
    edits: Annotated[list[EditIn], Field(default_factory=list[EditIn], max_length=64)]
    motion: Literal["push", "sway", "circle"] = "push"
    seconds: int = Field(default=LENGTH, ge=SECONDS[0], le=SECONDS[-1])
    amount: float = Field(default=0.5, ge=0, le=1)
    fill: Literal["fast", "best"] = "fast"
    size: Literal["1080p", "4k"] = "1080p"
    format: Literal["mp4", "webp"] = "mp4"


class MotionOut(ApiModel):
    id: str
    state: Literal["waiting", "making", "done", "failed"]
    progress: float
    seconds: float | None  # what making it took
    width: int
    height: int
    bytes: int
    format: Literal["mp4", "webp"]
    encoder_name: str | None  # what made an MP4
    problem: str | None


class MotionSave(ApiModel):
    folder: str | None = None  # None: beside the picture


class MotionSaved(ApiModel):
    path: str
    name: str
    history_id: int


@router.get("/pictures/{picture_id}/motion")
def motion_facts(
    picture_id: int,
    request: Request,
    conn: Database,
    sight: Seeing,
    ai: Models,
) -> MotionFacts:
    """What a picture's 3D photo can be made with here: ffmpeg and the H.264 encoder that works
    (looked for once), the sizes the picture has the pixels for, and what it waits for."""
    picture, now = _picture(conn, picture_id)
    try:
        seen = sight.of(picture, now)
    except (UnreadableError, PictureGoneError, NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    motions = _motions(request)
    encoder = motions.encoder()
    sizes: list[SizeChoice] = []
    for size in ("1080p", "4k"):
        if size == "4k" and max(seen.width, seen.height) < SIDES["4k"]:
            continue  # it would only be stretched
        width, height = video_size(seen.width, seen.height, size)
        moving = Moving(size=size)
        sizes.append(
            SizeChoice(
                size=size, width=width, height=height, bytes=about_bytes(moving, width, height)
            )
        )
    webp_w, webp_h = webp_size(seen.width, seen.height)
    webp = SizeChoice(
        size="1080p",
        width=webp_w,
        height=webp_h,
        bytes=about_bytes(Moving(format="webp"), webp_w, webp_h),
    )
    return MotionFacts(
        ffmpeg=motions.ffmpeg_ready(),
        encoder=encoder,
        encoder_name=ENCODERS.get(encoder) if encoder else None,
        sizes=sizes,
        webp=webp,
        seconds=list(SECONDS),
        needs=[DEPTH] if ai.edit_file(DEPTH, DEPTH_FILE) is None else [],
    )


@router.post("/pictures/{picture_id}/motion", status_code=status.HTTP_202_ACCEPTED)
def make_motion(
    picture_id: int,
    body: MotionAsk,
    request: Request,
    conn: Database,
    ai: Models,
    aside: SetAside,
) -> MotionOut:
    """Makes a 3D photo into the cache, on a thread of its own (the one asked for before it, if
    it isn't made yet, is let go): how it's coming on comes from /motion/{id}."""
    picture, now = _picture(conn, picture_id)
    if _aside(conn, picture_id, aside):
        raise HTTPException(status.HTTP_409_CONFLICT, _ASIDE)
    if body.version != now:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{picture.path.name} changed since Mado read it: look at it as it is now first.",
        )
    if ai.edit_file(DEPTH, DEPTH_FILE) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "It needs a model Mado downloads the first time it's asked for: download it first.",
        )
    pixels = _pixels(conn, picture_id)
    if pixels > MOST_PIXELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"It's {pixels / 1e6:.0f} megapixels, and Mado reads depth in pictures up to "
            f"{MOST_PIXELS / 1e6:.0f}: make a smaller copy of it on the Size tab, then make that "
            "a 3D photo.",
        )
    try:
        edits = edits_of(body.edits, now).edits
    except EditError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    moving = Moving(body.motion, body.seconds, body.amount, body.fill, body.size, body.format)
    asked = _motions(request).ask(picture_id, picture.path, now, moving, edits)
    return _out(asked.id, request)


@router.get("/motion/{motion_id}")
def motion_state(motion_id: str, request: Request) -> MotionOut:
    """How a 3D photo is coming on."""
    return _out(motion_id, request)


@router.get("/motion/{motion_id}/video", response_class=FileResponse, responses=_VIDEO)
def motion_video(motion_id: str, request: Request) -> FileResponse:
    """A 3D photo made: its MP4, or its animated WebP."""
    found = _motions(request).get(motion_id)
    if found is None or found.state != "done" or found.file is None or not found.file.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That 3D photo isn't made any more.")
    media = "video/mp4" if found.moving.format == "mp4" else "image/webp"
    return FileResponse(found.file, media_type=media)


@router.post("/motion/{motion_id}/save")
def save_motion(
    motion_id: str, body: MotionSave, request: Request, conn: Database, aside: SetAside
) -> MotionSaved:
    """Saves a 3D photo made as a new file beside its picture or into a folder chosen ("Harbour
    at dusk (3D photo).mp4"), with its line in History. A pasted picture's goes only into a folder
    chosen; the picture is never changed."""
    motions = _motions(request)
    found = motions.get(motion_id)
    if found is None or found.state != "done":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That 3D photo isn't made any more.")
    row = conn.execute("SELECT pasted FROM pictures WHERE id = ?", (found.picture_id,)).fetchone()
    pasted = bool(row and row["pasted"])
    if body.folder is None and pasted:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose a folder for it: a pasted picture isn't in any of your folders yet.",
        )
    folder = Path(body.folder) if body.folder else found.source.parent
    if body.folder and not folder.is_dir():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{folder} isn't there: its drive may be unplugged. Choose another folder.",
        )
    if aside.holds(folder):
        raise HTTPException(status.HTTP_409_CONFLICT, _ASIDE)
    try:
        saved = motions.save(motion_id, folder, found.source.stem, conn=conn, now=_now())
    except MotionError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    return MotionSaved(path=str(saved.path), name=saved.path.name, history_id=saved.history_id)


@router.delete("/motion/{motion_id}", status_code=status.HTTP_204_NO_CONTENT)
def drop_motion(motion_id: str, request: Request) -> None:
    """Lets a 3D photo go: one being made stops between frames, and its file goes."""
    _motions(request).drop(motion_id)


def _out(motion_id: str, request: Request) -> MotionOut:
    found = _motions(request).get(motion_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That 3D photo isn't made any more.")
    return MotionOut(
        id=found.id,
        state=found.state,
        progress=round(found.progress, 3),
        seconds=found.seconds,
        width=found.width,
        height=found.height,
        bytes=found.bytes,
        format=found.moving.format,
        encoder_name=ENCODERS.get(found.encoder) if found.encoder else None,
        problem=found.problem,
    )


def _picture(conn: sqlite3.Connection, picture_id: int) -> tuple[Picture, str]:
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't in your library any more."
        )
    return picture_of(conn, picture_id, Path(row["path"])), version(row["modified"], row["size"])


def _pixels(conn: sqlite3.Connection, picture_id: int) -> int:
    """How many pixels a picture has, as the library read it (0 when it doesn't know)."""
    row = conn.execute("SELECT width, height FROM pictures WHERE id = ?", (picture_id,)).fetchone()
    return int(row["width"] or 0) * int(row["height"] or 0) if row is not None else 0


def _aside(conn: sqlite3.Connection, picture_id: int, aside: SetAside) -> bool:
    row = conn.execute(
        "SELECT path, folder_id FROM pictures WHERE id = ?", (picture_id,)
    ).fetchone()
    return row is not None and row["folder_id"] is None and aside.holds(Path(row["path"]))


def _now() -> datetime:
    return datetime.now().astimezone()
