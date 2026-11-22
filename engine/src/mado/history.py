"""History: what Mado did, newest first, a week of days at a time, and its undo.

Each picture made is a line: a new picture beside its original, which History can take away
(into quarantine, and put back from there till the clear-out), or an original replaced, which
History puts back (the made picture going into quarantine in its place). Emptying a drive's
quarantine by hand is a line too; that can't be undone. Clearing History forgets lines, never
pictures: a line whose picture still waits in quarantine stays, so it can be put back.
"""

import sqlite3
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import Literal

from mado.quarantine import MoveError, Quarantine

type Kind = Literal["made", "replaced", "emptied"]

DAYS_A_PAGE = 7
# Held while a picture's line is written and its pictures move (mado/making.py), and while a
# line is undone or done again, so an undo never comes between a line and its moves.
MOVES = threading.RLock()


@dataclass(frozen=True)
class Entry:
    id: int
    at: str  # local time, with its offset
    kind: Kind
    name: str  # the original's file name; the drive, for a quarantine emptied
    made_for: str | None  # what its size made it for: "TV 8K"; None without a size
    original: str | None
    result: str | None
    aside: str | None  # what waits in quarantine for it now
    aside_at: str | None
    cleared_at: str | None
    cleared_by: Literal["days", "owner"] | None  # the clear-out after its days, or the owner
    undone_at: str | None
    bytes: int | None
    look: str | None = None  # what it was made with: "Warm film at 60%"
    batch_id: int | None = None  # the batch it was made in, when it was


@dataclass(frozen=True)
class Page:
    entries: list[Entry]  # newest first
    older: str | None  # the day the next page starts before ("2026-11-15"); None: that's all


class UndoError(Exception):
    """A line History can't undo now, with a sentence saying why."""


def made(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    job_id: int | None,
    name: str,
    made_for: str | None,
    original: Path,
    result: Path,
    look: str | None = None,
) -> int:
    """A new picture made beside (or away from) its original."""
    return _insert(conn, now, "made", job_id, name, (made_for, look), original, result, None)


def replaced(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    job_id: int | None,
    name: str,
    made_for: str | None,
    original: Path,
    result: Path,
    aside: Path,
    look: str | None = None,
) -> int:
    """An original replaced by a picture made from it, the original set aside."""
    return _insert(conn, now, "replaced", job_id, name, (made_for, look), original, result, aside)


def forget(conn: sqlite3.Connection, entry_id: int) -> None:
    """Forgets a line whose change didn't happen after all."""
    with conn:
        conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))


def renamed(conn: sqlite3.Connection, entry_id: int, result: Path) -> None:
    """The picture a line made going to another name: the one it was to have was taken."""
    with conn:
        conn.execute("UPDATE history SET result = ? WHERE id = ?", (str(result), entry_id))


def for_job(conn: sqlite3.Connection, job_id: int) -> Entry | None:
    """The line a job wrote, if it got that far."""
    row = conn.execute(
        "SELECT * FROM history WHERE job_id = ? ORDER BY id DESC LIMIT 1", (job_id,)
    ).fetchone()
    return _entry(row) if row is not None else None


def entry(conn: sqlite3.Connection, entry_id: int) -> Entry | None:
    row = conn.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
    return _entry(row) if row is not None else None


def page(
    conn: sqlite3.Connection, *, before: str | None = None, query: str = "", days: int = DAYS_A_PAGE
) -> Page:
    """The lines on the `days` latest days with any, before the day `before` ("2026-11-22";
    None: from today). With a `query`, only lines naming a picture or folder with every word."""
    words = query.casefold().split()
    rows = [
        _entry(row)
        for row in conn.execute(
            "SELECT h.*, j.batch_id FROM history AS h LEFT JOIN jobs AS j ON j.id = h.job_id"
            " WHERE (?1 IS NULL OR substr(h.at, 1, 10) < ?1)"
            " ORDER BY h.at DESC, h.id DESC",
            (before,),
        )
    ]
    found = [each for each in rows if _names(each, words)]
    on = list(dict.fromkeys(each.at[:10] for each in found))
    shown = set(on[:days])
    return Page(
        entries=[each for each in found if each.at[:10] in shown],
        older=on[days - 1] if len(on) > days else None,
    )


def undo(conn: sqlite3.Connection, quarantine: Quarantine, entry_id: int, now: datetime) -> Entry:
    """Takes a new picture away (into quarantine), or puts a replaced original back (the made
    picture going into quarantine in its place). Raises UndoError."""
    with MOVES:
        return _undo(conn, quarantine, entry_id, now)


