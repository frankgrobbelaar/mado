"""The quarantine: where a picture set aside waits (an original a made picture replaced, or a
made picture taken away), on its own drive in "Mado quarantine", a folder a day, so setting one
aside is a rename, never a copy. History puts it back. After 30 days the daily clear-out
deletes it (mado/care.py), or all of a drive's at once when the owner empties it to make room.

Mado deletes only what's in one day's folder of a quarantine, whatever its records say: a
damaged record, or one an imported export held, never points it at a picture elsewhere.
"""

import errno
import logging
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Literal

from mado.core.naming import aside_name, in_quarantine, quarantine_root

log = logging.getLogger(__name__)

DAYS = 30  # how long a picture set aside waits before the clear-out
_IN_USE = (32, 33)  # Windows' sharing and lock violations: another app has the file open
_PARTIAL = ".mado-partial"


class MoveError(Exception):
    """A picture Mado couldn't move, with a sentence saying why. Nothing was lost."""


class Quarantine:
    def __init__(self, root_of: Callable[[Path], Path] = quarantine_root) -> None:
        """`root_of` says where a picture's quarantine is: at the top of its own drive (tests
        and development keep it somewhere of their own)."""
        self._root_of = root_of

    def root(self, picture: Path) -> Path:
        return self._root_of(picture)

    def holds(self, path: Path) -> bool:
        """Whether `path` is a picture set aside, in one of its quarantine's day folders."""
        return in_quarantine(path, self.root(path))

    def place(self, picture: Path, now: datetime) -> Path:
        """Where setting a picture aside now would put it: today's folder of its drive's
        quarantine, under its own name or the next free one."""
        folder = self.root(picture) / now.date().isoformat()
        return folder / aside_name(picture.name, lambda name: (folder / name).exists())

    def set_aside(self, picture: Path, now: datetime, *, to: Path | None = None) -> Path:
        """Moves a picture into today's folder of its drive's quarantine (or to `to`, a place
        `place` gave) and says where it went. Raises MoveError."""
        target = to or self.place(picture, now)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise MoveError(
                f"Mado couldn't make its quarantine folder {target.parent}: "
                f"{error.strerror or error}."
            ) from error
        move(picture, target)
        return target

    def put_back(self, aside: Path, to: Path) -> None:
        """Moves a picture set aside back where it was. Raises MoveError, when something else
        is there now, for one."""
        if to.exists():
            raise MoveError(
                f"There's another {to.name} in its place now, so Mado left the one set aside "
                "where it is. Move that one, then try again."
            )
        move(aside, to)
        _tidy(aside.parent)


def move(source: Path, target: Path) -> None:
    """Moves a file, never over another: a rename on the same drive; to another drive, a copy
    beside its new place, checked, put in place, then the original removed. Raises MoveError."""
    if not source.exists():
        raise MoveError(f"{source.name} isn't where it was: it was moved or deleted since.")
    if target.exists():
        raise MoveError(f"There's already a {target.name} there, so Mado didn't move it.")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)  # fails, rather than replacing, when the name is taken
    except OSError as error:
        if error.errno == errno.EXDEV or getattr(error, "winerror", None) == 17:
            _copy_across(source, target)
            return
        raise MoveError(_could_not(source, error)) from error


def _copy_across(source: Path, target: Path) -> None:
    partial = target.with_name(target.name + _PARTIAL)
    try:
        shutil.copy2(source, partial)
        if partial.stat().st_size != source.stat().st_size:
            raise MoveError(f"The copy of {source.name} came out the wrong size; it stays put.")
        partial.rename(target)
        source.unlink()
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise MoveError(_could_not(source, error)) from error


def _could_not(source: Path, error: OSError) -> str:
    if getattr(error, "winerror", None) in _IN_USE:
        return (
            f"{source.name} is open in another app, so Mado can't move it. Close it there, then "
            "try again."
        )
    return f"Mado couldn't move {source.name}: {error.strerror or error}."


def _tidy(day: Path) -> None:
    """A day's folder, then the quarantine itself, once nothing's left in them."""
    with suppress(OSError):
        day.rmdir()
        day.parent.rmdir()


# What waits in quarantine, as History knows it.
_ASIDE = "SELECT id, aside, aside_at FROM history WHERE aside IS NOT NULL AND cleared_at IS NULL"


def clear_out(
    conn: sqlite3.Connection, quarantine: Quarantine, *, now: datetime, days: int = DAYS
) -> int:
    """Deletes what was set aside more than `days` ago. Returns how many pictures went."""
    cutoff = now - timedelta(days=days)
    old = [row for row in conn.execute(_ASIDE) if _before(row["aside_at"], cutoff)]
    cleared = _delete(conn, quarantine, old, now, "days")
    if cleared:
        log.info("Cleared %d pictures set aside more than %d days ago", cleared, days)
    return cleared


def empty(conn: sqlite3.Connection, quarantine: Quarantine, drive: str, *, now: datetime) -> int:
    """Deletes everything set aside on a drive ("D:") now, however recently: the owner asked, to
    make room there. History says so. Returns how many bytes went."""
    there = [
        row
        for row in conn.execute(_ASIDE)
        if PureWindowsPath(row["aside"]).drive.casefold() == drive.casefold()
    ]
    freed = sum(_size(Path(row["aside"])) for row in there)
    cleared = _delete(conn, quarantine, there, now, "owner")
    if cleared:
        with conn:
            conn.execute(
                "INSERT INTO history (at, kind, name, bytes) VALUES (?, 'emptied', ?, ?)",
                (now.isoformat(timespec="seconds"), drive.upper(), freed),
            )
        log.info("Emptied the quarantine on %s: %d pictures", drive, cleared)
    return freed if cleared else 0


def by_drive(conn: sqlite3.Connection) -> dict[str, int]:
    """What waits in quarantine on each drive ("D:"), in bytes."""
    found: dict[str, int] = {}
    for row in conn.execute(_ASIDE):
        size = _size(Path(row["aside"]))
        if size:
            drive = PureWindowsPath(row["aside"]).drive.upper() or "?"
            found[drive] = found.get(drive, 0) + size
    return found


def _delete(
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    rows: list[sqlite3.Row],
    now: datetime,
    by: Literal["days", "owner"],
) -> int:
    """Deletes what rows say waits in quarantine, `by` the clear-out's days or the owner, and
    notes it. What's on a drive that isn't connected waits for it."""
    cleared = 0
    emptied: set[Path] = set()
    for row in rows:
        aside = Path(row["aside"])
        if not quarantine.holds(aside):  # a damaged or imported record: never Mado's to delete
            log.warning("Mado didn't clear %s out: it isn't in a quarantine folder", aside)
            continue
        if not aside.exists() and not Path(aside.anchor).exists():
            continue  # its drive isn't connected: Windows says nothing's missing then
        try:
            aside.unlink(missing_ok=True)
        except OSError as error:
            log.warning("Mado couldn't clear %s out of quarantine: %s", aside, error)
            continue
        with conn:
            conn.execute(
                "UPDATE history SET cleared_at = ?, cleared_by = ? WHERE id = ?",
                (now.isoformat(timespec="seconds"), by, row["id"]),
            )
        cleared += 1
        emptied.add(aside.parent)
    for day in emptied:
        _tidy(day)
    return cleared


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:  # gone already, or its drive isn't connected
        return 0


def _before(stamp: str | None, cutoff: datetime) -> bool:
    if not stamp:
        return False
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return (moment if moment.tzinfo else moment.astimezone()) < cutoff
