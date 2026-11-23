"""The pictures: the grid by the day they were taken (a page at a time, for many thousands), one
picture's details and its neighbours, the copies the window shows, and reading one again."""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from mado.api.common import ApiModel, Copies, Database, Finding
from mado.core.files import kind_of
from mado.library import file_time, save_facts, save_problem
from mado.pictures import (
    InUseError,
    NeedsFfmpegError,
    PictureGoneError,
    UnreadableError,
    read_facts,
)
from mado.previews import Source, version

router = APIRouter()
log = logging.getLogger(__name__)

type Order = Literal["newest", "oldest"]
type PictureState = Literal["ready", "raw", "broken"]

PAGE = 200  # pictures a page, unless asked for fewer
_KEEP = {"Cache-Control": "private, max-age=31536000, immutable"}  # its address names its version
_NOT_HERE = "That picture isn't in your library any more."


class PictureItem(ApiModel):
    id: int
    name: str  # its file's name
    path: str
    format: str | None  # "JPEG", "HEIC"…; a RAW file's own ("CR3")
    state: PictureState  # "raw": listed, not readable yet; "broken": won't open
    width: int | None  # as it's shown
    height: int | None
    size: int  # bytes
    taken_at: str  # local time: "2026-11-12T18:42:07"
    version: str  # changes when its file does: its copies' addresses carry it


class DayCount(ApiModel):
    day: str  # "2026-11-14"
    pictures: int  # all of that day's, on this page or not


class PicturePage(ApiModel):
    pictures: list[PictureItem]
    days: list[DayCount]  # the days on this page, in its order
    total: int  # pictures in the whole list
    next: str | None  # where the next page starts; None on the last


class PictureDetails(PictureItem):
    folder_id: int
    folder: str  # its library folder
    dir: str  # the folders between that and it: "2026/Trip"
    modified_at: str  # the file's time, local
    taken_from: Literal["camera", "file"]  # whose clock says when it was taken
    camera: str | None
    orientation: int | None  # EXIF's 1 to 8
    located: bool  # it carries where it was taken
    problem: str | None  # why it won't open
    damaged: bool  # the owner marked it as damaged: not asked about again till its file changes


class Neighbours(ApiModel):
    before: list[PictureItem]  # the pictures before it in the list, the nearest last
    after: list[PictureItem]  # after it, the nearest first


@dataclass(frozen=True)
class Shown:
    """Which pictures a list shows, and in which order."""

    folder: int | None
    inside: str  # a folder inside it: "2026/Trip"; "" for all of it
    words: str  # every word must be in a picture's name
    order: Order


def _shown(
    folder: int | None = None,
    inside: Annotated[str, Query(alias="dir")] = "",
    q: str = "",
    order: Order = "newest",
) -> Shown:
    return Shown(folder, inside.strip("/"), q, order)


Showing = Annotated[Shown, Depends(_shown)]


@router.get("/pictures")
def pictures(
    conn: Database,
    shown: Showing,
    after: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = PAGE,
) -> PicturePage:
    """A page of the pictures, by the day they were taken: newest first, or oldest. `after` is
    where the page before ended."""
    where, values = _where(shown)
    total: int = conn.execute(
        f"SELECT COUNT(*) FROM pictures WHERE {where}",  # noqa: S608 - built of fixed pieces
        values,
    ).fetchone()[0]
    newest = shown.order == "newest"
    paged, paged_values = where, list(values)
    if after:
        taken, _, number = after.rpartition("|")
        paged += f" AND (taken_at, id) {'<' if newest else '>'} (?, ?)"
        paged_values += [taken, int(number) if number.isdigit() else 0]
    way = "DESC" if newest else "ASC"
    rows = conn.execute(
        f"""SELECT * FROM pictures WHERE {paged}
            ORDER BY taken_at {way}, id {way} LIMIT ?""",  # noqa: S608 - built of fixed pieces
        [*paged_values, limit + 1],
    ).fetchall()
    page = rows[:limit]
    days = list(dict.fromkeys(str(row["taken_at"])[:10] for row in page))
    counts: dict[str, int] = {}
    if days:
        marks = ", ".join("?" for _ in days)
        counts = {
            row["day"]: row["pictures"]
            for row in conn.execute(
                f"""SELECT substr(taken_at, 1, 10) AS day, COUNT(*) AS pictures
                    FROM pictures WHERE {where} AND substr(taken_at, 1, 10) IN ({marks})
                    GROUP BY day""",  # noqa: S608 - built of fixed pieces
                [*values, *days],
            )
        }
    last = page[-1] if len(rows) > limit else None
    return PicturePage(
        pictures=[_item(row) for row in page],
        days=[DayCount(day=day, pictures=counts.get(day, 0)) for day in days],
        total=total,
        next=f"{last['taken_at']}|{last['id']}" if last is not None else None,
    )