def _undo(conn: sqlite3.Connection, quarantine: Quarantine, entry_id: int, now: datetime) -> Entry:
    found = entry(conn, entry_id)
    if found is None:
        raise UndoError("History has no such line any more.")
    if found.undone_at is not None:
        raise UndoError("That's undone already.")
    if found.kind != "emptied":
        _first_newer(conn, found, found.result)
    stamp = now.isoformat(timespec="seconds")
    match found.kind:
        case "made":
            result = Path(found.result or "")
            try:
                aside = quarantine.set_aside(result, now)
            except MoveError as error:
                raise UndoError(str(error)) from None
            _update(conn, entry_id, aside=str(aside), aside_at=stamp, undone_at=stamp)
        case "replaced":
            if found.cleared_at is not None:
                raise UndoError(_gone(found))
            if not found.aside:
                raise UndoError(_NOTHING_ASIDE)
            _put_original_back(conn, quarantine, found, now)
        case "emptied":
            raise UndoError("What was emptied out of quarantine is gone for good.")
    return entry(conn, entry_id) or found


def redo(conn: sqlite3.Connection, quarantine: Quarantine, entry_id: int, now: datetime) -> Entry:
    """Undoes an undo: puts a new picture that was taken away back where it was, or replaces
    an original put back again (the original going into quarantine once more). Raises
    UndoError."""
    with MOVES:
        return _redo(conn, quarantine, entry_id, now)


def _redo(conn: sqlite3.Connection, quarantine: Quarantine, entry_id: int, now: datetime) -> Entry:
    found = entry(conn, entry_id)
    if found is None:
        raise UndoError("History has no such line any more.")
    if (
        found.kind == "emptied"
        or found.undone_at is None
        or not found.aside
        or not found.result
        or not found.original
    ):
        raise UndoError("There's nothing to put back for that line.")
    if found.cleared_at is not None:
        raise UndoError(_gone(found))
    if found.kind == "made":
        try:
            quarantine.put_back(Path(found.aside), Path(found.result))
        except MoveError as error:
            raise UndoError(str(error)) from None
        _update(conn, entry_id, aside=None, aside_at=None, undone_at=None)
        return entry(conn, entry_id) or found
    _first_newer(conn, found, found.original)
    _swapped(conn, quarantine, found, Path(found.original), Path(found.result), None, now)
    return entry(conn, entry_id) or found


def of_batch(conn: sqlite3.Connection, batch_id: int, limit: int = -1) -> list[Entry]:
    """A batch's lines, newest first; the newest `limit` of them, when it's given."""
    return [
        _entry(row)
        for row in conn.execute(
            """SELECT h.*, j.batch_id FROM history AS h JOIN jobs AS j ON j.id = h.job_id
               WHERE j.batch_id = ? ORDER BY h.id DESC LIMIT ?""",
            (batch_id, limit),
        )
    ]


def undo_batch(
    conn: sqlite3.Connection, quarantine: Quarantine, batch_id: int, now: datetime
) -> tuple[int, list[str]]:
    """Undoes every line of a batch that can be, newest first: its new pictures taken away, or
    its originals put back. Says how many were, and why any couldn't be."""
    done, problems = 0, list[str]()
    for line in of_batch(conn, batch_id):
        if line.undone_at is not None or not _can_undo(line):
            continue
        try:
            undo(conn, quarantine, line.id, now)
        except UndoError as error:
            problems.append(f"{line.name}: {error}")
            continue
        done += 1
    return done, problems


def redo_batch(
    conn: sqlite3.Connection, quarantine: Quarantine, batch_id: int, now: datetime
) -> tuple[int, list[str]]:
    """Undoes a batch's undo, oldest first: its new pictures put back, or its originals replaced
    again. Says how many were, and why any couldn't be."""
    done, problems = 0, list[str]()
    for line in reversed(of_batch(conn, batch_id)):
        if line.undone_at is None or not line.aside or line.cleared_at is not None:
            continue
        try:
            redo(conn, quarantine, line.id, now)
        except UndoError as error:
            problems.append(f"{line.name}: {error}")
            continue
        done += 1
    return done, problems


def _can_undo(line: Entry) -> bool:
    if line.kind == "made":
        return line.result is not None
    return line.kind == "replaced" and line.aside is not None and line.cleared_at is None


def clear(conn: sqlite3.Connection, *, keep: timedelta | None, now: datetime) -> int:
    """Forgets the lines older than `keep` (None: all of them), except those whose picture still
    waits in quarantine, so it can be put back. Pictures never change. Returns how many went."""
    rows = conn.execute(
        "SELECT id, at FROM history WHERE aside IS NULL OR cleared_at IS NOT NULL"
    ).fetchall()
    cutoff = now - keep if keep is not None else None
    gone = [row["id"] for row in rows if cutoff is None or _before(row["at"], cutoff)]
    with conn:
        conn.executemany("DELETE FROM history WHERE id = ?", [(each,) for each in gone])
    return len(gone)


