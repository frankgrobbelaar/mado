"""The owner's own looks, kept in the database: a .cube file imported, or a mix kept from the Looks
tab (a look at its strength made into one table, with its finishing touches). Each is a table
packed small (mado/core/grids.py: a 65-point table in tens of kilobytes, where its .cube file is
7 MB of text), so the nightly backups and the export carry them without growing much.

Their names are the owner's: unique in any case, and never the name of one of Mado's looks. An
imported file is named after its title, or its file, with "(2)" when that's taken.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import numpy as np

from mado.core.cube import CubeError, read, too_big
from mado.core.grids import SIDE, Grid, blended, identity, packed, unpacked
from mado.core.looks import Look, built_in, mado_look, phrase
from mado.core.touches import NONE, Touches, named, words

YOURS = "yours-"  # an own look's id, after its row: "yours-3"
LONGEST = 60  # letters a name may have


@dataclass(frozen=True)
class Kept:
    id: str  # "yours-3"
    name: str
    kind: Literal["cube", "mix"]
    points: int  # the table's points a side
    touches: Touches  # a mix's; none for a .cube file
    source: str  # the .cube file's name, or the look mixed: "Warm film at 60%"
    added_at: str


class LookNameError(ValueError):
    """A name a look can't have, with a sentence saying why."""


def listed(conn: sqlite3.Connection) -> list[Kept]:
    """The owner's looks, oldest first."""
    rows = conn.execute("SELECT * FROM looks ORDER BY id").fetchall()
    return [_kept(row) for row in rows]


def found(conn: sqlite3.Connection, look_id: str) -> tuple[Kept, Look] | None:
    """One of the owner's looks and its table, by its id ("yours-3"); None when there's none."""
    number = _number(look_id)
    row = (
        conn.execute("SELECT * FROM looks WHERE id = ?", (number,)).fetchone()
        if number is not None
        else None
    )
    if row is None:
        return None
    kept = _kept(row)
    try:
        grid = unpacked(row["grid"], row["points"])
    except ValueError:  # a table damaged in the records: the look can't be used
        return None
    return kept, Look(kept.id, kept.name, grid)


def resolve(conn: sqlite3.Connection, look_id: str) -> Look | None:
    """A look by its id: one of Mado's ("warm-film") or the owner's ("yours-3")."""
    if look_id.startswith(YOURS):
        mine = found(conn, look_id)
        return mine[1] if mine else None
    return mado_look(look_id)


def imported(conn: sqlite3.Connection, path: Path, now: datetime) -> Kept:
    """A .cube file kept as a look, named after its title (or its file). Raises CubeError, with
    a sentence saying why it can't be."""
    try:
        size = path.stat().st_size
    except OSError:
        raise CubeError(
            f"Mado couldn't find {path.name} any more: it may have been moved, or its drive "
            "unplugged."
        ) from None
    problem = too_big(size)
    if problem:
        raise CubeError(problem)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CubeError(f"Mado couldn't read {path.name}: {error.strerror or error}.") from None
    cube = read(_text(data))
    name = _free_name(conn, (cube.title or path.stem).strip()[:LONGEST].strip() or "My look")
    return _added(conn, name, "cube", cube.grid, NONE, path.name, now)


def kept(
    conn: sqlite3.Connection,
    name: str,
    look: Look,
    strength: float,
    touches: Touches,
    now: datetime,
) -> Kept:
    """The mix on the Looks tab kept as a look: its look at its strength made into one table (the
    original's own colours, when it had none), and its touches. Raises LookNameError."""
    name = _checked(conn, name)
    grid = blended(look.grid, strength) if look.grid is not None else identity(SIDE)
    return _added(conn, name, "mix", grid, touches, _mixed(look, strength, touches), now)


def _mixed(look: Look, strength: float, touches: Touches) -> str:
    """What a mix is made of: "Warm film at 60%, grain 20, vignette 35", "Dust 40"."""
    parts = [phrase(look, strength, NONE)] if look.grid is not None and strength > 0 else []
    if touches.on():
        parts.append(words(touches))
    said = ", ".join(parts) or "The original"
    return said[0].upper() + said[1:]