@router.get("/pictures/{picture_id}")
def picture(picture_id: int, conn: Database) -> PictureDetails:
    """One picture, with everything Mado read of it."""
    return _details(conn, _row(conn, picture_id))


@router.get("/pictures/{picture_id}/neighbours")
def neighbours(
    picture_id: int,
    conn: Database,
    shown: Showing,
    count: Annotated[int, Query(ge=1, le=50)] = 8,
) -> Neighbours:
    """The pictures either side of one, in the list it was opened from."""
    row = _row(conn, picture_id)
    where, values = _where(shown)
    key = [row["taken_at"], row["id"]]
    newer = conn.execute(
        f"""SELECT * FROM pictures WHERE {where} AND (taken_at, id) > (?, ?)
            ORDER BY taken_at, id LIMIT ?""",  # noqa: S608 - built of fixed pieces
        [*values, *key, count],
    ).fetchall()
    older = conn.execute(
        f"""SELECT * FROM pictures WHERE {where} AND (taken_at, id) < (?, ?)
            ORDER BY taken_at DESC, id DESC LIMIT ?""",  # noqa: S608 - built of fixed pieces
        [*values, *key, count],
    ).fetchall()
    if shown.order == "newest":
        before, after = list(reversed(newer)), older
    else:
        before, after = list(reversed(older)), newer
    return Neighbours(
        before=[_item(each) for each in before], after=[_item(each) for each in after]
    )


_PICTURE: dict[int | str, dict[str, Any]] = {200: {"content": {"image/webp": {}}}}
_ANY_PICTURE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}
}


@router.get("/pictures/{picture_id}/thumbnail", response_class=FileResponse, responses=_PICTURE)
def thumbnail(picture_id: int, conn: Database, copies: Copies) -> FileResponse:
    """Its thumbnail, about 512 pixels on its longer side (WebP)."""
    source = Source.of(_row(conn, picture_id))
    return FileResponse(
        _made(lambda: copies.thumbnail(source)), media_type="image/webp", headers=_KEEP
    )


@router.get("/pictures/{picture_id}/view", response_class=FileResponse, responses=_PICTURE)
def view(picture_id: int, conn: Database, copies: Copies) -> FileResponse:
    """It the size of a screen, at most 2560 pixels on its longer side (WebP)."""
    source = Source.of(_row(conn, picture_id))
    return FileResponse(_made(lambda: copies.view(source)), media_type="image/webp", headers=_KEEP)


@router.get("/pictures/{picture_id}/full", response_class=FileResponse, responses=_ANY_PICTURE)
def full(picture_id: int, conn: Database, copies: Copies) -> FileResponse:
    """It at full size: the picture itself when the window can show its format, else a copy it
    can (PNG)."""
    source = Source.of(_row(conn, picture_id))
    path, media = _made(lambda: copies.full(source))
    return FileResponse(path, media_type=media, headers=_KEEP)


@router.post("/pictures/{picture_id}/damaged")
def mark_damaged(picture_id: int, conn: Database) -> PictureDetails:
    """Marks a picture that won't open as damaged: it isn't asked about again, unless its file
    changes. The picture itself stays exactly as it is."""
    row = _row(conn, picture_id)
    if not row["problem"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That picture opens now, so there's nothing to mark."
        )
    with conn:
        conn.execute("UPDATE pictures SET damaged = 1 WHERE id = ?", (picture_id,))
    return _details(conn, _row(conn, picture_id))


