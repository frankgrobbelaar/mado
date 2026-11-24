"""The pictures: the grid by the day they were taken (a page at a time, for many thousands), one
picture's details and its neighbours, the copies the window shows, and reading one again."""

import json
import logging
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from mado import favourites, hdr, outside
from mado.api.common import ApiModel, Copies, Database, Finding, Paths, Searching, SetAside
from mado.core.files import kind_of
from mado.duplicates import Found, choices, kept
from mado.library import (
    HDR_STATES,
    file_time,
    save_facts,
    save_hdr,
    save_problem,
    save_waiting,
)
from mado.pictures import (
    InUseError,
    NeedsFfmpegError,
    NeedsReaderError,
    PictureGoneError,
    ShortOfMemoryError,
    UnreadableError,
    read_facts,
)
from mado.previews import Source, version
from mado.quarantine import Quarantine
from mado.search import Search
from mado.system import pictures_folder

router = APIRouter()
log = logging.getLogger(__name__)

type Order = Literal["newest", "oldest"]
type PictureState = Literal["ready", "waiting", "broken"]

PAGE = 200  # pictures a page, unless asked for fewer
_KEEP = {"Cache-Control": "private, max-age=31536000, immutable"}  # its address names its version
_NOT_HERE = "That picture isn't in your library any more."


class GroupTag(ApiModel):
    """A group of duplicates or a burst, on the tile of a picture kept from it."""

    key: int  # the group's number, which opens its review there
    kind: Literal["duplicates", "burst"]
    pictures: int  # in the group: "burst of 5", "2 copies"


class PictureItem(ApiModel):
    id: int
    name: str  # its file's name
    path: str
    format: str | None  # "JPEG", "HEIC"…; a RAW file's own ("CR3")
    # "waiting": a camera RAW listed while Mado's RAW reader comes; "broken": won't open
    state: PictureState
    raw: bool  # a camera RAW: read by Mado's RAW reader, and never written over
    hdr: bool = False  # an HDR photo whose gain map Mado reads: it wears an "HDR" tag
    width: int | None  # as it's shown
    height: int | None
    size: int  # bytes
    taken_at: str  # local time: "2026-11-12T18:42:07"
    version: str  # changes when its file does: its copies' addresses carry it
    group: GroupTag | None = None  # in the grid, a group's kept picture
    favourite: bool = False  # the owner gave it a heart
    outside: bool = (
        False  # opened from outside the library: dropped, picked, pasted, from File Explorer
    )


class DayCount(ApiModel):
    day: str  # "2026-11-14"
    pictures: int  # all of that day's, on this page or not


class PicturePage(ApiModel):
    pictures: list[PictureItem]
    days: list[DayCount]  # the days on this page, in its order
    total: int  # pictures in the whole list
    next: str | None  # where the next page starts; None on the last


class GainMapOut(ApiModel):
    """An HDR photo's gain map, as its page says it."""

    readable: bool  # Mado reads it, and keeps it through its tools
    stops: float | None  # how many stops past ordinary white its HDR rendition goes
    base_is_hdr: bool  # its picture is the HDR rendition, and the gain map makes the ordinary one
    colour: bool  # a gain map in colour, not grey
    width: int | None  # the gain map as stored
    height: int | None
    why: str | None  # why Mado can't keep it: "Its gain map is version 2.0, which Mado…"


class PictureDetails(PictureItem):
    gain_map: GainMapOut | None = None  # an HDR photo's, read from its file as it is now
    folder_id: int | None  # its library folder's number; None outside the library
    folder: str  # its library folder; outside the library, the folder it's in
    dir: str  # the folders between that and it: "2026/Trip"
    modified_at: str  # the file's time, local
    taken_from: Literal["camera", "file"]  # whose clock says when it was taken
    camera: str | None
    orientation: int | None  # EXIF's 1 to 8
    located: bool  # it carries where it was taken
    problem: str | None  # why it won't open
    damaged: bool  # the owner marked it as damaged: not asked about again till its file changes
    pasted: bool  # pasted from the clipboard, kept in Mado's data folder till it's saved
    aside: bool  # it waits in a quarantine: opened to look at only
    saves_to: str | None  # where Save puts a new picture first, when not beside it (a pasted one)


class Favourite(ApiModel):
    favourite: bool  # give it a heart, or take it back


class Neighbours(ApiModel):
    before: list[PictureItem]  # the pictures before it in the list, the nearest last
    after: list[PictureItem]  # after it, the nearest first


