"""History: what Mado did, a week of days at a time, newest first, with its undo (taking a new
picture away, putting a replaced original back: a picture's changes newest first; putting back a
picture set aside from its duplicates, or all of a review's) and clearing it; and the
quarantine, what waits there on each drive, and emptying one."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from mado import batches, history
from mado.api.common import ApiModel, Copies, Database, Finding, Paths, Scans, SetAside
from mado.api.jobs import PictureRef
from mado.core.batch import at_night
from mado.core.files import kind_of
from mado.core.motion import MOTION_WORDS
from mado.history import Entry, UndoError
from mado.pictures import (
    NeedsFfmpegError,
    NeedsReaderError,
    PictureGoneError,
    UnreadableError,
    decode,
)
from mado.previews import THUMBNAIL, Source, save_copy, version
from mado.quarantine import DAYS, by_drive, empty

router = APIRouter()

Day = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]
KEEPS: dict[str, timedelta | None] = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "nothing": None,
}


class EntryOut(ApiModel):
    id: int
    at: str  # local time, with its offset
    kind: Literal["made", "replaced", "emptied", "aside"]
    name: str  # the original's file name; the drive, for a quarantine emptied; 'aside': its own
    made_for: str | None  # what its size made it for: "TV 8K"
    look: str | None  # what it was made with: "Warm film at 60%"
    edit: str | None  # what was edited first: "erased a part"
    restore: str | None  # what restoring did: "filled its scratches and dust"
    fix: str | None  # what the fixes did: "took out noise"
    depth: str | None  # the depth tools: "portrait blur at f/2.8"; a video: "into a 3D photo"
    original: str | None
    result: str | None
    result_name: str | None
    aside: str | None  # what waits in quarantine for it now
    aside_until: str | None  # the day the clear-out takes it: "2026-12-22"
    cleared_at: str | None
    cleared_by: Literal["days", "owner"] | None  # the clear-out after its days, or the owner
    undone_at: str | None
    bytes: int | None
    picture: PictureRef | None  # a picture to show beside it, while the library has one
    can_undo: bool  # "Take it away", "Put back"
    can_redo: bool  # "Put it back", for a picture taken away; "Replace it again"
    batch: int | None  # the batch it was made in, which History shows as one line
    kept_name: str | None  # 'aside': the picture of its group that was kept
    review: int | None  # 'aside': the review it was set aside in, which History shows as one line


class BatchLine(ApiModel):
    """A batch as History's one line for it: what it made, and what undoes all of it."""

    id: int
    name: str  # "Holiday prints"
    source: str  # where its pictures came from: "Holiday"
    watch: str | None  # the watch folder that made it: "To TV"
    how: Literal["new", "replace"]
    made_for: str | None
    look: str | None
    edit: str | None  # "cut out the subject"
    restore: str | None  # "coloured it"
    fix: str | None  # "took out noise"
    depth: str | None  # "portrait blur at f/2.8"
    purpose: str | None  # what its size made them for: "tv"
    into: str  # where they went: "Holiday › Edited"
    made: int  # its pictures made, not taken away or put back
    undone: int  # those taken away, or put back
    failed: list[str]  # the pictures that didn't work
    overnight: bool  # made at night
    can_undo: bool  # "Take them away", "Put the originals back"
    can_redo: bool
    working: bool  # some of its pictures are still in the queue: undone as a whole once done
    drive: str | None  # where what it set aside waits: "D:"
    aside_until: str | None  # the day the clear-out takes it
    picture: PictureRef | None


class ReviewLine(ApiModel):
    """A review of duplicates and bursts as History's one line for it: what it set aside, and
    what puts all of it back."""

    id: int
    at: str
    duplicates: int  # groups of duplicates whose rest it set aside
    bursts: int  # and bursts
    pictures: int  # it set aside
    bytes: int  # what that freed
    back: int  # put back since
    cleared: int  # cleared out of quarantine since: after their days, or emptied
    can_undo: bool  # "Put them back"
    drives: list[str]  # where what it set aside waits: "D:"
    aside_until: str | None  # the day the clear-out takes them
    picture: PictureRef | None  # a picture it kept


