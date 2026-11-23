"""The library's folders, and the pictures in them, as the database keeps them.

A scan (mado/scan.py) fills this in: `find_pictures` walks a folder and records each picture with
its size and time, then `save_facts` keeps what reading it found (mado/pictures.py). Pictures
never change here: this only looks.
"""

import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

from mado.core.files import Kind, kind_of, skipped_folder
from mado.core.library import Covered, Holds, fits, inner_folder
from mado.pictures import Facts

_COMMIT_EVERY = 200  # pictures recorded between commits while walking a folder


class FolderError(Exception):
    """A folder that can't go in the library, with a sentence saying why."""


@dataclass(frozen=True)
class Folder:
    id: int
    path: Path
    added_at: str
    walked_at: str | None  # when a scan last looked all through it


@dataclass(frozen=True)
class Found:
    """What walking one folder found."""

    pictures: int
    added: int  # new to the library
    changed: tuple[int, ...]  # pictures whose file changed since, to read again
    gone: int  # no longer there
    problems: tuple[str, ...]  # folders inside that couldn't be opened


@dataclass(frozen=True)
class Unread:
    id: int
    path: Path
    kind: Kind


def folders(conn: sqlite3.Connection) -> list[Folder]:
    """The library's folders, in the order they were added."""
    rows = conn.execute("SELECT id, path, added_at, walked_at FROM folders ORDER BY id").fetchall()
    return [Folder(row["id"], Path(row["path"]), row["added_at"], row["walked_at"]) for row in rows]


def add_folder(conn: sqlite3.Connection, path: Path, *, now: datetime) -> Folder:
    """Adds a folder to the library. A folder that holds library folders takes them in, with
    their pictures."""
    path = Path(os.path.normpath(path.absolute()))
    if not path.is_dir():
        raise FolderError(
            f"{path} isn't there. Check its drive is connected and the folder exists."
        )
    existing = {PureWindowsPath(folder.path): folder for folder in folders(conn)}
    match fits(PureWindowsPath(path), existing):
        case Covered(by=by) if PureWindowsPath(path) == by:
            raise FolderError(f"{existing[by].path} is already in your library.")
        case Covered(by=by):
            raise FolderError(f"{path} is already in your library, as part of {existing[by].path}.")
        case Holds(folders=held):
            absorbed = [existing[inner].id for inner in held]
        case None:
            absorbed = []
    with conn:
        folder_id: int = conn.execute(
            "INSERT INTO folders (path, added_at) VALUES (?, ?) RETURNING id",
            (str(path), now.isoformat()),
        ).fetchone()[0]
        for inner in absorbed:
            moved = conn.execute("SELECT id, path FROM pictures WHERE folder_id = ?", (inner,))
            conn.executemany(
                "UPDATE pictures SET folder_id = ?, dir = ? WHERE id = ?",
                [
                    (
                        folder_id,
                        inner_folder(PureWindowsPath(path), PureWindowsPath(row["path"])),
                        row["id"],
                    )
                    for row in moved.fetchall()
                ],
            )
            conn.execute("DELETE FROM folders WHERE id = ?", (inner,))
    return Folder(folder_id, path, now.isoformat(), None)


def remove_folder(conn: sqlite3.Connection, folder_id: int) -> list[int] | None:
    """Forgets a folder and what Mado knew of its pictures, and says which pictures those were
    (None: no such folder). The pictures themselves stay exactly where they are."""
    with conn:
        ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM pictures WHERE folder_id = ?", (folder_id,))
        ]
        removed = conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,)).rowcount
    return ids if removed else None


def find_pictures(
    conn: sqlite3.Connection,
    folder: Folder,
    *,
    stamp: str,
    on_file: Callable[[Path], None] = lambda _: None,
    stop: Callable[[], bool] = lambda: False,
) -> Found | None:
    """Walks a library folder and records every picture in it.

    `stamp` names the scan; pictures it doesn't see are marked gone, except inside folders it
    couldn't open. Returns None, having marked nothing gone, when the folder isn't there (its
    drive unplugged, say), when it leaves the library during the walk, or when `stop` asks to
    stop. Links and junctions aren't followed: they can go round in circles, or off to another
    drive.
    """
    if not folder.path.is_dir():
        return None
    root = PureWindowsPath(folder.path)
    pictures = added = 0
    changed: list[int] = []
    problems: list[str] = []
    unopened: list[PureWindowsPath] = []
    waiting = [folder.path]
    while waiting:
        current = waiting.pop()
        try:
            with os.scandir(current) as entries:
                listed = sorted(entries, key=lambda entry: entry.name.casefold())
        except OSError as error:
            problems.append(f"Mado couldn't look in {current}: {error.strerror or error}.")
            unopened.append(PureWindowsPath(current))
            continue
        inside = [Path(entry.path) for entry in listed if _walks_into(entry)]
        waiting.extend(reversed(inside))  # so folders come off the stack in name order too
        for entry in listed:
            kind = kind_of(entry.name)
            if kind is None or not entry.is_file(follow_symlinks=False):
                continue
            if stop():
                conn.commit()
                return None
            path = Path(entry.path)
            on_file(path)
            stat = entry.stat(follow_symlinks=False)
            place = inner_folder(root, PureWindowsPath(path))
            try:
                outcome, picture_id = _record(
                    conn, folder.id, path, place, kind, stat.st_size, stat.st_mtime_ns, stamp
                )
            except sqlite3.IntegrityError:  # the folder left the library during the walk
                conn.rollback()
                return None
            pictures += 1
            added += outcome == "added"
            if outcome == "changed":
                changed.append(picture_id)
            if pictures % _COMMIT_EVERY == 0:
                conn.commit()
        conn.commit()  # after each folder, so the database is never held up for long
    unseen = conn.execute(
        "SELECT id, path FROM pictures WHERE folder_id = ? AND gone_at IS NULL AND seen_at <> ?",
        (folder.id, stamp),
    ).fetchall()
    gone = [
        row["id"]
        for row in unseen
        if not any(PureWindowsPath(row["path"]).is_relative_to(away) for away in unopened)
    ]
    with conn:
        conn.executemany("UPDATE pictures SET gone_at = ? WHERE id = ?", [(stamp, i) for i in gone])
        conn.execute("UPDATE folders SET walked_at = ? WHERE id = ?", (stamp, folder.id))
    return Found(pictures, added, tuple(changed), len(gone), tuple(problems))