def _put_original_back(
    conn: sqlite3.Connection, quarantine: Quarantine, found: Entry, now: datetime
) -> None:
    original, result = Path(found.original or ""), Path(found.result or "")
    stamp = now.isoformat(timespec="seconds")
    _swapped(conn, quarantine, found, result, original, stamp, now)


def _swapped(
    conn: sqlite3.Connection,
    quarantine: Quarantine,
    found: Entry,
    there: Path,
    back_to: Path,
    undone_at: str | None,
    now: datetime,
) -> None:
    """A replaced line's two pictures swapped: the one at `there` into quarantine (when it's
    still there), the one waiting there for the line back at `back_to`."""
    set_aside: Path | None = None
    try:
        if there.exists():
            set_aside = quarantine.set_aside(there, now)
        quarantine.put_back(Path(found.aside or ""), back_to)
    except MoveError as error:
        if set_aside is not None:  # the picture set aside goes back where it was
            with suppress(MoveError):  # else it waits in quarantine, the line as it was
                quarantine.put_back(set_aside, there)
        raise UndoError(str(error)) from None
    stamp = now.isoformat(timespec="seconds")
    _update(
        conn,
        found.id,
        aside=str(set_aside) if set_aside else None,
        aside_at=stamp if set_aside else None,
        undone_at=undone_at,
    )


def _first_newer(conn: sqlite3.Connection, found: Entry, moving: str | None) -> None:
    """Raises UndoError when a newer line, not undone, replaced the picture at `moving`, which
    undoing (or redoing) `found` would move: that one is undone first."""
    if not moving:
        return
    key = moving.casefold()
    for row in conn.execute(
        "SELECT name, original FROM history"
        " WHERE id > ? AND kind = 'replaced' AND undone_at IS NULL ORDER BY id",
        (found.id,),
    ):
        if row["original"] and str(row["original"]).casefold() == key:
            raise UndoError(
                f"{row['name']} was replaced again since. Put that back first: History "
                "undoes a picture's changes newest first."
            )


_NOTHING_ASIDE = "Mado has nothing set aside for it any more, so it can't be put back."


def _gone(found: Entry) -> str:
    when = (found.cleared_at or "")[:10]
    on = f" on {when}" if when else ""
    if found.cleared_by == "owner":
        return f"You emptied it out of quarantine{on}, so it can't be put back."
    return f"It was cleared out of quarantine{on}, after its days were up, so it can't be put back."


def _insert(
    conn: sqlite3.Connection,
    now: datetime,
    kind: Kind,
    job_id: int | None,
    name: str,
    made: tuple[str | None, str | None],  # what its size made it for, and what look it has
    original: Path,
    result: Path,
    aside: Path | None,
) -> int:
    stamp = now.isoformat(timespec="seconds")
    with conn:
        row = conn.execute(
            """INSERT INTO history (at, kind, job_id, name, made_for, look, original, result,
                                    aside, aside_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                stamp,
                kind,
                job_id,
                name,
                made[0],
                made[1],
                str(original),
                str(result),
                str(aside) if aside else None,
                stamp if aside else None,
            ),
        ).fetchone()
    entry_id: int = row["id"]
    return entry_id


def _update(
    conn: sqlite3.Connection,
    entry_id: int,
    *,
    aside: str | None,
    aside_at: str | None,
    undone_at: str | None,
) -> None:
    with conn:
        conn.execute(
            "UPDATE history SET aside = ?, aside_at = ?, cleared_at = NULL, cleared_by = NULL,"
            " undone_at = ?"
            " WHERE id = ?",
            (aside, aside_at, undone_at, entry_id),
        )


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        at=row["at"],
        kind=row["kind"],
        name=row["name"],
        made_for=row["made_for"],
        original=row["original"],
        result=row["result"],
        aside=row["aside"],
        aside_at=row["aside_at"],
        cleared_at=row["cleared_at"],
        cleared_by=row["cleared_by"],
        undone_at=row["undone_at"],
        bytes=row["bytes"],
        look=row["look"],
        batch_id=row["batch_id"] if "batch_id" in row.keys() else None,  # noqa: SIM118 - a Row's
    )


def _names(found: Entry, words: list[str]) -> bool:
    """Whether a line names every word: its picture, what it was made for or with, or a
    folder."""
    if not words:
        return True
    text = " ".join(
        part
        for part in (
            found.name,
            found.made_for,
            found.look,
            found.original,
            PureWindowsPath(found.result).name if found.result else None,
        )
        if part
    ).casefold()
    return all(word in text for word in words)


def _before(stamp: str, cutoff: datetime) -> bool:
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return (moment if moment.tzinfo else moment.astimezone()) < cutoff