@dataclass(frozen=True)
class Shown:
    """Which pictures a list shows, and in which order."""

    folder: int | None
    inside: str  # a folder inside it: "2026/Trip"; "" for all of it
    words: str  # a search: by name, what a picture shows and its words (/search)
    order: Order
    favourites: bool = False  # only the owner's favourites, from outside the library too
    like: int | None = None  # the pictures most like this one (/search/like)


def _shown(
    folder: int | None = None,
    inside: Annotated[str, Query(alias="dir")] = "",
    q: str = "",
    order: Order = "newest",
    favourites: bool = False,
    like: int | None = None,
) -> Shown:
    return Shown(folder, inside.strip("/"), q, order, favourites, like)


Showing = Annotated[Shown, Depends(_shown)]


@router.get("/pictures")
def pictures(
    conn: Database,
    shown: Showing,
    finder: Finding,
    after: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = PAGE,
) -> PicturePage:
    """A page of the pictures, by the day they were taken: newest first, or oldest. `after` is
    where the page before ended. A picture kept from a group of duplicates or a burst says
    which, and a favourite says so."""
    where, values = shown_where(shown)
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
    tags = group_tags(finder.found(), choices(conn))
    hearts = favourites.among(conn, (row["id"] for row in page))
    return PicturePage(
        pictures=[item_of(row, tags.get(row["id"]), row["id"] in hearts) for row in page],
        days=[DayCount(day=day, pictures=counts.get(day, 0)) for day in days],
        total=total,
        next=f"{last['taken_at']}|{last['id']}" if last is not None else None,
    )


@router.get("/pictures/{picture_id}")
def picture(
    picture_id: int, conn: Database, aside: SetAside, copies: Copies, paths: Paths
) -> PictureDetails:
    """One picture, with everything Mado read of it. One from outside the library, which no
    scan looks after, is looked at as it is now: read again once its file changed (a Save in its
    place, say), 404 with why once it went; and it counts as opened again, its month before it's
    forgotten starting afresh. A camera RAW waiting for Mado's RAW reader asks for it."""
    row = _row(conn, picture_id)
    reader = copies.reader
    if reader is not None and row["raw"] and row["read_at"] and row["width"] is None:
        reader.ask()  # opening a RAW fetches its reader, as reading one does
    if row["folder_id"] is None:
        try:
            outside.open_picture(
                conn,
                Path(row["path"]),
                now=datetime.now().astimezone(),
                forget=copies.forget,
                data=paths,
                reader=copies.reader,
            )
        except outside.OpenError as error:
            raise HTTPException(error.status, str(error)) from None
        row = _row(conn, picture_id)
    return details(conn, row, aside)


@router.get("/pictures/{picture_id}/neighbours")
def neighbours(
    picture_id: int,
    conn: Database,
    shown: Showing,
    finding: Searching,
    count: Annotated[int, Query(ge=1, le=50)] = 8,
) -> Neighbours:
    """The pictures either side of one, in the list it was opened from: none for one outside
    the library, which isn't in a list, unless it was opened from the favourites. Opened from a
    search's results, or More like this, they're its neighbours there, in the results' order."""
    row = _row(conn, picture_id)
    if row["folder_id"] is None and not shown.favourites:
        return Neighbours(before=[], after=[])
    if shown.words.strip() or shown.like is not None:
        return _found_neighbours(conn, finding, shown, picture_id, count)
    where, values = shown_where(shown)
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
    hearts = favourites.among(conn, (each["id"] for each in (*before, *after)))
    return Neighbours(
        before=[item_of(each, None, each["id"] in hearts) for each in before],
        after=[item_of(each, None, each["id"] in hearts) for each in after],
    )


def _found_neighbours(
    conn: sqlite3.Connection, finding: Search, shown: Shown, picture_id: int, count: int
) -> Neighbours:
    """A picture's neighbours in a search's results (or More like this), as they're shown."""
    from mado.api.search import found_ids  # the search's own module builds on this one's lists

    order = found_ids(conn, finding, shown)
    if shown.like is not None and picture_id == shown.like:
        order = [picture_id, *order]  # the picture More like this was asked of leads its list
    if picture_id not in order:
        return Neighbours(before=[], after=[])
    at = order.index(picture_id)
    wanted = order[max(0, at - count) : at] + order[at + 1 : at + 1 + count]
    rows = {
        row["id"]: row
        for row in conn.execute(
            "SELECT * FROM pictures WHERE id IN (SELECT value FROM json_each(?))",
            (json.dumps(wanted),),
        )
    }
    hearts = favourites.among(conn, wanted)
    before = [rows[each] for each in order[max(0, at - count) : at] if each in rows]
    after = [rows[each] for each in order[at + 1 : at + 1 + count] if each in rows]
    return Neighbours(
        before=[item_of(each, None, each["id"] in hearts) for each in before],
        after=[item_of(each, None, each["id"] in hearts) for each in after],
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
        _made(lambda: copies.thumbnail(source), conn, picture_id),
        media_type="image/webp",
        headers=_KEEP,
    )


