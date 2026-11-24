"""The owner's own painting styles, kept in the database: a picture's style as MicroAST read it (512
numbers, 2 KB) with a small copy of the picture to know it by, 160 pixels at most, never the
picture itself; and any style a recipe names, found (Mado's, the owner's, or a picture's carried
whole in the recipe).

Their names are the owner's: unique in any case, and never the name of one of Mado's styles. A
style's number is never given to another, so a recipe naming one deleted fails rather than paint
with another (as the owner's looks do, mado/own_looks.py).
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from mado.core.painting import (
    CLASSICS,
    CODE,
    PAINTERS,
    Floats,
    Style,
    code_of,
    mado_style,
    picture_style,
)

YOURS = "yours-"  # an own style's id, after its row: "yours-3"
LONGEST = 60  # letters a name may have


@dataclass(frozen=True)
class Kept:
    id: str  # "yours-3"
    name: str
    source: str  # the picture it came from, by name
    added_at: str


class StyleNameError(ValueError):
    """A name a style can't have, with a sentence saying why."""


def listed(conn: sqlite3.Connection) -> list[Kept]:
    """The owner's styles, oldest first."""
    return [_kept(row) for row in conn.execute("SELECT * FROM styles ORDER BY id")]


def found(conn: sqlite3.Connection, style_id: str) -> tuple[Kept, Style] | None:
    """One of the owner's styles and the style itself, by its id ("yours-3"); None when there's
    none (or its numbers are damaged in the records)."""
    row = _row(conn, style_id)
    if row is None:
        return None
    kept = _kept(row)
    data = bytes(row["code"])
    if len(data) != CODE * 4:
        return None
    try:
        style = picture_style(kept.name, np.frombuffer(data, "<f4"), kept.id)
    except ValueError:
        return None
    return kept, style


def thumbnail(conn: sqlite3.Connection, style_id: str) -> bytes | None:
    """The small copy of the picture an own style came from."""
    row = _row(conn, style_id)
    return bytes(row["thumbnail"]) if row is not None else None


def resolve(conn: sqlite3.Connection, asked: dict[str, object]) -> Style | None:
    """The style a recipe's painting step names: one of Mado's ("hokusai"), the owner's
    ("yours-3"), or a picture's carried whole (`style` "picture", its `code` and the picture's
    name as `named`); None when it isn't there any more, or can't be read."""
    style_id = str(asked.get("style", ""))
    if style_id == "picture":
        code, named = asked.get("code"), asked.get("named")
        if not isinstance(code, str):
            return None
        try:
            return picture_style(
                named if isinstance(named, str) and named else "A picture's", code_of(code)
            )
        except ValueError:
            return None
    if style_id.startswith(YOURS):
        mine = found(conn, style_id)
        return mine[1] if mine else None
    return mado_style(style_id)


def kept(
    conn: sqlite3.Connection,
    name: str,
    code: Floats,
    small: bytes,
    source: str,
    now: datetime,
) -> Kept:
    """A picture's style kept as one of the owner's: its numbers and a small copy of the picture
    (`small`, made by the caller). Raises StyleNameError."""
    tidy = _checked(conn, name)
    values = np.asarray(code, "<f4").ravel()
    if values.size != CODE:
        raise ValueError(f"A picture's style is {CODE} numbers, not {values.size}.")
    try:
        with conn:
            row = conn.execute(
                """INSERT INTO styles (name, code, thumbnail, source, added_at)
                   VALUES (?, ?, ?, ?, ?) RETURNING *""",
                (tidy, values.tobytes(), small, source, now.isoformat(timespec="seconds")),
            ).fetchone()
    except sqlite3.IntegrityError:  # kept under that name a moment ago (asked twice at once)
        raise StyleNameError(_taken(tidy)) from None
    return _kept(row)


def renamed(conn: sqlite3.Connection, style_id: str, name: str) -> Kept | None:
    """One of the owner's styles under a new name; None when there's no such style. Raises
    StyleNameError."""
    row = _row(conn, style_id)
    if row is None:
        return None
    tidy = _checked(conn, name, but=row["id"])
    try:
        with conn:
            conn.execute("UPDATE styles SET name = ? WHERE id = ?", (tidy, row["id"]))
    except sqlite3.IntegrityError:
        raise StyleNameError(_taken(tidy)) from None
    return _kept(_row(conn, style_id) or row)


def deleted(conn: sqlite3.Connection, style_id: str) -> bool:
    """Deletes one of the owner's styles: False when there was no such style. Pictures painted
    with it stay as they are."""
    number = _number(style_id)
    if number is None:
        return False
    with conn:
        return conn.execute("DELETE FROM styles WHERE id = ?", (number,)).rowcount > 0


def _checked(conn: sqlite3.Connection, name: str, but: int | None = None) -> str:
    tidy = " ".join(name.split())
    if not tidy:
        raise StyleNameError("Give it a name first.")
    if len(tidy) > LONGEST:
        raise StyleNameError(f"Keep its name to {LONGEST} letters or fewer.")
    if any(style.name.casefold() == tidy.casefold() for style in (*PAINTERS, *CLASSICS)):
        raise StyleNameError(f"{tidy} is one of Mado's own styles. Pick another name.")
    # Compared here rather than by SQLite, whose NOCASE folds only A to Z.
    for row in conn.execute("SELECT name FROM styles WHERE id IS NOT ?", (but,)):
        if str(row["name"]).casefold() == tidy.casefold():
            raise StyleNameError(_taken(row["name"]))
    return tidy


def _taken(name: str) -> str:
    return f"You have a style called {name} already. Pick another name."


def _row(conn: sqlite3.Connection, style_id: str) -> sqlite3.Row | None:
    number = _number(style_id)
    if number is None:
        return None
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM styles WHERE id = ?", (number,)
    ).fetchone()
    return row


def _kept(row: sqlite3.Row) -> Kept:
    return Kept(
        id=f"{YOURS}{row['id']}", name=row["name"], source=row["source"], added_at=row["added_at"]
    )


def _number(style_id: str) -> int | None:
    digits = style_id.removeprefix(YOURS)
    return int(digits) if style_id.startswith(YOURS) and digits.isdigit() else None