class HistoryOut(ApiModel):
    entries: list[EntryOut]  # newest first
    older: str | None  # the day the next page starts before; None: that's all
    batches: list[BatchLine]  # the batches its lines were made in
    reviews: list[ReviewLine]  # the reviews its lines were set aside in


class BatchUndone(ApiModel):
    done: int  # lines undone (or done again)
    problems: list[str]  # why any couldn't be, picture by picture


class MadeToday(ApiModel):
    id: int  # its History line
    name: str  # the original's, without its extension
    made_for: str | None  # "TV 8K"
    look: str | None  # "Warm film at 60%"
    edit: str | None  # "erased a part"
    restore: str | None  # "filled its scratches and dust"
    fix: str | None  # "took out noise"
    depth: str | None  # "portrait blur at f/2.8", "into a 3D photo"


class ClearHistory(ApiModel):
    keep: Literal["day", "week", "month", "nothing"]


class Cleared(ApiModel):
    cleared: int


class DriveAside(ApiModel):
    drive: str  # "D:"
    folder: str  # its quarantine
    bytes: int


class EmptyQuarantine(ApiModel):
    drive: str


class Emptied(ApiModel):
    bytes: int  # how much went for good


@router.get("/history")
def what_mado_did(
    conn: Database, before: Day = None, q: Annotated[str, Query(max_length=200)] = ""
) -> HistoryOut:
    """What Mado did on its latest days with anything on them (a week's worth), newest first.
    `before` ("2026-11-15", the page's `older`) asks for the days before that one, and `q` for
    what names a picture or folder."""
    found = history.page(conn, before=before, query=q)
    batch_ids = list(dict.fromkeys(each.batch_id for each in found.entries if each.batch_id))
    lines = [_batch_line(conn, each) for each in batch_ids]
    review_ids = list(dict.fromkeys(each.review_id for each in found.entries if each.review_id))
    reviews = [_review_line(conn, each) for each in review_ids]
    return HistoryOut(
        entries=[_out(conn, each) for each in found.entries],
        older=found.older,
        batches=[line for line in lines if line is not None],
        reviews=[line for line in reviews if line is not None],
    )


@router.post("/history/batches/{batch_id}/undo")
def undo_batch(batch_id: int, conn: Database, quarantine: SetAside) -> BatchUndone:
    """Undoes a whole batch: its new pictures taken away (into quarantine), or its originals put
    back. Each picture's own line says why one couldn't be. Not while some of its pictures are
    still in the queue: what's made after would be left as it is."""
    _done_with(conn, batch_id)
    done, problems = history.undo_batch(conn, quarantine, batch_id, _now())
    return BatchUndone(done=done, problems=problems)


@router.post("/history/batches/{batch_id}/redo")
def redo_batch(batch_id: int, conn: Database, quarantine: SetAside) -> BatchUndone:
    """Undoes a batch's undo: its new pictures put back, or its originals replaced again."""
    _done_with(conn, batch_id)
    done, problems = history.redo_batch(conn, quarantine, batch_id, _now())
    return BatchUndone(done=done, problems=problems)


@router.post("/history/reviews/{review_id}/undo")
def undo_review(
    review_id: int, conn: Database, quarantine: SetAside, scanner: Scans, finder: Finding
) -> BatchUndone:
    """Puts back every picture a review set aside, newest first, each where it was; the library
    reads them again. Each picture's own line says why one couldn't be."""
    done, problems = history.undo_review(conn, quarantine, review_id, _now())
    if done:
        scanner.request()
        finder.wake()
    return BatchUndone(done=done, problems=problems)


@router.get("/history/today")
def made_today(conn: Database) -> list[MadeToday]:
    """The pictures made today, newest first, for Home."""
    today = _now().date().isoformat()
    rows = conn.execute(
        """SELECT id, name, made_for, look, edit, restore, fix, depth FROM history
           WHERE kind IN ('made', 'replaced') AND undone_at IS NULL AND substr(at, 1, 10) = ?
           ORDER BY at DESC, id DESC LIMIT 12""",
        (today,),
    ).fetchall()
    return [
        MadeToday(
            id=row["id"],
            name=PureWindowsPath(row["name"]).stem,
            made_for=row["made_for"],
            look=row["look"],
            edit=row["edit"],
            restore=row["restore"],
            fix=row["fix"],
            depth=row["depth"],
        )
        for row in rows
    ]


