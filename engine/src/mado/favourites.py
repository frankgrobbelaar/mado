"""Favourites: pictures the owner gave a heart, in the library or from outside it.

- A favourite is kept by its picture's number. A picture changed in place (replaced by a Save, or
  edited in another app) keeps its number, so it stays one. One moved or renamed in File Explorer
  is found gone by a scan and found again where it went, under a new number: `follow` gives the
  heart to it, by its size and file time, which Windows keeps through a move or a rename, as
  History follows a picture's family by its paths.
- One whose picture went and stayed gone is forgotten after 30 days, the month a picture waits in
  Mado's quarantine before it's deleted for good (`forget_gone`); a picture back within them (put
  back from quarantine, its drive plugged in) is a favourite still. Its folder taken out of the
  library forgets it at once, with its pictures.
- One from outside the library is never forgotten while it's a favourite (mado/outside.py).
"""

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import PureWindowsPath

DAYS = 30  # a favourite whose picture stays gone this long is forgotten


def set_favourite(
    conn: sqlite3.Connection, picture_id: int, favourite: bool, now: datetime
) -> bool:
    """Gives a picture its heart, or takes it back. False when there's no such picture."""
    there = conn.execute("SELECT 1 FROM pictures WHERE id = ?", (picture_id,)).fetchone()
    if there is None:
        return False
    with conn:
        if favourite:
            conn.execute(
                "INSERT OR IGNORE INTO favourites (picture_id, at) VALUES (?, ?)",
                (picture_id, now.isoformat(timespec="seconds")),
            )
        else:
            conn.execute("DELETE FROM favourites WHERE picture_id = ?", (picture_id,))
    return True


def is_favourite(conn: sqlite3.Connection, picture_id: int) -> bool:
    row = conn.execute("SELECT 1 FROM favourites WHERE picture_id = ?", (picture_id,)).fetchone()
    return row is not None


def among(conn: sqlite3.Connection, picture_ids: Iterable[int]) -> set[int]:
    """Which of these pictures are favourites."""
    wanted = list(dict.fromkeys(picture_ids))
    found: set[int] = set()
    for start in range(0, len(wanted), 500):  # SQLite's limit on values in one statement
        chunk = wanted[start : start + 500]
        marks = ", ".join("?" for _ in chunk)
        found |= {
            row[0]
            for row in conn.execute(
                f"SELECT picture_id FROM favourites WHERE picture_id IN ({marks})",  # noqa: S608 - ?s
                chunk,
            )
        }
    return found


def count(conn: sqlite3.Connection) -> int:
    """The favourites whose pictures are there now (as far as Mado knows) and read."""
    found: int = conn.execute(
        """SELECT COUNT(*) FROM favourites AS f JOIN pictures AS p ON p.id = f.picture_id
           WHERE p.gone_at IS NULL AND p.read_at IS NOT NULL"""
    ).fetchone()[0]
    return found


def follow(conn: sqlite3.Connection) -> int:
    """Favourites whose picture a scan found gone follow it to where it went: a picture the same
    scan found new (a move or a rename is one gone and one found at once), with the same size and
    file time, not a favourite already; one of the same name first (it moved), then one in the
    same folder (it was renamed). Two pictures written in the same instant can share a size and a
    time, so one that was there before never counts. Says how many followed."""
    gone = conn.execute(
        """SELECT f.picture_id, p.name, p.path, p.size, p.modified, p.gone_at
           FROM favourites AS f JOIN pictures AS p ON p.id = f.picture_id
           WHERE p.gone_at IS NOT NULL"""
    ).fetchall()
    followed = 0
    for row in gone:
        found = conn.execute(
            """SELECT id, name, path FROM pictures
               WHERE gone_at IS NULL AND size = ? AND modified = ? AND found_at = ?
                 AND id NOT IN (SELECT picture_id FROM favourites)""",
            (row["size"], row["modified"], row["gone_at"]),
        ).fetchall()
        if not found:
            continue
        name = str(row["name"]).casefold()
        folder = str(PureWindowsPath(row["path"]).parent).casefold()
        best = min(
            found,
            key=lambda each: (
                str(each["name"]).casefold() != name,
                str(PureWindowsPath(each["path"]).parent).casefold() != folder,
                each["id"],
            ),
        )
        with conn:
            conn.execute(
                "UPDATE favourites SET picture_id = ? WHERE picture_id = ?",
                (best["id"], row["picture_id"]),
            )
        followed += 1
    return followed


def forget_gone(conn: sqlite3.Connection, *, now: datetime, days: int = DAYS) -> int:
    """Forgets the favourites whose pictures went `days` ago or more and haven't come back.
    Says how many."""
    cutoff = now - timedelta(days=days)
    rows = conn.execute(
        """SELECT f.picture_id, p.gone_at FROM favourites AS f
           JOIN pictures AS p ON p.id = f.picture_id WHERE p.gone_at IS NOT NULL"""
    ).fetchall()
    going = [(row["picture_id"],) for row in rows if _before(row["gone_at"], cutoff)]
    with conn:
        conn.executemany("DELETE FROM favourites WHERE picture_id = ?", going)
    return len(going)


def _before(stamp: object, cutoff: datetime) -> bool:
    try:
        moment = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    return (moment if moment.tzinfo else moment.astimezone()) <= cutoff
