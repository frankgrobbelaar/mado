"""History: what Mado did, a week of days at a time, newest first, with its undo (taking a new
picture away, putting a replaced original back: a picture's changes newest first) and clearing
it; and the quarantine, what waits there on each drive, and emptying one."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from mado import history
from mado.api.common import ApiModel, Database, SetAside
from mado.api.jobs import PictureRef
from mado.history import Entry, UndoError
from mado.previews import version
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
    kind: Literal["made", "replaced", "emptied"]
    name: str  # the original's file name; the drive, for a quarantine emptied
    made_for: str | None
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


class HistoryOut(ApiModel):
    entries: list[EntryOut]  # newest first
    older: str | None  # the day the next page starts before; None: that's all


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
    return HistoryOut(entries=[_out(conn, each) for each in found.entries], older=found.older)


@router.post("/history/{entry_id}/undo")
def undo(entry_id: int, conn: Database, quarantine: SetAside) -> EntryOut:
    """Takes a new picture away (into quarantine, put back from here), or puts a replaced
    original back (the made picture going into quarantine in its place)."""
    try:
        done = history.undo(conn, quarantine, entry_id, _now())
    except UndoError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    return _out(conn, done)


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
        or (found.kind == "replaced" and found.aside is not None and not gone)
    )
    can_redo = (
        found.kind != "emptied"
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
    )


def _picture(conn: sqlite3.Connection, found: Entry) -> PictureRef | None:
    """The picture to show beside a line: the one made, while it's in the library, else its
    original."""
    for path in (found.result, found.original):
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