def renamed(conn: sqlite3.Connection, look_id: str, name: str) -> Kept | None:
    """One of the owner's looks under a new name; None when there's no such look. Raises
    LookNameError."""
    number = _number(look_id)
    if (
        number is None
        or conn.execute("SELECT 1 FROM looks WHERE id = ?", (number,)).fetchone() is None
    ):
        return None
    name = _checked(conn, name, but=number)
    try:
        with conn:
            conn.execute("UPDATE looks SET name = ? WHERE id = ?", (name, number))
    except sqlite3.IntegrityError:  # kept under that name a moment ago
        raise LookNameError(_taken(name)) from None
    row = conn.execute("SELECT * FROM looks WHERE id = ?", (number,)).fetchone()
    return _kept(row)


def deleted(conn: sqlite3.Connection, look_id: str) -> bool:
    """Deletes one of the owner's looks: False when there was no such look. Pictures made with
    it stay as they are."""
    number = _number(look_id)
    if number is None:
        return False
    with conn:
        gone = conn.execute("DELETE FROM looks WHERE id = ?", (number,)).rowcount
    return gone > 0


def cube_text(name: str, grid: Grid) -> str:
    """A look as a .cube file another app reads: its name, its size and its rows, red fastest."""
    rows = "\n".join(f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in grid.reshape(-1, 3).tolist())
    title = name.replace('"', "'")
    return f'TITLE "{title}"\nLUT_3D_SIZE {grid.shape[0]}\n{rows}\n'


def _text(data: bytes) -> str:
    """A .cube file's text: UTF-8 (or Windows' UTF-16, by its mark). Raises CubeError for a file
    that isn't text."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    elif b"\x00" not in data[:4096]:
        return data.decode("utf-8-sig", errors="replace")
    raise CubeError("It isn't a .cube file: it isn't text, as a .cube file is.")


def _checked(conn: sqlite3.Connection, name: str, but: int | None = None) -> str:
    """A name the owner gave, tidied, or why it can't be one."""
    tidy = " ".join(name.split())
    if not tidy:
        raise LookNameError("Give it a name first.")
    if len(tidy) > LONGEST:
        raise LookNameError(f"Keep its name to {LONGEST} letters or fewer.")
    if any(look.name.casefold() == tidy.casefold() for look in built_in()):
        raise LookNameError(f"{tidy} is one of Mado's own looks. Pick another name.")
    # Compared here rather than by SQLite, whose NOCASE folds only A to Z: "Été" is "ÉTÉ" too.
    for row in conn.execute("SELECT name FROM looks WHERE id IS NOT ?", (but,)):
        if str(row["name"]).casefold() == tidy.casefold():
            raise LookNameError(_taken(row["name"]))
    return tidy


def _taken(name: str) -> str:
    return f"You have a look called {name} already. Pick another name."


def _free_name(conn: sqlite3.Connection, name: str) -> str:
    """The name, or the name with "(2)", "(3)"… when it's taken, cut to fit with its number."""
    candidate, number = name, 2
    while True:
        try:
            return _checked(conn, candidate)
        except LookNameError:
            suffix = f" ({number})"
            candidate = f"{name[: LONGEST - len(suffix)].rstrip()}{suffix}"
            number += 1


def _added(
    conn: sqlite3.Connection,
    name: str,
    kind: Literal["cube", "mix"],
    grid: Grid,
    touches: Touches,
    source: str,
    now: datetime,
) -> Kept:
    amounts = {touch: touches.amount(touch) for touch in touches.on()}
    try:
        with conn:
            row = conn.execute(
                """INSERT INTO looks (name, kind, points, grid, touches, source, added_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING *""",
                (
                    name,
                    kind,
                    grid.shape[0],
                    packed(np.asarray(grid, np.float32)),
                    json.dumps(amounts) if kind == "mix" else None,
                    source,
                    now.isoformat(timespec="seconds"),
                ),
            ).fetchone()
    except sqlite3.IntegrityError:  # kept under that name a moment ago (asked twice at once)
        raise LookNameError(_taken(name)) from None
    return _kept(row)


def _kept(row: sqlite3.Row) -> Kept:
    amounts: object = json.loads(row["touches"]) if row["touches"] else {}
    touches = named(cast("dict[str, int]", amounts)) if isinstance(amounts, dict) else NONE
    return Kept(
        id=f"{YOURS}{row['id']}",
        name=row["name"],
        kind=row["kind"],
        points=row["points"],
        touches=touches,
        source=row["source"],
        added_at=row["added_at"],
    )


def _number(look_id: str) -> int | None:
    digits = look_id.removeprefix(YOURS)
    return int(digits) if look_id.startswith(YOURS) and digits.isdigit() else None
