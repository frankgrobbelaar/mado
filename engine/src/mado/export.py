"""Export: everything Mado knows, in one zip you can open without Mado."""

import csv
import io
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from mado import __version__, db, own_looks
from mado.config import DataPaths

_UNSAFE = str.maketrans(dict.fromkeys('<>:"/\\|?*', "-"))


def export_data(paths: DataPaths, folder: Path, now: datetime | None = None) -> Path | None:
    """Write `Mado export <date>.zip` into `folder` and return its path: the database, its
    settings as JSON, the library's folders as JSON and its pictures as CSV (what Mado read of
    each), History as CSV (each picture made, replaced, taken away or set aside, and what waits
    in quarantine), the owner's looks (listed in JSON, each a .cube file any app opens), their
    recipes and watch folders as JSON, what they decided of duplicates and bursts as JSON, and a
    manifest saying which Mado wrote it.

    Returns None when Mado has no data yet. Never overwrites a file: a second
    export on the same day becomes `Mado export <date> (2).zip`.
    """
    if not paths.database.exists():
        return None
    now = now or datetime.now().astimezone()
    folder.mkdir(parents=True, exist_ok=True)
    target = _unused_name(folder / f"Mado export {now:%Y-%m-%d}.zip")

    with tempfile.TemporaryDirectory() as scratch:
        snapshot = Path(scratch) / "mado.db"
        with (
            closing(db.connect(paths.database)) as source,
            closing(sqlite3.connect(snapshot)) as copy,
        ):
            source.backup(copy)
            copy.execute("PRAGMA journal_mode = DELETE")  # one self-contained file
            settings = _settings(source)
            library_folders = _folders(source)
            pictures = _pictures(source)
            done = _history(source)
            looks = _looks(source)
            kept_recipes = _recipes(source)
            watch_folders = _watch_folders(source)
            duplicates = _duplicates(source)
            schema_version = db.schema_version(source)

        manifest = {
            "app": "Mado",
            "version": __version__,
            "exportedAt": now.isoformat(timespec="seconds"),
            "schemaVersion": schema_version,
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "mado.db")
            archive.writestr("settings.json", json.dumps(settings, indent=2))
            archive.writestr("folders.json", json.dumps(library_folders, indent=2))
            archive.writestr("pictures.csv", pictures)
            archive.writestr("history.csv", done)
            archive.writestr("looks.json", json.dumps([each for each, _ in looks], indent=2))
            for listed, text in looks:
                archive.writestr(str(listed["file"]), text)
            archive.writestr("recipes.json", json.dumps(kept_recipes, indent=2))
            archive.writestr("watch-folders.json", json.dumps(watch_folders, indent=2))
            archive.writestr("duplicates.json", json.dumps(duplicates, indent=2))
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return target


def _duplicates(conn: sqlite3.Connection) -> dict[str, object]:
    """What the owner decided of duplicates and bursts: the pictures they said aren't the same
    (by their paths), which of a group they keep or set aside, and each setting aside."""
    if not _has_table(conn, "not_same"):
        return {"notTheSame": [], "choices": [], "reviews": []}
    pairs = [
        sorted([row["first"], row["second"]])
        for row in conn.execute(
            """SELECT a.path AS first, b.path AS second FROM not_same AS n
               JOIN pictures AS a ON a.id = n.first JOIN pictures AS b ON b.id = n.second
               ORDER BY a.path, b.path"""
        )
    ]
    choices = [
        {"path": row["path"], "keep": bool(row["keep"])}
        for row in conn.execute(
            """SELECT p.path, c.keep FROM choices AS c JOIN pictures AS p ON p.id = c.picture_id
               ORDER BY p.path"""
        )
    ]
    reviews = [
        {"at": row["at"], "duplicates": row["duplicates"], "bursts": row["bursts"]}
        for row in conn.execute("SELECT at, duplicates, bursts FROM reviews ORDER BY id")
    ]
    return {"notTheSame": pairs, "choices": choices, "reviews": reviews}


