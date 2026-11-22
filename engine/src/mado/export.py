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

from mado import __version__, db
from mado.config import DataPaths


def export_data(paths: DataPaths, folder: Path, now: datetime | None = None) -> Path | None:
    """Write `Mado export <date>.zip` into `folder` and return its path: the database, its
    settings as JSON, the library's folders as JSON and its pictures as CSV (what Mado read of
    each), History as CSV (each picture made, replaced or taken away, and what waits in
    quarantine), and a manifest saying which Mado wrote it.

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
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return target


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


_HISTORY_COLUMNS = (
    "at", "kind", "name", "madeFor", "original", "result", "aside", "clearedAt", "undoneAt",
)  # fmt: skip


def _history(conn: sqlite3.Connection) -> str:
    """What Mado did, oldest first, as CSV: each picture made or replaced, what waits in
    quarantine, and what was undone."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(_HISTORY_COLUMNS)
    if _has_table(conn, "history"):
        for row in conn.execute("SELECT * FROM history ORDER BY at, id"):
            writer.writerow(
                tuple(
                    row[column] or ""
                    for column in (
                        "at",
                        "kind",
                        "name",
                        "made_for",
                        "original",
                        "result",
                        "aside",
                        "cleared_at",
                        "cleared_by",
                        "undone_at",
                    )
                )
            )
    return out.getvalue()


def _state(row: sqlite3.Row) -> str:
    if row["raw"]:
        return "camera RAW, not read yet"
    if row["problem"]:
        return f"won't open: {row['problem']}"
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