def unread(conn: sqlite3.Connection) -> list[Unread]:
    """Pictures still to read, the newest file first: the days the owner looks at first fill in
    first."""
    rows = conn.execute(
        """SELECT id, path, name FROM pictures
           WHERE read_at IS NULL AND gone_at IS NULL ORDER BY modified DESC, id"""
    ).fetchall()
    return [Unread(row["id"], Path(row["path"]), kind_of(row["name"]) or "picture") for row in rows]


def save_facts(conn: sqlite3.Connection, picture_id: int, found: Facts, *, now: datetime) -> None:
    """Keeps what reading a picture found. When the camera's clock says when it was taken, that
    wins over the file's time."""
    taken = found.taken.isoformat(timespec="seconds") if found.taken else None
    with conn:
        conn.execute(
            """UPDATE pictures
               SET read_at = ?, problem = NULL, damaged = 0, format = ?, width = ?, height = ?,
                   taken_at = COALESCE(?, taken_at),
                   taken_from = CASE WHEN ? IS NULL THEN taken_from ELSE 'camera' END,
                   camera = ?, orientation = ?, located = ?
               WHERE id = ?""",
            (
                now.isoformat(),
                found.format,
                found.width,
                found.height,
                taken,
                taken,
                found.camera,
                found.orientation,
                int(found.located),
                picture_id,
            ),
        )


def save_problem(conn: sqlite3.Connection, picture_id: int, problem: str, *, now: datetime) -> None:
    """Keeps why a picture won't open. It's listed as it is, and read again once it changes."""
    row = conn.execute("SELECT name FROM pictures WHERE id = ?", (picture_id,)).fetchone()
    if row is None:
        return  # its folder left the library meanwhile
    extension = PureWindowsPath(row["name"]).suffix[1:].upper() or None
    with conn:
        conn.execute(
            """UPDATE pictures SET read_at = ?, problem = ?, format = COALESCE(format, ?)
               WHERE id = ?""",
            (now.isoformat(), problem, extension, picture_id),
        )


def file_time(modified: int) -> str:
    """A file's time (nanoseconds since 1970) in local time, to the second, as
    "2026-11-12T18:42:07"."""
    try:
        moment = datetime.fromtimestamp(modified / 1e9)
    except OverflowError, OSError, ValueError:  # a time Windows can't put in local time
        moment = datetime(1970, 1, 1)
    return moment.isoformat(timespec="seconds")


def _walks_into(entry: os.DirEntry[str]) -> bool:
    """A folder the walk goes into: a real folder, not a link or junction, nor one it skips."""
    return (
        entry.is_dir(follow_symlinks=False)
        and not entry.is_symlink()
        and not entry.is_junction()
        and not skipped_folder(entry.name)
    )


def _record(
    conn: sqlite3.Connection,
    folder_id: int,
    path: Path,
    place: str,
    kind: Kind,
    size: int,
    modified: int,
    stamp: str,
) -> tuple[str, int]:
    """Saves one found picture. Returns "added", "changed" or "same", and its number. A picture
    found gone before and here again counts as found now (`found_at`): it's new to the library
    once more. A camera RAW file has nothing to read yet, so it's read as it's found."""
    raw = kind == "raw"
    format_ = path.suffix[1:].upper() if raw else None
    read = stamp if raw else None
    taken = file_time(modified)
    before = conn.execute(
        "SELECT id, size, modified, gone_at FROM pictures WHERE path = ?", (str(path),)
    ).fetchone()
    if before is None:
        picture_id: int = conn.execute(
            """INSERT INTO pictures (folder_id, path, dir, name, size, modified, found_at, seen_at,
                                     read_at, raw, format, taken_at, taken_from)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'file') RETURNING id""",
            (
                folder_id,
                str(path),
                place,
                path.name,
                size,
                modified,
                stamp,
                stamp,
                read,
                int(raw),
                format_,
                taken,
            ),
        ).fetchone()[0]
        return "added", picture_id
    back = stamp if before["gone_at"] is not None else None
    if (before["size"], before["modified"]) == (size, modified):
        conn.execute(
            """UPDATE pictures SET folder_id = ?, dir = ?, name = ?, seen_at = ?, gone_at = NULL,
                                   found_at = COALESCE(?, found_at)
               WHERE id = ?""",
            (folder_id, place, path.name, stamp, back, before["id"]),
        )
        return ("added" if back else "same"), before["id"]
    conn.execute(
        """UPDATE pictures
           SET folder_id = ?, dir = ?, name = ?, size = ?, modified = ?, seen_at = ?,
               gone_at = NULL, found_at = COALESCE(?, found_at), read_at = ?, problem = NULL,
               damaged = 0, raw = ?, format = ?, width = NULL, height = NULL, taken_at = ?,
               taken_from = 'file', camera = NULL, orientation = NULL, located = 0
           WHERE id = ?""",
        (
            folder_id,
            place,
            path.name,
            size,
            modified,
            stamp,
            back,
            read,
            int(raw),
            format_,
            taken,
            before["id"],
        ),
    )
    return ("added" if back else "changed"), before["id"]