def _recipes(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """The owner's recipes: each one's steps and how it saves, as Mado keeps them."""
    if not _has_table(conn, "recipes"):
        return []
    return [
        {
            "name": row["name"],
            "steps": json.loads(row["steps"]),
            "saving": json.loads(row["saving"]),
            "used": row["used"],
            "usedAt": row["used_at"],
        }
        for row in conn.execute("SELECT * FROM recipes ORDER BY id")
    ]


def _watch_folders(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """The watch folders: each one's folder, its recipe, where its pictures go, on or off."""
    if not _has_table(conn, "watch_folders"):
        return []
    return [
        {
            "folder": row["path"],
            "recipe": row["recipe"],
            "results": row["results"],
            "watching": bool(row["watching"]),
        }
        for row in conn.execute(
            """SELECT w.path, w.results, w.watching, r.name AS recipe FROM watch_folders AS w
               JOIN recipes AS r ON r.id = w.recipe_id ORDER BY w.id"""
        )
    ]


def _looks(conn: sqlite3.Connection) -> list[tuple[dict[str, object], str]]:
    """The owner's looks, each as the export lists it and as a .cube file's text."""
    if not _has_table(conn, "looks"):
        return []
    found: list[tuple[dict[str, object], str]] = []
    files: set[str] = set()
    for kept in own_looks.listed(conn):
        mine = own_looks.found(conn, kept.id)
        if mine is None or mine[1].grid is None:
            continue  # a table damaged in the records: nothing to write out
        base = f"looks/{kept.name.translate(_UNSAFE)}"
        file, number = f"{base}.cube", 2
        while file.casefold() in files:
            file, number = f"{base} ({number}).cube", number + 1
        files.add(file.casefold())
        listed: dict[str, object] = {
            "name": kept.name,
            "kind": kept.kind,
            "source": kept.source,
            "touches": {touch: kept.touches.amount(touch) for touch in kept.touches.on()},
            "points": kept.points,
            "addedAt": kept.added_at,
            "file": file,
        }
        found.append((listed, own_looks.cube_text(kept.name, mine[1].grid)))
    return found


def _settings(conn: sqlite3.Connection) -> dict[str, object]:
    if not _has_table(conn, "settings"):
        return {}
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key")
    return {row["key"]: json.loads(row["value"]) for row in rows}


def _folders(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """The library's folders, in the order they were added."""
    if not _has_table(conn, "folders"):
        return []
    rows = conn.execute("SELECT path, added_at FROM folders ORDER BY id")
    return [{"path": row["path"], "addedAt": row["added_at"]} for row in rows]


_PICTURE_COLUMNS = (
    "path", "format", "width", "height", "size", "takenAt", "takenFrom", "camera", "located",
    "state",
)  # fmt: skip


def _pictures(conn: sqlite3.Connection) -> str:
    """Every picture in the library, with what Mado read of it, as CSV a spreadsheet opens."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(_PICTURE_COLUMNS)
    if _has_table(conn, "pictures"):
        for row in conn.execute("SELECT * FROM pictures WHERE gone_at IS NULL ORDER BY path"):
            writer.writerow(
                (
                    row["path"],
                    row["format"] or "",
                    row["width"] or "",
                    row["height"] or "",
                    row["size"],
                    row["taken_at"],
                    row["taken_from"],
                    row["camera"] or "",
                    "yes" if row["located"] else "no",
                    _state(row),
                )
            )
    return out.getvalue()


# Each of History's columns as the export names it, and the column it's kept in.
_HISTORY_COLUMNS = (
    ("at", "at"),
    ("kind", "kind"),
    ("name", "name"),
    ("madeFor", "made_for"),
    ("look", "look"),
    ("edit", "edit"),
    ("original", "original"),
    ("result", "result"),
    ("aside", "aside"),
    ("clearedAt", "cleared_at"),
    ("clearedBy", "cleared_by"),
    ("undoneAt", "undone_at"),
    ("kept", "kept"),
    ("review", "review_id"),
)


def _history(conn: sqlite3.Connection) -> str:
    """What Mado did, oldest first, as CSV: each picture made, replaced or set aside, what it was
    made for and with and what was edited (or the picture kept in its place), what waits in
    quarantine, and what was undone."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(name for name, _column in _HISTORY_COLUMNS)
    if _has_table(conn, "history"):
        for row in conn.execute("SELECT * FROM history ORDER BY at, id"):
            kept = row.keys()
            writer.writerow(
                ("" if row[column] is None else row[column]) if column in kept else ""
                for _name, column in _HISTORY_COLUMNS
            )
    return out.getvalue()


def _state(row: sqlite3.Row) -> str:
    if row["raw"]:
        return "camera RAW, not read yet"
    if row["problem"]:
        damaged = "damaged" in row.keys() and row["damaged"]  # noqa: SIM118 - a Row's
        return f"won't open{', marked as damaged' if damaged else ''}: {row['problem']}"
    return "read" if row["read_at"] else "still to read"


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?"
    return conn.execute(query, (name,)).fetchone() is not None


def _unused_name(path: Path) -> Path:
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate
