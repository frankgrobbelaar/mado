"""Pictures from anywhere: a picture opened from outside the library (dropped, picked, pasted,
opened from File Explorer, Open with or the command line), known by its path.

- One in a library folder is simply the library's picture: the library's record of it, or one
  made now as a scan would.
- Any other is a picture outside the library: never listed in the Library, never counted, never
  looked at for duplicates. Its folder added to the library later, the scan makes it the
  library's, keeping its number, so its jobs stay its own (History goes by its path).
- One not opened for a month is forgotten, with its copies in the cache, unless the queue or
  History still needs it; a pasted one (mado/pasting.py) is deleted then too, as it's Mado's own
  file, in its data folder.
"""

import logging
import os
import re
import sqlite3
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath

from mado.config import DataPaths
from mado.core.files import kind_of
from mado.core.library import holding, inner_folder
from mado.core.opening import Found, long_form, not_a_picture, not_there
from mado.library import folders, record, save_facts, save_problem
from mado.pictures import InUseError, PictureGoneError, UnreadableError, read_facts

log = logging.getLogger(__name__)

# Forgotten after this long unopened: the month the quarantine and the edits' masks keep too, so
# a picture opened again from History or Made today within it finds its copies as they were.
DAYS = 30
_LONG = 248  # a path this long may need Windows' long form, \\?\, to be reached


class OpenError(Exception):
    """A picture that can't be opened, with a sentence saying why, and the answer it makes."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def reachable(given: str) -> Path:
    """A path as given (quotes and spaces round it gone, `..` worked out), or in Windows' long
    form when only that reaches it: a path longer than 260 letters, on a PC where long paths
    aren't turned on."""
    path = Path(os.path.normpath(given.strip().strip('"')))
    if len(str(path)) < _LONG or path.exists():
        return path
    long = Path(long_form(str(path)))
    return long if long.exists() else path


def found(path: Path) -> Found:
    """What a path is: a folder, a picture by its name, another file, or not there."""
    if path.is_dir():
        return "folder"
    if path.is_file():
        return "picture" if kind_of(path.name) is not None else "other"
    return "missing"


def drive_there(path: Path) -> bool:
    """Whether a path's drive (or network share) is there, connected."""
    anchor = PureWindowsPath(path).anchor
    return not anchor or Path(anchor).exists()


def why_not(path: Path) -> str:
    """Why a path didn't open: not a picture Mado reads, or not there."""
    if path.exists():
        return not_a_picture(path.name)
    return not_there(str(path), drive_there(path))


def open_picture(
    conn: sqlite3.Connection,
    path: Path,
    *,
    now: datetime,
    forget: Callable[[list[int]], None] = lambda _ids: None,
    data: DataPaths | None = None,
) -> int:
    """The picture at `path`, as Mado knows it, by its number: the library's when it's in a
    library folder, else one outside the library, read now (or again, when its file changed:
    `forget` lets the copies of what it was go). In Mado's own folder (`data`), only a paste is
    opened, and it's always a paste, never the library's. Raises OpenError."""
    kind = kind_of(path.name)
    if kind is None or not path.is_file():
        raise OpenError(why_not(path), 404 if not path.exists() else 422)
    paste = data is not None and _inside(path, data.pasted)
    if data is not None and not paste and _inside(path, data.root):
        raise OpenError(
            f"{path.name} is one of Mado's own files, kept in its data folder, not a picture of "
            "yours, so Mado doesn't open it.",
            422,
        )
    stat = path.stat()
    stamp = now.isoformat()
    known = conn.execute(
        "SELECT id, folder_id FROM pictures WHERE path = ? AND gone_at IS NULL", (str(path),)
    ).fetchone()
    if known is not None and known["folder_id"] is not None and not paste:
        return int(known["id"])
    library = {PureWindowsPath(folder.path): folder for folder in folders(conn)}
    root = None if paste else holding(PureWindowsPath(path), library)
    folder_id = library[root].id if root is not None else None
    place = inner_folder(root, PureWindowsPath(path)) if root is not None else ""
    with conn:
        outcome, picture_id = record(
            conn, folder_id, path, place, kind, stat.st_size, stat.st_mtime_ns, stamp
        )
        if folder_id is None:
            conn.execute(
                "UPDATE pictures SET opened_at = ?, pasted = MAX(pasted, ?) WHERE id = ?",
                (stamp, int(paste), picture_id),
            )
    if outcome == "changed":
        forget([picture_id])
    unread = conn.execute(
        "SELECT read_at IS NULL FROM pictures WHERE id = ?", (picture_id,)
    ).fetchone()[0]
    if unread:
        _read(conn, picture_id, path, now)
    return picture_id


def opened(conn: sqlite3.Connection, picture_id: int, now: datetime) -> None:
    """A picture outside the library was opened again: the month before it's forgotten starts
    afresh."""
    with conn:
        conn.execute(
            "UPDATE pictures SET opened_at = ? WHERE id = ? AND folder_id IS NULL",
            (now.isoformat(), picture_id),
        )


def forget(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    pasted: Path,
    copies: Callable[[list[int]], None],
    days: int = DAYS,
) -> int:
    """Forgets the pictures outside the library not opened for `days`, unless the queue or
    History still needs them, with their copies; a pasted one's file goes too, as it's Mado's
    own, in `pasted`. Returns how many went."""
    cutoff = now - timedelta(days=days)
    _clear_orphans(conn, pasted, cutoff)
    rows = conn.execute(
        "SELECT id, path, pasted, opened_at FROM pictures WHERE folder_id IS NULL"
    ).fetchall()
    going = [
        row
        for row in rows
        if _before(row["opened_at"], cutoff) and not _needed(conn, row["id"], row["path"], cutoff)
    ]
    if not going:
        return 0
    with conn:
        conn.executemany("DELETE FROM pictures WHERE id = ?", [(row["id"],) for row in going])
    copies([row["id"] for row in going])
    _delete_pasted(
        (Path(row["path"]) for row in going if row["pasted"]),
        pasted,
    )
    log.info("Forgot %d pictures from outside the library not opened for %d days", len(going), days)
    return len(going)


def _read(conn: sqlite3.Connection, picture_id: int, path: Path, now: datetime) -> None:
    """Reads a picture's facts now; one that won't open is kept with why, as the library keeps
    one. Raises OpenError for one open in another app, or gone as it was read."""
    kind = kind_of(path.name) or "picture"
    try:
        save_facts(conn, picture_id, read_facts(path, kind), now=now)
    except InUseError as error:
        raise OpenError(str(error), 409) from None
    except PictureGoneError:
        raise OpenError(not_there(str(path), drive_there(path)), 404) from None
    except UnreadableError as error:
        save_problem(conn, picture_id, str(error), now=now)


def _needed(conn: sqlite3.Connection, picture_id: int, path: str, cutoff: datetime) -> bool:
    """Whether the queue or History still needs a picture: a job waiting to make it, or a line
    of History naming it that's recent, or with something of it still in quarantine."""
    waiting = conn.execute(
        """SELECT 1 FROM jobs WHERE state IN ('queued', 'running')
             AND (picture_id = ? OR source = ? COLLATE NOCASE) LIMIT 1""",
        (picture_id, path),
    ).fetchone()
    if waiting is not None:
        return True
    lines = conn.execute(
        """SELECT at, aside FROM history WHERE cleared_at IS NULL
             AND (original = ? COLLATE NOCASE OR result = ? COLLATE NOCASE)""",
        (path, path),
    ).fetchall()
    return any(line["aside"] or not _before(line["at"], cutoff) for line in lines)


def _clear_orphans(conn: sqlite3.Connection, pasted: Path, cutoff: datetime) -> None:
    """Deletes pastes with no record (a stop between writing one and keeping its record, or
    records restored from before it) once their month is up: only Mado's own, named as it names
    them."""
    try:
        files = [each for each in pasted.iterdir() if _PASTED.fullmatch(each.name)]
    except OSError:
        return  # nothing pasted yet
    known = {
        str(row["path"]).casefold()
        for row in conn.execute("SELECT path FROM pictures WHERE pasted = 1")
    }
    old: list[Path] = []
    for each in files:
        try:
            written = datetime.fromtimestamp(each.stat().st_mtime).astimezone()
        except OSError:
            continue
        if str(each).casefold() not in known and written < cutoff:
            old.append(each)
    _delete_pasted(old, pasted)


# How Mado names a paste (mado/core/opening.py, pasted_name).
_PASTED = re.compile(r"Pasted \d{4}-\d\d-\d\d \d\d\.\d\d( \(\d+\))?\.png", re.IGNORECASE)


def _delete_pasted(files: Iterable[Path], pasted: Path) -> None:
    """Deletes pasted pictures, only ever a file in Mado's own folder for them."""
    for file in files:
        if str(file.parent).casefold() != str(pasted).casefold():
            log.warning("Mado didn't delete %s: it isn't one of its pasted pictures", file)
            continue
        try:
            file.unlink(missing_ok=True)
        except OSError as error:
            log.warning("Mado couldn't delete the pasted picture %s: %s", file, error)


def _inside(path: Path, folder: Path) -> bool:
    """Whether a path is in a folder, or inside one in it, however either is written."""
    return PureWindowsPath(os.path.normpath(path)).is_relative_to(
        PureWindowsPath(os.path.normpath(folder))
    )


def _before(stamp: str | None, cutoff: datetime) -> bool:
    if not stamp:
        return False
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return (moment if moment.tzinfo else moment.astimezone()) < cutoff