_VIEW: dict[int | str, dict[str, Any]] = {200: {"content": {"image/webp": {}, "image/jpeg": {}}}}


@router.get("/pictures/{picture_id}/view", response_class=FileResponse, responses=_VIEW)
def view(picture_id: int, conn: Database, copies: Copies) -> FileResponse:
    """It the size of a screen, at most 2560 pixels on its longer side (WebP): a camera RAW
    developed, as Save makes it; an HDR photo as an Ultra HDR JPEG, its gain map with it."""
    source = Source.of(_row(conn, picture_id))
    path = _made(lambda: copies.view(source), conn, picture_id)
    media = "image/jpeg" if path.suffix == ".jpg" else "image/webp"
    return FileResponse(path, media_type=media, headers=_KEEP)


@router.get("/pictures/{picture_id}/full", response_class=FileResponse, responses=_ANY_PICTURE)
def full(picture_id: int, conn: Database, copies: Copies) -> FileResponse:
    """It at full size: the picture itself when the window can show its format, else a copy it
    can (PNG)."""
    source = Source.of(_row(conn, picture_id))
    path, media = _made(lambda: copies.full(source), conn, picture_id)
    return FileResponse(path, media_type=media, headers=_KEEP)


@router.put("/pictures/{picture_id}/favourite")
def favourite(picture_id: int, body: Favourite, conn: Database, aside: SetAside) -> PictureDetails:
    """Gives a picture a heart, or takes it back: a favourite, in the library or from outside it,
    which the daily wallpaper can change to. The picture itself stays exactly as it is."""
    _row(conn, picture_id)
    favourites.set_favourite(conn, picture_id, body.favourite, datetime.now().astimezone())
    return details(conn, _row(conn, picture_id), aside)


@router.post("/pictures/{picture_id}/damaged")
def mark_damaged(picture_id: int, conn: Database, aside: SetAside) -> PictureDetails:
    """Marks a picture that won't open as damaged: it isn't asked about again, unless its file
    changes. The picture itself stays exactly as it is."""
    row = _row(conn, picture_id)
    if not row["problem"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That picture opens now, so there's nothing to mark."
        )
    with conn:
        conn.execute("UPDATE pictures SET damaged = 1 WHERE id = ?", (picture_id,))
    return details(conn, _row(conn, picture_id), aside)


@router.post("/pictures/{picture_id}/read")
def read_again(
    picture_id: int,
    conn: Database,
    copies: Copies,
    finder: Finding,
    aside: SetAside,
) -> PictureDetails:
    """Reads one picture again now (one that wouldn't open may have been mended since). A camera
    RAW is read by Mado's RAW reader, which it asks for while it isn't there."""
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
    try:
        save_facts(conn, picture_id, read_facts(path, kind, copies.reader), now=now)
        copies.thumbnail(Source.of(_row(conn, picture_id)))
    except NeedsReaderError:
        save_waiting(conn, picture_id, now=now)  # read once Mado's RAW reader is here
    except NeedsFfmpegError:
        pass  # read; its thumbnail waits for ffmpeg
    except OSError as error:  # read; its thumbnail is made when it's next asked for
        log.warning("Mado couldn't keep the thumbnail of %s: %s", path, error)
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (InUseError, ShortOfMemoryError) as error:  # nothing's wrong with it: as it was
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    except UnreadableError as error:
        save_problem(conn, picture_id, str(error), now=now)
    finder.wake()  # looked at as it is now
    return details(conn, _row(conn, picture_id), aside)


def group_tags(found: Found, chosen: Mapping[int, bool]) -> dict[int, GroupTag]:
    """The tag each group's kept pictures wear in the grid: the group's number, which opens its
    review there, its kind and how many pictures it holds."""
    tags: dict[int, GroupTag] = {}
    for group in found.groups:
        kind: Literal["duplicates", "burst"] = "burst" if group.kind == "burst" else "duplicates"
        tag = GroupTag(key=min(group.members), kind=kind, pictures=len(group.members))
        for member in kept(group, chosen):
            tags[member] = tag
    return tags