_THUMBNAIL: dict[int | str, dict[str, Any]] = {200: {"content": {"image/webp": {}}}}


@router.get("/history/{entry_id}/thumbnail", response_class=FileResponse, responses=_THUMBNAIL)
def made_thumbnail(entry_id: int, conn: Database, paths: Paths, copies: Copies) -> FileResponse:
    """A thumbnail of the picture a line made (WebP): the library's, or made now from the picture
    itself when it's outside the library; for a 3D photo, its picture's. Only a picture Mado
    made."""
    found = history.entry(conn, entry_id)
    if found is None or not found.result or found.undone_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That picture isn't there any more.")
    video = bool(found.depth and found.depth.startswith(MOTION_WORDS))
    result = Path(found.original) if video and found.original else Path(found.result)
    row = conn.execute(
        "SELECT * FROM pictures WHERE path = ? AND gone_at IS NULL AND read_at IS NOT NULL",
        (str(result),),
    ).fetchone()
    try:
        if row is not None:
            made = copies.thumbnail(Source.of(row))
        else:
            stat = result.stat()
            made = (
                paths.cache / "made" / f"{entry_id}-{version(stat.st_mtime_ns, stat.st_size)}.webp"
            )
            if not made.is_file():
                image = decode(result, kind_of(result.name) or "picture", longest=THUMBNAIL)
                save_copy(image, made, "WEBP", quality=80, method=4)
    except OSError, PictureGoneError, UnreadableError, NeedsFfmpegError, NeedsReaderError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That picture isn't there any more."
        ) from None
    return FileResponse(
        made, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.post("/history/{entry_id}/undo")
def undo(
    entry_id: int, conn: Database, quarantine: SetAside, scanner: Scans, finder: Finding
) -> EntryOut:
    """Takes a new picture away (into quarantine, put back from here), puts a replaced original
    back (the made picture going into quarantine in its place), or puts a picture set aside from
    its duplicates back where it was (the library reads it again)."""
    try:
        done = history.undo(conn, quarantine, entry_id, _now())
    except UndoError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    if done.kind == "aside":
        _keep_put_back(conn, done)
        scanner.request()
        finder.wake()
    return _out(conn, done)


def _keep_put_back(conn: sqlite3.Connection, line: Entry) -> None:
    """A picture put back on its own is one the owner keeps: setting its group aside again
    leaves it. (A whole review put back is the review as it was, Mado's picks and all.)"""
    row = conn.execute(
        "SELECT id, size, modified FROM pictures WHERE path = ?", (line.original,)
    ).fetchone()
    if row is None:
        return
    with conn:
        conn.execute(
            """INSERT INTO choices (picture_id, keep, size, modified, at) VALUES (?, 1, ?, ?, ?)
               ON CONFLICT (picture_id) DO UPDATE SET keep = 1, size = excluded.size,
                   modified = excluded.modified, at = excluded.at""",
            (row["id"], row["size"], row["modified"], _now().isoformat(timespec="seconds")),
        )


@router.post("/history/{entry_id}/redo")
def redo(entry_id: int, conn: Database, quarantine: SetAside) -> EntryOut:
    """Puts a new picture that was taken away back where it was, or replaces an original put
    back again (the original going into quarantine once more)."""
    try:
        done = history.redo(conn, quarantine, entry_id, _now())
    except UndoError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _out(conn, done)


@router.post("/history/clear")
def clear_history(body: ClearHistory, conn: Database) -> Cleared:
    """Forgets what Mado did before the last day, week or month, or all of it. What still waits
    in quarantine stays, so it can be put back, and no picture changes."""
    return Cleared(cleared=history.clear(conn, keep=KEEPS[body.keep], now=_now()))


@router.get("/quarantine")
def set_aside(conn: Database, quarantine: SetAside) -> list[DriveAside]:
    """What waits in quarantine on each drive."""
    found: list[DriveAside] = []
    for drive, size in sorted(by_drive(conn).items()):
        folder = quarantine.root(Path(f"{drive}/"))
        found.append(DriveAside(drive=drive, folder=str(folder), bytes=size))
    return found


@router.post("/quarantine/empty")
def empty_quarantine(body: EmptyQuarantine, conn: Database, quarantine: SetAside) -> Emptied:
    """Deletes everything set aside on a drive now, before its days are up: it can't be put
    back. History says so."""
    return Emptied(bytes=empty(conn, quarantine, body.drive, now=_now()))


def _out(conn: sqlite3.Connection, found: Entry) -> EntryOut:
    gone = found.cleared_at is not None
    can_undo = found.undone_at is None and (
        (found.kind == "made" and found.result is not None)
        or (found.kind in ("replaced", "aside") and found.aside is not None and not gone)
    )
    can_redo = (
        found.kind not in ("emptied", "aside")
        and found.undone_at is not None
        and found.aside is not None
        and not gone
    )
    return EntryOut(
        id=found.id,
        at=found.at,
        kind=found.kind,
        name=found.name,
        made_for=found.made_for,
        look=found.look,
        edit=found.edit,
        restore=found.restore,
        fix=found.fix,
        depth=found.depth,
        original=found.original,
        result=found.result,
        result_name=PureWindowsPath(found.result).name if found.result else None,
        aside=found.aside if not gone else None,
        aside_until=_until(found.aside_at) if found.aside and not gone else None,
        cleared_at=found.cleared_at,
        cleared_by=found.cleared_by,
        undone_at=found.undone_at,
        bytes=found.bytes,
        picture=_picture(conn, found),
        can_undo=can_undo,
        can_redo=can_redo,
        batch=found.batch_id,
        kept_name=PureWindowsPath(found.kept).name if found.kept else None,
        review=found.review_id,
    )


def _working(conn: sqlite3.Connection, batch_id: int) -> bool:
    """Whether some of a batch's pictures are still in the queue."""
    found = conn.execute(
        "SELECT 1 FROM jobs WHERE batch_id = ? AND state IN ('queued', 'running') LIMIT 1",
        (batch_id,),
    ).fetchone()
    return found is not None


def _done_with(conn: sqlite3.Connection, batch_id: int) -> None:
    if _working(conn, batch_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Some of its pictures are still in the queue. Once they're made, or taken out of "
            "the queue, this undoes all of it.",
        )


def _batch_line(conn: sqlite3.Connection, batch_id: int) -> BatchLine | None:
    """A batch's one line in History."""
    row = conn.execute(
        """SELECT b.*, w.path AS watch_path FROM batches AS b
           LEFT JOIN watch_folders AS w ON w.id = b.watch_id WHERE b.id = ?""",
        (batch_id,),
    ).fetchone()
    if row is None:
        return None
    # Counted by SQLite: a batch can hold thousands of lines.
    counts = conn.execute(
        """SELECT COUNT(*) FILTER (WHERE h.undone_at IS NULL) AS made,
                  COUNT(*) FILTER (WHERE h.undone_at IS NOT NULL) AS undone,
                  COUNT(*) FILTER (WHERE h.undone_at IS NULL AND (
                      (h.kind = 'made' AND h.result IS NOT NULL)
                      OR (h.kind = 'replaced' AND h.aside IS NOT NULL AND h.cleared_at IS NULL)
                  )) AS undoable,
                  COUNT(*) FILTER (WHERE h.undone_at IS NOT NULL AND h.aside IS NOT NULL
                                   AND h.cleared_at IS NULL) AS redoable
           FROM history AS h JOIN jobs AS j ON j.id = h.job_id WHERE j.batch_id = ?""",
        (batch_id,),
    ).fetchone()
    aside = conn.execute(
        """SELECT h.aside, h.aside_at FROM history AS h JOIN jobs AS j ON j.id = h.job_id
           WHERE j.batch_id = ? AND h.aside IS NOT NULL AND h.cleared_at IS NULL
           ORDER BY h.id DESC LIMIT 1""",
        (batch_id,),
    ).fetchone()
    newest = history.of_batch(conn, batch_id, limit=10)
    steps, saving = batches.kept_steps(row["steps"])
    failed = [
        Path(each["source"]).name
        for each in conn.execute(
            "SELECT source FROM jobs WHERE batch_id = ? AND state = 'failed' ORDER BY position",
            (batch_id,),
        )
    ]
    order = batches.first_order(conn, batch_id)
    made_for, look, edit = order.get("label"), order.get("look"), order.get("edit")
    fix, depth, restore = order.get("fix"), order.get("depth"), order.get("restore")
    started = row["started_at"]
    try:
        overnight = started is not None and at_night(datetime.fromisoformat(started))
    except ValueError:
        overnight = False
    watch = row["watch_path"]
    return BatchLine(
        id=batch_id,
        name=row["name"],
        source=row["source"],
        watch=PureWindowsPath(watch).name if watch else None,
        how="replace" if saving.get("how") == "replace" else "new",
        made_for=made_for if isinstance(made_for, str) else None,
        look=look if isinstance(look, str) else None,
        edit=edit if isinstance(edit, str) else None,
        restore=restore if isinstance(restore, str) else None,
        fix=fix if isinstance(fix, str) else None,
        depth=depth if isinstance(depth, str) else None,
        purpose=batches.purpose_of(conn, steps),
        into=batches.into_words(saving, row["shared"]),
        made=counts["made"],
        undone=counts["undone"],
        failed=failed,
        overnight=overnight,
        can_undo=counts["undoable"] > 0,
        can_redo=counts["redoable"] > 0,
        working=_working(conn, batch_id),
        drive=str(aside["aside"])[:2] if aside else None,
        aside_until=_until(aside["aside_at"]) if aside else None,
        picture=next(
            (found for each in newest if (found := _picture(conn, each)) is not None), None
        ),
    )


def _review_line(conn: sqlite3.Connection, review_id: int) -> ReviewLine | None:
    """A review's one line in History."""
    row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if row is None:
        return None
    lines = history.of_review(conn, review_id)
    waiting = [
        each for each in lines if each.undone_at is None and each.aside and not each.cleared_at
    ]
    drives = sorted({PureWindowsPath(each.aside or "").drive.upper() for each in waiting} - {""})
    until = [day for each in waiting if (day := _until(each.aside_at)) is not None]
    return ReviewLine(
        id=review_id,
        at=row["at"],
        duplicates=row["duplicates"],
        bursts=row["bursts"],
        pictures=len(lines),
        bytes=sum(each.bytes or 0 for each in lines),
        back=sum(1 for each in lines if each.undone_at is not None),
        cleared=sum(1 for each in lines if each.cleared_at is not None),
        can_undo=bool(waiting),
        drives=drives,
        aside_until=max(until) if until else None,
        picture=next(
            (found for each in lines[:10] if (found := _picture(conn, each)) is not None), None
        ),
    )


def _picture(conn: sqlite3.Connection, found: Entry) -> PictureRef | None:
    """The picture to show beside a line: the one made, while it's in the library, else its
    original; for a picture set aside, itself once it's back, else the one its group kept."""
    paths = (
        (found.original, found.kept) if found.kind == "aside" else (found.result, found.original)
    )
    for path in paths:
        if not path:
            continue
        row = conn.execute(
            """SELECT id, modified, size FROM pictures
               WHERE path = ? AND gone_at IS NULL AND read_at IS NOT NULL AND problem IS NULL""",
            (path,),
        ).fetchone()
        if row is not None:
            return PictureRef(id=row["id"], version=version(row["modified"], row["size"]))
    return None


def _until(aside_at: str | None) -> str | None:
    if not aside_at:
        return None
    try:
        return (datetime.fromisoformat(aside_at) + timedelta(days=DAYS)).date().isoformat()
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now().astimezone()
