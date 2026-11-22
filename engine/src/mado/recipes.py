"""Recipes: a batch's steps and how it saves, kept by name to use again on any batch, or on every
new picture put in a watch folder (mado/watching.py). The steps are a list, each a kind and its
choices, so later pieces add kinds of their own (docs/stack/queue.md)."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import cast

NAME_LONGEST = 60


class RecipeError(ValueError):
    """A recipe that can't be kept or changed as asked, with a sentence saying why."""


@dataclass(frozen=True)
class Kept:
    id: int
    name: str
    steps: list[dict[str, object]]
    saving: dict[str, object]
    used: int  # batches made from it
    used_at: str | None
    added_at: str


def listed(conn: sqlite3.Connection) -> list[Kept]:
    """The owner's recipes, in the order they were kept."""
    return [_kept(row) for row in conn.execute("SELECT * FROM recipes ORDER BY id")]


def found(conn: sqlite3.Connection, recipe_id: int) -> Kept | None:
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return _kept(row) if row else None


def kept(
    conn: sqlite3.Connection,
    name: str,
    steps: list[dict[str, object]],
    saving: dict[str, object],
    now: datetime,
) -> Kept:
    """Keeps steps and how they save as a recipe. Raises RecipeError for a name that won't do."""
    checked = _checked(conn, name)
    with conn:
        row = conn.execute(
            """INSERT INTO recipes (name, steps, saving, added_at) VALUES (?, ?, ?, ?)
               RETURNING *""",
            (checked, json.dumps(steps), json.dumps(saving), now.isoformat(timespec="seconds")),
        ).fetchone()
    return _kept(row)


def changed(
    conn: sqlite3.Connection,
    recipe_id: int,
    name: str,
    steps: list[dict[str, object]],
    saving: dict[str, object],
) -> Kept | None:
    """A recipe's name, steps and saving changed: batches already in the queue make what they
    were asked for, and its watch folders the new. None when there's no such recipe."""
    checked = _checked(conn, name, but=recipe_id)
    with conn:
        row = conn.execute(
            "UPDATE recipes SET name = ?, steps = ?, saving = ? WHERE id = ? RETURNING *",
            (checked, json.dumps(steps), json.dumps(saving), recipe_id),
        ).fetchone()
    return _kept(row) if row else None


def deleted(conn: sqlite3.Connection, recipe_id: int) -> bool:
    """Deletes a recipe: batches made from it keep their steps. Raises RecipeError while a watch
    folder runs it."""
    watching = conn.execute(
        "SELECT path FROM watch_folders WHERE recipe_id = ? ORDER BY id LIMIT 1", (recipe_id,)
    ).fetchone()
    if watching is not None:
        raise RecipeError(
            f"{watching['path']} runs it as a watch folder: give that one another recipe, or "
            "stop watching it, first."
        )
    with conn:
        return conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,)).rowcount > 0


def _checked(conn: sqlite3.Connection, name: str, *, but: int | None = None) -> str:
    plain = " ".join(name.split())
    if not plain:
        raise RecipeError("Give it a name, so you can find it again.")
    if len(plain) > NAME_LONGEST:
        raise RecipeError(f"That name is long: keep it to {NAME_LONGEST} letters.")
    taken = conn.execute(
        "SELECT id FROM recipes WHERE name = ? COLLATE NOCASE AND id IS NOT ?", (plain, but)
    ).fetchone()
    if taken is not None:
        raise RecipeError(f"You have a recipe called {plain} already: give this one another name.")
    return plain


def _kept(row: sqlite3.Row) -> Kept:
    steps: object = json.loads(row["steps"])
    saving: object = json.loads(row["saving"])
    return Kept(
        id=row["id"],
        name=row["name"],
        steps=[
            cast("dict[str, object]", each)
            for each in (cast("list[object]", steps) if isinstance(steps, list) else [])
            if isinstance(each, dict)
        ],
        saving=cast("dict[str, object]", saving) if isinstance(saving, dict) else {},
        used=row["used"],
        used_at=row["used_at"],
        added_at=row["added_at"],
    )