def shown_where(shown: Shown) -> tuple[str, list[object]]:
    """The pictures a list shows, as SQL: those in the grid (the library's, never one opened
    from outside it, unless it's a favourite and the list is the favourites), in a folder, with
    every word."""
    clauses = ["gone_at IS NULL", "read_at IS NOT NULL"]
    if shown.favourites:
        clauses.append("id IN (SELECT picture_id FROM favourites)")
    else:
        clauses.append("folder_id IS NOT NULL")
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
    if row["problem"]:
        return "broken"
    return "waiting" if row["raw"] and row["width"] is None else "ready"


def item_of(
    row: sqlite3.Row, group: GroupTag | None = None, favourite: bool = False
) -> PictureItem:
    return PictureItem(
        id=row["id"],
        name=row["name"],
        path=row["path"],
        format=row["format"],
        state=_state(row),
        raw=bool(row["raw"]),
        hdr=row["hdr"] == 1 and not row["problem"],
        width=row["width"],
        height=row["height"],
        size=row["size"],
        taken_at=row["taken_at"],
        version=version(row["modified"], row["size"]),
        group=group,
        favourite=favourite,
        outside=row["folder_id"] is None,
    )


def gain_map_of(conn: sqlite3.Connection, row: sqlite3.Row) -> GainMapOut | None:
    """An HDR photo's gain map, read from its file's headers as it is now (kept for the grid's
    tag when it differs from what the scan read); None for a picture without one."""
    path = Path(row["path"])
    if row["problem"] or row["raw"] or row["width"] is None or not path.is_file():
        return None  # its drive away: what the scan read stands
    found = hdr.facts(path)
    state = HDR_STATES[found.state]
    if state != row["hdr"]:
        save_hdr(conn, row["id"], found.state)
    if found.state == "none":
        return None
    info = found.info
    width, height = found.size or (None, None)
    return GainMapOut(
        readable=found.state == "hdr",
        stops=round(info.stops, 2) if info is not None else None,
        base_is_hdr=info.base_is_hdr if info is not None else False,
        colour=info.colour if info is not None else False,
        width=width,
        height=height,
        why=f"Its gain map {found.why}." if found.why else None,
    )


def details(conn: sqlite3.Connection, row: sqlite3.Row, aside: Quarantine) -> PictureDetails:
    """A picture in full: what Mado read of it, where it lives (its library folder, or the
    folder it's in, outside the library), whether it's pasted or waits in a quarantine, and an
    HDR photo's gain map."""
    outside_ = row["folder_id"] is None
    pasted = bool(row["pasted"])
    path = Path(row["path"])
    gain_map = gain_map_of(conn, row)
    # As its headers say now, gain map or none: the tag follows them.
    row = conn.execute("SELECT * FROM pictures WHERE id = ?", (row["id"],)).fetchone() or row
    if outside_:
        folder = str(path.parent)
    else:
        found = conn.execute(
            "SELECT path FROM folders WHERE id = ?", (row["folder_id"],)
        ).fetchone()
        folder = found["path"] if found else ""
    return PictureDetails(
        **item_of(row, None, favourites.is_favourite(conn, row["id"])).model_dump(
            by_alias=False, exclude={"group"}
        ),
        gain_map=gain_map,
        folder_id=row["folder_id"],
        folder=folder,
        dir=row["dir"],
        modified_at=file_time(row["modified"]),
        taken_from=row["taken_from"],
        camera=row["camera"],
        orientation=row["orientation"],
        located=bool(row["located"]),
        problem=row["problem"],
        damaged=bool(row["damaged"]),
        pasted=pasted,
        aside=outside_ and aside.holds(path),
        saves_to=str(pictures_folder()) if pasted else None,
    )


def _made[T](make: Callable[[], T], conn: sqlite3.Connection, picture_id: int) -> T:
    """A copy, made now if need be, or why it can't be, as the window shows it. A camera RAW
    whose pixels won't develop joins the pictures that won't open, as the scan reads only what it
    says of itself and its camera's preview; one held by another app, or too big for the memory
    free now, is as it was."""
    try:
        made = make()
    except PictureGoneError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (NeedsFfmpegError, NeedsReaderError) as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from None
    except UnreadableError as error:
        row = conn.execute("SELECT raw FROM pictures WHERE id = ?", (picture_id,)).fetchone()
        passing = isinstance(error, InUseError | ShortOfMemoryError)
        if row is not None and row["raw"] and not passing:
            save_problem(conn, picture_id, str(error), now=datetime.now().astimezone())
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    except OSError as error:  # keeping the copy, not the picture
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Mado couldn't keep a copy of it to show in its data folder: "
            f"{error.strerror or error}. Your picture is as it was.",
        ) from None
    return made