@router.post("/pictures/{picture_id}/read")
def read_again(picture_id: int, conn: Database, copies: Copies, finder: Finding) -> PictureDetails:
    """Reads one picture again now (one that wouldn't open may have been mended since)."""
    row = _row(conn, picture_id)
    path = Path(row["path"])
    try:
        stat = path.stat()
    except OSError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(PictureGoneError(path))) from None
    with conn:
        conn.execute(
            "UPDATE pictures SET size = ?, modified = ? WHERE id = ?",
            (stat.st_size, stat.st_mtime_ns, picture_id),
        )
    copies.forget([picture_id])
    kind = kind_of(path.name) or "picture"
    now = datetime.now().astimezone()
    if kind != "raw":
        try:
            save_facts(conn, picture_id, read_facts(path, kind), now=now)
            copies.thumbnail(Source.of(_row(conn, picture_id)))
        except NeedsFfmpegError:
            pass  # read; its thumbnail waits for ffmpeg
        except OSError as error:  # read; its thumbnail is made when it's next asked for
            log.warning("Mado couldn't keep the thumbnail of %s: %s", path, error)
        except PictureGoneError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
        except InUseError as error:  # nothing's wrong with it: left as it was
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
        except UnreadableError as error:
            save_problem(conn, picture_id, str(error), now=now)
    finder.wake()  # looked at as it is now
    return _details(conn, _row(conn, picture_id))


def _where(shown: Shown) -> tuple[str, list[object]]:
    """The pictures a list shows, as SQL: those in the grid, in a folder, with every word."""
    clauses = ["gone_at IS NULL", "read_at IS NOT NULL"]
    values: list[object] = []
    if shown.folder is not None:
        clauses.append("folder_id = ?")
        values.append(shown.folder)
        if shown.inside:
            clauses.append("(dir = ? OR substr(dir, 1, ?) = ?)")
            values += [shown.inside, len(shown.inside) + 1, f"{shown.inside}/"]
    for word in shown.words.split():
        clauses.append("name LIKE ? ESCAPE '\\'")
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        values.append(f"%{escaped}%")
    return " AND ".join(clauses), values


def _row(conn: sqlite3.Connection, picture_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM pictures WHERE id = ? AND gone_at IS NULL", (picture_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_HERE)
    return row


def _state(row: sqlite3.Row) -> PictureState:
    if row["raw"]:
        return "raw"
    return "broken" if row["problem"] else "ready"


def _item(row: sqlite3.Row) -> PictureItem:
    return PictureItem(
        id=row["id"],
        name=row["name"],
        path=row["path"],
        format=row["format"],
        state=_state(row),
        width=row["width"],
        height=row["height"],
        size=row["size"],
        taken_at=row["taken_at"],
        version=version(row["modified"], row["size"]),
    )


def _details(conn: sqlite3.Connection, row: sqlite3.Row) -> PictureDetails:
    folder = conn.execute("SELECT path FROM folders WHERE id = ?", (row["folder_id"],)).fetchone()
    return PictureDetails(
        **_item(row).model_dump(by_alias=False),
        folder_id=row["folder_id"],
        folder=folder["path"] if folder else "",
        dir=row["dir"],
        modified_at=file_time(row["modified"]),
        taken_from=row["taken_from"],
        camera=row["camera"],
        orientation=row["orientation"],
        located=bool(row["located"]),
        problem=row["problem"],
        damaged=bool(row["damaged"]),
    )


def _made[T](make: Callable[[], T]) -> T:
    """A copy, made now if need be, or why it can't be, as the window shows it."""
    try:
        made = make()
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except NeedsFfmpegError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except OSError as error:  # keeping the copy, not the picture
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Mado couldn't keep a copy of it to show in its data folder: "
            f"{error.strerror or error}. Your picture is as it was.",
        ) from None
    return made
